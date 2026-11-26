"""分析服务回归测试"""

import pytest

from models.schemas import UserProfile
from services.analysis_service import AnalysisService

# 零度可乐 OCR 样例（来自 main.py 注释）
COLA_OCR_TEXT = (
    "259647318577514&bdtype=0&commodity=&copyright=&cs=6口公司外面娱乐m常用YouTube"
    "SJKEZER7/9饮「零度可口可乐水的美味配料食品添加剂[二氧化碳、焦糖色、非甲酸钠、"
    "阿斯巴甜(含苯丙氨酸)、安赛蜜、柠檬酸钠咖啡因、蔗糖素]、食用香精由可口可乐"
)

COLA_EXPECTED_MATCHED = {
    "二氧化碳",
    "焦糖色",
    "苯甲酸钠",
    "阿斯巴甜",
    "安赛蜜",
    "柠檬酸钠",
    "咖啡因",
    "三氯蔗糖",
}


@pytest.fixture(scope="module")
def service():
    return AnalysisService()


@pytest.fixture
def run_analyze(service):
    async def _run(text, user_notes=None, user_profile=None):
        return await service.analyze_ingredients(text, user_notes, user_profile)

    return _run


@pytest.mark.asyncio
async def test_cola_sample_matches(run_analyze):
    result = await run_analyze(COLA_OCR_TEXT)
    assert set(result.matched_ingredients) == COLA_EXPECTED_MATCHED
    assert "柠檬酸" not in result.matched_ingredients
    assert result.confidence >= 0.9


@pytest.mark.asyncio
async def test_ingredient_section_extraction(run_analyze):
    result = await run_analyze(COLA_OCR_TEXT)
    assert "非甲酸钠" in result.ingredient_section
    assert "许可证" not in result.ingredient_section


@pytest.mark.asyncio
async def test_ocr_correction_benzoate(run_analyze):
    text = "配料：水、非甲酸钠、食用盐"
    result = await run_analyze(text)
    assert "苯甲酸钠" in result.matched_ingredients


@pytest.mark.asyncio
async def test_alias_sucralose(run_analyze):
    text = "食品添加剂：蔗糖素、水"
    result = await run_analyze(text)
    assert "三氯蔗糖" in result.matched_ingredients


@pytest.mark.asyncio
async def test_no_substring_false_positive(run_analyze):
    text = "配料：柠檬酸钠、水"
    result = await run_analyze(text)
    assert "柠檬酸钠" in result.matched_ingredients
    assert "柠檬酸" not in result.matched_ingredients


@pytest.mark.asyncio
async def test_greedy_decompose_merged_text(run_analyze):
    text = "配料：柠檬酸钠咖啡因"
    result = await run_analyze(text)
    assert "柠檬酸钠" in result.matched_ingredients
    assert "咖啡因" in result.matched_ingredients


@pytest.mark.asyncio
async def test_unknown_ingredients(run_analyze):
    text = "配料：水、神秘提取物X、未知成分Y"
    result = await run_analyze(text)
    assert any("神秘" in u for u in result.unknown_ingredients)
    assert "水" in result.matched_ingredients


@pytest.mark.asyncio
async def test_base_ingredient_layer(run_analyze):
    text = "配料：水、小麦粉、白砂糖、苯甲酸钠"
    result = await run_analyze(text)
    assert "水" in result.matched_ingredients
    assert len(result.by_type.base_ingredients) >= 2
    assert len(result.by_type.additives) >= 1


@pytest.mark.asyncio
async def test_database_size(service):
    assert len(service.ingredient_db) >= 500


@pytest.mark.asyncio
async def test_fuzzy_suggestion_for_typo(run_analyze):
    text = "配料：山梨酸纳、水"
    result = await run_analyze(text)
    assert result.unknown_ingredients
    assert any(
        s.unknown and any("山梨酸钾" in c for c in s.candidates)
        for s in result.ingredient_suggestions
    )


@pytest.mark.asyncio
async def test_coverage_stats(run_analyze):
    result = await run_analyze(COLA_OCR_TEXT)
    assert result.coverage["matched_count"] >= 8
    assert result.coverage["database_size"] >= 400


@pytest.mark.asyncio
async def test_allergen_profile(run_analyze):
    profile = UserProfile(allergens=["花生"])
    result = await run_analyze("配料：花生、白砂糖", user_profile=profile)
    assert any(i.name == "花生" for i in result.by_type.user_focus)


@pytest.mark.asyncio
async def test_e_number_alias(run_analyze):
    result = await run_analyze("配料：E330、水")
    assert "柠檬酸" in result.matched_ingredients


@pytest.mark.asyncio
async def test_by_category_grouping(run_analyze):
    result = await run_analyze(COLA_OCR_TEXT)
    assert "甜味剂" in result.by_category
    assert len(result.by_category["甜味剂"]) >= 3


@pytest.mark.asyncio
async def test_user_profile_highlights(run_analyze):
    profile = UserProfile(
        conditions=["苯丙酮尿症"],
        watch_categories=["甜味剂"],
    )
    result = await run_analyze(COLA_OCR_TEXT, user_profile=profile)
    highlight_names = {i.name for i in result.user_highlights}
    assert "阿斯巴甜" in highlight_names
    assert len(result.personal_warnings) >= 2


@pytest.mark.asyncio
async def test_user_notes_parsing(run_analyze):
    result = await run_analyze(
        "配料：苯甲酸钠、柠檬黄",
        user_notes="我对防腐剂过敏，给孩子买",
    )
    assert len(result.personal_warnings) >= 1
    highlight_names = {i.name for i in result.user_highlights}
    assert "苯甲酸钠" in highlight_names or "柠檬黄" in highlight_names


@pytest.mark.asyncio
async def test_needs_attention(run_analyze):
    text = "配料：阿斯巴甜、焦糖色"
    result = await run_analyze(text)
    attention_names = {i.name for i in result.needs_attention}
    assert "阿斯巴甜" in attention_names
    assert "焦糖色" not in attention_names


@pytest.mark.asyncio
async def test_msg_alias(run_analyze):
    text = "配料：谷氨酸钠、食用盐"
    result = await run_analyze(text)
    assert "谷氨酸钠" in result.matched_ingredients


@pytest.mark.asyncio
async def test_monoglyceride_alias(run_analyze):
    text = "配料：单甘酯、小麦粉"
    result = await run_analyze(text)
    assert "单硬脂酸甘油酯" in result.matched_ingredients
    assert "小麦粉" in result.matched_ingredients


@pytest.mark.asyncio
async def test_empty_text(run_analyze):
    result = await run_analyze("")
    assert result.matched_ingredients == []
    assert result.confidence <= 0.35
