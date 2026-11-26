import json
import os
import uuid
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

from config.auth import verify_admin
from config.settings import get_settings
from models.schemas import ScanHistoryItem, UserProfile
from routes.admin import router as admin_router
from services.analysis_service import AnalysisService
from services.ingredient_store import get_ingredient_store
from services.ocr_service import OCRService
from services.runtime import set_analysis_service, sync_analysis_from_store

app = FastAPI(title="食品成分分析系统", version="2.2.0")

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

ocr_service = OCRService()
analysis_service = AnalysisService()
set_analysis_service(analysis_service)
ingredient_store = get_ingredient_store()

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(admin_router)

@app.get("/admin")
async def admin_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/api/admin/page")

settings = get_settings()
oss_domain = settings.oss_domain_normalized
os.makedirs("uploads", exist_ok=True)


def _parse_user_profile(raw: Optional[str]) -> Optional[UserProfile]:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return UserProfile(**data)
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"user_profile 格式无效: {e}")


def _validate_and_download_image(full_url: str) -> str:
    """下载并校验图片，返回本地临时路径（阿里云 OCR 仍使用公网 URL）"""
    response = requests.get(full_url, timeout=30)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if content_type and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="提供的 URL 不是有效的图片")

    filename = f"{uuid.uuid4()}.jpg"
    file_path = os.path.join("uploads", filename)
    with open(file_path, "wb") as f:
        f.write(response.content)
    return file_path


@app.get("/api/index")
async def index():
    store = get_ingredient_store()
    return {
        "code": 1,
        "message": "success index",
        "data": {
            "database_size": len(store.ingredient_db),
            "ocr_provider": settings.ocr_provider,
        },
    }


@app.get("/api/health")
async def health_check():
    store = get_ingredient_store()
    return {
        "code": 1,
        "message": "success",
        "data": {
            "database_size": len(store.ingredient_db),
            "ocr_provider": settings.ocr_provider,
        },
    }


@app.post("/api/analyze")
@app.post("/api/food/analyze")  # 旧版前端兼容
async def analyze_food(
    image_url: str = Form(...),
    user_notes: Optional[str] = Form(None),
    user_profile: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
):
    file_path = None
    try:
        profile = _parse_user_profile(user_profile)
        full_url = (
            image_url
            if image_url.startswith(("http://", "https://"))
            else oss_domain + image_url
        )

        # 下载校验图片（与旧版 main 分支一致；阿里云 OCR 需公网可访问 URL）
        file_path = _validate_and_download_image(full_url)

        ocr_result = await ocr_service.extract_text_with_meta(full_url)
        analysis_result = await analysis_service.analyze_ingredients(
            ocr_result.text,
            user_notes,
            profile,
            user_id=user_id,
            source_type="ocr",
        )
        return {
            "code": 1,
            "message": "success",
            "data": {
                "text_result": ocr_result.text,
                "ocr_meta": {
                    "provider": ocr_result.provider,
                    "avg_confidence": ocr_result.avg_confidence,
                    "low_confidence_words": ocr_result.low_confidence_words,
                },
                "analysis_result": analysis_result,
            },
        }
    except requests.RequestException as e:
        raise HTTPException(status_code=400, detail=f"无法下载图片: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


@app.post("/api/analyze-text")
@app.post("/api/food/analyze_text")  # 旧版前端兼容
async def analyze_text(
    text_input: Optional[str] = Form(None),
    text_result: Optional[str] = Form(None),  # 旧版前端字段名
    user_notes: Optional[str] = Form(None),
    user_profile: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
):
    try:
        content = (text_input or text_result or "").strip()
        if not content:
            raise HTTPException(
                status_code=422,
                detail="请提供 text_input 或 text_result（配料表文本）",
            )
        profile = _parse_user_profile(user_profile)
        analysis_result = await analysis_service.analyze_ingredients(
            content,
            user_notes,
            profile,
            user_id=user_id,
            source_type="text",
        )
        return {"code": 1, "message": "success", "data": {"analysis_result": analysis_result}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@app.get("/api/history")
async def list_scan_history(
    user_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    rows = ingredient_store.list_scans(user_id=user_id, limit=limit)
    items = []
    for row in rows:
        matched = json.loads(row["matched_json"] or "[]")
        unknown = json.loads(row["unknown_json"] or "[]")
        items.append(
            ScanHistoryItem(
                id=row["id"],
                user_id=row["user_id"],
                source_type=row["source_type"],
                matched_count=len(matched),
                unknown_count=len(unknown),
                matched_ingredients=matched,
                unknown_ingredients=unknown,
                created_at=row["created_at"],
            )
        )
    return {"code": 1, "message": "success", "data": {"items": items}}


@app.post("/api/ocr-corrections", dependencies=[Depends(verify_admin)])
async def add_ocr_correction(
    ocr_text: str = Form(...),
    canonical_name: str = Form(...),
):
    try:
        ingredient_store.add_ocr_correction(ocr_text, canonical_name)
        return {
            "code": 1,
            "message": "success",
            "data": {"database_size": len(ingredient_store.ingredient_db)},
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

