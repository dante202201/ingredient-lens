"""OCR 提供商路由测试"""

import pytest

from config.settings import get_settings
from services.ocr_service import OCRService, OcrResult


@pytest.mark.asyncio
async def test_ocr_provider_tysbgpu(monkeypatch):
    monkeypatch.setenv("OCR_PROVIDER", "tysbgpu")
    get_settings.cache_clear()

    service = OCRService()

    def fake_tysbgpu(url):
        return OcrResult(text="测试文本", provider="tysbgpu", avg_confidence=0.9)

    monkeypatch.setattr(service, "_tysbgpu_with_meta", fake_tysbgpu)
    result = await service.extract_text_with_meta("http://example.com/a.jpg")
    assert result.provider == "tysbgpu"
    assert result.text == "测试文本"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_ocr_provider_ali(monkeypatch):
    monkeypatch.setenv("OCR_PROVIDER", "ali")
    get_settings.cache_clear()

    service = OCRService()

    async def fake_ali(url, ocr_type=None):
        return "阿里云识别结果"

    monkeypatch.setattr(service._ali_ocr, "recognize_text", fake_ali)
    result = await service.extract_text_with_meta("http://example.com/a.jpg")
    assert result.provider == "ali"
    assert result.text == "阿里云识别结果"

    get_settings.cache_clear()
