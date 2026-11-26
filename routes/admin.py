"""管理后台 API"""

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from config.auth import verify_admin
from models.schemas import IngredientUpsert
from services.ingredient_store import IngredientStore
from services.runtime import sync_analysis_from_store
from typing import Optional

ADMIN_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "admin")

router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_store() -> IngredientStore:
    from services.ingredient_store import get_ingredient_store

    return get_ingredient_store()


@router.get("/page")
async def admin_page():
    index = os.path.join(ADMIN_DIR, "index.html")
    if not os.path.exists(index):
        raise HTTPException(status_code=404, detail="管理页面不存在")
    return FileResponse(index)


@router.get("/stats", dependencies=[Depends(verify_admin)])
async def admin_stats(store: IngredientStore = Depends(get_store)):
    return {"code": 1, "message": "success", "data": store.get_stats()}


@router.get("/ingredients", dependencies=[Depends(verify_admin)])
async def list_ingredients(
    q: Optional[str] = Query(None),
    ingredient_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    store: IngredientStore = Depends(get_store),
):
    data = store.search_ingredients(q, ingredient_type, category, page, page_size)
    return {"code": 1, "message": "success", "data": data}


@router.get("/ingredients/{name}", dependencies=[Depends(verify_admin)])
async def get_ingredient(name: str, store: IngredientStore = Depends(get_store)):
    detail = store.get_ingredient_detail(name)
    if not detail:
        raise HTTPException(status_code=404, detail="成分不存在")
    return {"code": 1, "message": "success", "data": detail}


@router.post("/ingredients", dependencies=[Depends(verify_admin)])
async def create_ingredient(body: IngredientUpsert, store: IngredientStore = Depends(get_store)):
    if body.name in store.ingredient_db:
        raise HTTPException(status_code=409, detail="成分已存在，请使用 PUT 更新")
    store.upsert_ingredient(body.model_dump())
    store.reload()
    sync_analysis_from_store(store)
    return {"code": 1, "message": "success", "data": store.get_ingredient_detail(body.name)}


@router.put("/ingredients/{name}", dependencies=[Depends(verify_admin)])
async def update_ingredient(
    name: str, body: IngredientUpsert, store: IngredientStore = Depends(get_store)
):
    if name not in store.ingredient_db and name != body.name:
        raise HTTPException(status_code=404, detail="成分不存在")
    payload = body.model_dump()
    if body.name != name:
        store.rename_ingredient(name, body.name, payload)
    else:
        store.upsert_ingredient(payload)
    store.reload()
    sync_analysis_from_store(store)
    return {"code": 1, "message": "success", "data": store.get_ingredient_detail(body.name)}


@router.delete("/ingredients/{name}", dependencies=[Depends(verify_admin)])
async def delete_ingredient(name: str, store: IngredientStore = Depends(get_store)):
    if not store.delete_ingredient(name):
        raise HTTPException(status_code=404, detail="成分不存在")
    store.reload()
    sync_analysis_from_store(store)
    return {"code": 1, "message": "success", "data": {}}


@router.get("/unknown-candidates", dependencies=[Depends(verify_admin)])
async def unknown_candidates(
    min_hits: int = Query(2, ge=1),
    limit: int = Query(50, ge=1, le=200),
    store: IngredientStore = Depends(get_store),
):
    items = store.list_unknown_candidates(min_hits=min_hits, limit=limit)
    return {"code": 1, "message": "success", "data": {"items": items}}


@router.get("/ocr-corrections", dependencies=[Depends(verify_admin)])
async def list_ocr_corrections(
    limit: int = Query(50, ge=1, le=200),
    store: IngredientStore = Depends(get_store),
):
    items = store.list_ocr_corrections(limit=limit)
    return {"code": 1, "message": "success", "data": {"items": items}}


@router.post("/reload-database", dependencies=[Depends(verify_admin)])
async def reload_database(store: IngredientStore = Depends(get_store)):
    """从 YAML/CSV 重新同步成分库"""
    count = store.sync_from_files()
    store.reload()
    sync_analysis_from_store(store)
    return {
        "code": 1,
        "message": "success",
        "data": {"synced": count, "database_size": len(store.ingredient_db)},
    }


@router.get("/export-yaml", dependencies=[Depends(verify_admin)])
async def export_yaml(store: IngredientStore = Depends(get_store)):
    """导出当前 SQLite 成分库为 YAML 结构（JSON 格式返回，便于下载/备份）"""
    import yaml

    grouped = store.export_to_yaml_dict()
    files = {}
    for ing_type, ingredients in grouped.items():
        if not ingredients:
            continue
        files[f"{ing_type}.yaml"] = yaml.dump(
            {"default_type": ing_type, "ingredients": ingredients},
            allow_unicode=True,
            sort_keys=False,
        )
    return {
        "code": 1,
        "message": "success",
        "data": {
            "files": files,
            "total": sum(len(v) for v in grouped.values()),
        },
    }
