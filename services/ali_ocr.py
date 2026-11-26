# -*- coding: utf-8 -*-
"""阿里云 OCR 官方 SDK（RecognizeAllText）"""

from typing import Optional

from alibabacloud_ocr_api20210707 import models as ocr_api_20210707_models
from alibabacloud_ocr_api20210707.client import Client as OcrApi20210707Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models

from config.settings import get_settings


class AliOCRService:
    def __init__(self):
        settings = get_settings()
        self.access_key_id = settings.ali_access_key_id
        self.access_key_secret = settings.ali_access_key_secret
        self.endpoint = settings.ali_ocr_endpoint
        self.ocr_type = settings.ali_ocr_type
        self._client: Optional[OcrApi20210707Client] = None

    def _create_client(self) -> OcrApi20210707Client:
        if self._client is None:
            settings = get_settings()
            config = open_api_models.Config(
                access_key_id=settings.require_ali_access_key_id(),
                access_key_secret=settings.require_ali_access_key_secret(),
            )
            config.endpoint = self.endpoint
            self._client = OcrApi20210707Client(config)
        return self._client

    async def recognize_text(self, url: str, ocr_type: Optional[str] = None) -> str:
        client = self._create_client()
        request = ocr_api_20210707_models.RecognizeAllTextRequest(
            url=url,
            type=ocr_type or self.ocr_type,
        )
        runtime = util_models.RuntimeOptions()
        try:
            resp = await client.recognize_all_text_with_options_async(request, runtime)
            return resp.body.data.content or ""
        except Exception as error:
            error_msg = getattr(error, "message", str(error))
            recommend_url = ""
            if hasattr(error, "data") and error.data:
                recommend_url = error.data.get("Recommend", "")
            detail = f"阿里云 OCR 识别失败: {error_msg}"
            if recommend_url:
                detail += f"\n诊断地址: {recommend_url}"
            raise RuntimeError(detail) from error
