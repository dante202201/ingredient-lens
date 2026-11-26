"""应用配置（从环境变量读取）"""

import os
from functools import lru_cache


@lru_cache
def get_settings() -> "Settings":
    return Settings()


class Settings:
    def __init__(self) -> None:
        self.admin_token: str = os.getenv("ADMIN_TOKEN", "")
        # OCR 提供商: ali（官方 SDK）| tysbgpu（市场 AppCode）
        self.ocr_provider: str = os.getenv("OCR_PROVIDER", "ali").strip().lower()
        self.ocr_appcode: str = os.getenv("OCR_APPCODE", "")
        self.ocr_api_url: str = os.getenv(
            "OCR_API_URL",
            "https://tysbgpu.market.alicloudapi.com/api/predict/ocr_general",
        )
        self.ali_access_key_id: str = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
        self.ali_access_key_secret: str = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
        self.ali_ocr_endpoint: str = os.getenv(
            "ALI_OCR_ENDPOINT", "ocr-api.cn-hangzhou.aliyuncs.com"
        )
        self.ali_ocr_type: str = os.getenv("ALI_OCR_TYPE", "Advanced")
        self.oss_domain: str = os.getenv(
            "OSS_DOMAIN", "https://your-bucket.oss-cn-beijing.aliyuncs.com/"
        )
        self.cors_origins: list[str] = self._parse_cors_origins()

    def _parse_cors_origins(self) -> list[str]:
        raw = os.getenv("CORS_ORIGINS", "")
        if raw.strip():
            return [o.strip() for o in raw.split(",") if o.strip()]
        return [
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]

    @property
    def oss_domain_normalized(self) -> str:
        domain = self.oss_domain
        if domain and not domain.endswith("/"):
            domain += "/"
        return domain

    def require_ocr_appcode(self) -> str:
        if not self.ocr_appcode:
            raise ValueError(
                "未配置 OCR_APPCODE，请在 .env 中设置（OCR_PROVIDER=tysbgpu 时必填）"
            )
        return self.ocr_appcode

    def require_ali_access_key_id(self) -> str:
        if not self.ali_access_key_id:
            raise ValueError(
                "未配置 ALIBABA_CLOUD_ACCESS_KEY_ID，请在 .env 中设置（OCR_PROVIDER=ali 时必填）"
            )
        return self.ali_access_key_id

    def require_ali_access_key_secret(self) -> str:
        if not self.ali_access_key_secret:
            raise ValueError(
                "未配置 ALIBABA_CLOUD_ACCESS_KEY_SECRET，请在 .env 中设置（OCR_PROVIDER=ali 时必填）"
            )
        return self.ali_access_key_secret
