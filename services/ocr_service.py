import asyncio
from dataclasses import dataclass, field
from typing import List

from config.settings import get_settings
import services.tysbgpu_ocr as tysbgpu_ocr
from services.ali_ocr import AliOCRService


@dataclass
class OcrResult:
    text: str
    provider: str = "tysbgpu"
    low_confidence_words: List[str] = field(default_factory=list)
    avg_confidence: float = 1.0


class OCRService:
    def __init__(self):
        self._ali_ocr = AliOCRService()

    async def extract_text(self, image_url: str) -> str:
        result = await self.extract_text_with_meta(image_url)
        return result.text

    async def extract_text_with_meta(self, image_url: str) -> OcrResult:
        provider = get_settings().ocr_provider
        try:
            if provider == "ali":
                text = await self._ali_ocr.recognize_text(image_url)
                return OcrResult(text=text, provider="ali")
            return await asyncio.get_event_loop().run_in_executor(
                None, self._tysbgpu_with_meta, image_url
            )
        except Exception as e:
            raise Exception(f"OCR 处理失败: {str(e)}") from e

    def _tysbgpu_with_meta(self, image_url: str) -> OcrResult:
        ocr = tysbgpu_ocr.OCRService()
        payload = ocr.request_with_meta(image_url, ocr.params)
        return OcrResult(
            text=payload["text"],
            provider="tysbgpu",
            low_confidence_words=payload.get("low_confidence_words") or [],
            avg_confidence=payload.get("avg_confidence") or 1.0,
        )
