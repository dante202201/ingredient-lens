import re
from typing import Dict, List, Optional, Tuple

from models.schemas import (
    AnalysisResult,
    FoodItem,
    Ingredient,
    IngredientSuggestion,
    IngredientType,
    LayeredIngredients,
    SafetyLevel,
    UserProfile,
)
from services.fuzzy_matcher import suggest_ingredients
from services.ingredient_store import get_ingredient_store
from services.ingredient_loader import register_jieba_dictionary

INGREDIENT_SECTION_PATTERNS = [
    r"(?:配料(?:表)?|食品添加剂)[：:\s]*\[([^\]]+)\]",
    r"(?:配料(?:表)?|食品添加剂)[：:\s]*[（(]([^）)]+)[）)]",
    r"(?:配料(?:表)?|食品添加剂)[：:\s]*([^。；\n]{5,300})",
    r"(?:配料(?:表)?)[：:\s]*([^。；\n]{5,300})",
]

NOISE_PATTERNS = [
    r"^\d+$",
    r"^SC\d+",
    r"许可证",
    r"生产商",
    r"地址",
    r"产地",
    r"商标",
    r"授权",
    r"^http",
]

NOTE_CATEGORY_KEYWORDS = {
    "防腐剂": "防腐剂",
    "甜味剂": "甜味剂",
    "色素": "色素",
    "增稠剂": "增稠剂",
    "乳化剂": "乳化剂",
    "抗氧化剂": "抗氧化剂",
}

ALLERGEN_NOTE_KEYWORDS = {
    "花生": "花生",
    "坚果": "坚果",
    "麸质": "含麸质谷物",
    "小麦": "含麸质谷物",
    "牛奶": "乳",
    "乳制品": "乳",
    "乳糖": "乳",
    "大豆": "大豆",
    "虾": "甲壳纲类动物",
    "蟹": "甲壳纲类动物",
    "鱼": "鱼类",
    "鸡蛋": "蛋类",
    "蛋": "蛋类",
    "芝麻": "芝麻",
}


class AnalysisService:
    def __init__(self):
        self.store = get_ingredient_store()
        (
            self.ingredient_db,
            self.alias_map,
            self.ocr_correction_map,
            self.matchable_names,
            self.matcher,
        ) = (
            self.store.ingredient_db,
            self.store.alias_map,
            self.store.ocr_correction_map,
            self.store.matchable_names,
            self.store.matcher,
        )
        register_jieba_dictionary(self.ingredient_db, self.alias_map)

    async def analyze_ingredients(
        self,
        text: str,
        user_notes: str = None,
        user_profile: UserProfile = None,
        user_id: str = None,
        source_type: str = "text",
        save_history: bool = True,
    ) -> AnalysisResult:
        profile = self._merge_user_profile(user_profile, user_notes)
        processed_text = self._preprocess_text(text, user_notes)
        ingredient_section = self._extract_ingredient_section(processed_text)
        matched, unknown = self._extract_ingredients(ingredient_section, processed_text)
        result = self._analyze_safety(matched, unknown, processed_text, ingredient_section, profile)

        if save_history and processed_text.strip():
            self.store.save_scan(
                user_id=user_id,
                source_type=source_type,
                raw_text=processed_text,
                ingredient_section=ingredient_section,
                matched=result.matched_ingredients,
                unknown=result.unknown_ingredients,
                confidence=result.confidence,
            )
        return result

    def _merge_user_profile(
        self, user_profile: Optional[UserProfile], user_notes: Optional[str]
    ) -> UserProfile:
        profile = user_profile or UserProfile()
        if not user_notes:
            return profile

        watch_categories = list(profile.watch_categories)
        avoid_categories = list(profile.avoid_categories)
        conditions = list(profile.conditions)
        allergens = list(profile.allergens)

        for keyword, category in NOTE_CATEGORY_KEYWORDS.items():
            if keyword in user_notes and category not in watch_categories:
                watch_categories.append(category)

        for keyword, allergen in ALLERGEN_NOTE_KEYWORDS.items():
            if keyword in user_notes and allergen not in allergens:
                allergens.append(allergen)

        if any(k in user_notes for k in ("过敏", "敏感")):
            for cat in ("防腐剂", "色素", "甜味剂"):
                if cat not in watch_categories:
                    watch_categories.append(cat)

        if any(k in user_notes for k in ("儿童", "孩子", "宝宝")):
            if "儿童慎用" not in conditions:
                conditions.append("儿童慎用")

        if "苯丙酮尿症" in user_notes or "PKU" in user_notes.upper():
            if "苯丙酮尿症" not in conditions:
                conditions.append("苯丙酮尿症")

        return UserProfile(
            conditions=conditions,
            watch_categories=watch_categories,
            watch_ingredients=list(profile.watch_ingredients),
            avoid_categories=avoid_categories,
            allergens=allergens,
        )

    def _preprocess_text(self, text: str, user_notes: str) -> str:
        if user_notes:
            text = f"{text} {user_notes}"
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _extract_ingredient_section(self, text: str) -> str:
        for pattern in INGREDIENT_SECTION_PATTERNS:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return text

    def _split_candidates(self, section: str) -> List[str]:
        parts = re.split(r"[、，,；;]", section)
        return [p.strip() for p in parts if p.strip()]

    def _clean_candidate(self, raw: str) -> str:
        return re.sub(r"\s+", "", raw.strip())

    def _is_noise(self, text: str) -> bool:
        if self._to_canonical(text):
            return False
        if len(text) < 2:
            return True
        for pattern in NOISE_PATTERNS:
            if re.search(pattern, text):
                return True
        return False

    def _to_canonical(self, name: str) -> Optional[str]:
        if name in self.ingredient_db:
            return name
        if name in self.alias_map:
            return self.alias_map[name]
        if name in self.ocr_correction_map:
            return self.ocr_correction_map[name]
        return None

    def _resolve_ingredient(self, raw: str) -> Optional[str]:
        cleaned = self._clean_candidate(raw)
        if not cleaned:
            return None

        canonical = self._to_canonical(cleaned)
        if canonical:
            return canonical

        if self._is_noise(cleaned):
            return None

        base = re.sub(r"[（(][^）)]*[）)]", "", cleaned).strip()
        if base and base != cleaned:
            canonical = self._to_canonical(base)
            if canonical:
                return canonical
        return None

    def _decompose(self, text: str) -> Tuple[List[str], str]:
        patterns, remainder = self.matcher.decompose(text)
        matched = []
        for pattern in patterns:
            canonical = self._to_canonical(pattern)
            if canonical and canonical not in matched:
                matched.append(canonical)
        return matched, remainder

    def _extract_ingredients(
        self, ingredient_section: str, full_text: str
    ) -> Tuple[List[str], List[str]]:
        matched: List[str] = []
        unknown: List[str] = []
        candidates = self._split_candidates(ingredient_section)

        for candidate in candidates:
            canonical = self._resolve_ingredient(candidate)
            if canonical:
                if canonical not in matched:
                    matched.append(canonical)
                continue

            if len(candidate) > 4:
                decomposed, remainder = self._decompose(self._clean_candidate(candidate))
                if decomposed:
                    for name in decomposed:
                        if name not in matched:
                            matched.append(name)
                    if remainder and len(remainder) >= 2:
                        unknown.append(remainder)
                    continue

            cleaned = self._clean_candidate(candidate)
            if cleaned and not self._is_noise(cleaned):
                unknown.append(cleaned)

        if not matched:
            decomposed, remainder = self._decompose(self._clean_candidate(ingredient_section))
            matched.extend(decomposed)
            if remainder and len(remainder) >= 2 and remainder not in unknown:
                unknown.append(remainder)

        return matched, unknown

    def _analyze_safety(
        self,
        ingredient_names: List[str],
        unknown_ingredients: List[str],
        processed_text: str,
        ingredient_section: str,
        profile: UserProfile,
    ) -> AnalysisResult:
        matched_ingredients: List[Ingredient] = []
        warnings: List[str] = []
        safety_scores: List[int] = []

        for ing_name in ingredient_names:
            if ing_name not in self.ingredient_db:
                continue
            ingredient = self.ingredient_db[ing_name]
            matched_ingredients.append(ingredient)
            safety_scores.append(self._get_safety_score(ingredient.safety_level))

            if ingredient.safety_level == SafetyLevel.DANGEROUS:
                warnings.append(f"⚠️ 警告: {ing_name} - {ingredient.description}，存在健康风险")
            elif ingredient.safety_level == SafetyLevel.WARNING:
                warnings.append(f"⚠️ 注意: {ing_name} - {ingredient.description}")
                if ingredient.potential_risks:
                    warnings.append(f"   潜在风险: {', '.join(ingredient.potential_risks)}")
            elif ingredient.safety_level == SafetyLevel.CAUTION:
                if ingredient.ingredient_type != IngredientType.BASE:
                    warnings.append(
                        f"ℹ️ 提示: {ing_name} - {ingredient.description}，建议适量摄入"
                    )
                    if ingredient.potential_risks:
                        warnings.append(f"   注意事项: {', '.join(ingredient.potential_risks)}")

        allergen_hits = self._detect_allergens(matched_ingredients, profile)
        user_highlights = self._get_user_highlights(matched_ingredients, profile, allergen_hits)
        personal_warnings = self._generate_personal_warnings(user_highlights, profile, allergen_hits)
        warnings = personal_warnings + [w for w in warnings if w not in personal_warnings]

        overall_safety = self._calculate_overall_safety(safety_scores, warnings)
        recommendations = self._generate_recommendations(
            matched_ingredients, warnings, user_highlights, profile
        )
        by_category = self._group_by_category(matched_ingredients)
        by_type = self._group_by_type(matched_ingredients, unknown_ingredients, user_highlights, allergen_hits)
        needs_attention = [
            ing
            for ing in matched_ingredients
            if ing.safety_level in (SafetyLevel.WARNING, SafetyLevel.DANGEROUS)
            or ing in allergen_hits
        ]
        confidence = self._calculate_confidence(
            matched_ingredients, unknown_ingredients, ingredient_section, processed_text
        )
        total_candidates = len(matched_ingredients) + len(unknown_ingredients)
        coverage = {
            "matched_count": len(matched_ingredients),
            "unknown_count": len(unknown_ingredients),
            "total_candidates": total_candidates,
            "coverage_rate": round(len(matched_ingredients) / total_candidates, 2) if total_candidates else 0.0,
            "database_size": len(self.ingredient_db),
        }

        suggestion_map = suggest_ingredients(
            unknown_ingredients,
            self.ingredient_db.keys(),
            self.alias_map,
        )
        ingredient_suggestions = [
            IngredientSuggestion(unknown=k, candidates=v)
            for k, v in suggestion_map.items()
        ]
        if ingredient_suggestions:
            for item in ingredient_suggestions[:3]:
                names = "、".join(item.candidates)
                warnings.append(f"💡 「{item.unknown}」未收录，您是否指: {names}？")

        food_item = FoodItem(
            name="识别食品",
            ingredients=matched_ingredients,
            overall_safety=overall_safety,
            warnings=warnings,
            recommendations=recommendations,
        )

        return AnalysisResult(
            food_item=food_item,
            confidence=confidence,
            processed_text=processed_text,
            ingredient_section=ingredient_section,
            matched_ingredients=[ing.name for ing in matched_ingredients],
            unknown_ingredients=unknown_ingredients,
            by_category=by_category,
            by_type=by_type,
            user_highlights=user_highlights,
            needs_attention=needs_attention,
            personal_warnings=personal_warnings,
            coverage=coverage,
            ingredient_suggestions=ingredient_suggestions,
        )

    def _detect_allergens(
        self, ingredients: List[Ingredient], profile: UserProfile
    ) -> List[Ingredient]:
        hits: List[Ingredient] = []
        user_allergens = set(profile.allergens)
        for ing in ingredients:
            if ing.ingredient_type == IngredientType.ALLERGEN:
                hits.append(ing)
                continue
            if user_allergens and user_allergens.intersection(set(ing.tags)):
                hits.append(ing)
                continue
            for allergen in user_allergens:
                if allergen in ing.name or allergen in ing.description:
                    hits.append(ing)
                    break
        seen = set()
        result = []
        for ing in hits:
            if ing.name not in seen:
                seen.add(ing.name)
                result.append(ing)
        return result

    def _group_by_type(
        self,
        ingredients: List[Ingredient],
        unknown: List[str],
        user_focus: List[Ingredient],
        allergen_hits: List[Ingredient],
    ) -> LayeredIngredients:
        focus_names = {i.name for i in user_focus} | {i.name for i in allergen_hits}
        layered = LayeredIngredients(unknown=unknown)
        layered.user_focus = [i for i in ingredients if i.name in focus_names]
        layered.allergens = [
            i for i in ingredients if i.ingredient_type == IngredientType.ALLERGEN or i in allergen_hits
        ]
        layered.additives = [i for i in ingredients if i.ingredient_type == IngredientType.ADDITIVE]
        layered.base_ingredients = [i for i in ingredients if i.ingredient_type == IngredientType.BASE]
        layered.composites = [i for i in ingredients if i.ingredient_type == IngredientType.COMPOSITE]
        return layered

    def _get_user_highlights(
        self,
        ingredients: List[Ingredient],
        profile: UserProfile,
        allergen_hits: List[Ingredient],
    ) -> List[Ingredient]:
        if not any(
            [
                profile.conditions,
                profile.watch_categories,
                profile.watch_ingredients,
                profile.avoid_categories,
                profile.allergens,
            ]
        ) and not allergen_hits:
            return []

        highlights: List[Ingredient] = list(allergen_hits)
        for ing in ingredients:
            if ing in highlights:
                continue
            if ing.name in profile.watch_ingredients:
                highlights.append(ing)
                continue
            if ing.category in profile.watch_categories:
                highlights.append(ing)
                continue
            if ing.category in profile.avoid_categories:
                highlights.append(ing)
                continue
            if profile.allergens and set(profile.allergens).intersection(set(ing.tags)):
                highlights.append(ing)
                continue
            if any(cond in ing.tags or cond in ing.potential_risks for cond in profile.conditions):
                highlights.append(ing)
                continue
            for cond in profile.conditions:
                if cond in ing.tags:
                    highlights.append(ing)
                    break

        seen = set()
        result = []
        for ing in highlights:
            if ing.name not in seen:
                seen.add(ing.name)
                result.append(ing)
        return result

    def _generate_personal_warnings(
        self,
        highlights: List[Ingredient],
        profile: UserProfile,
        allergen_hits: List[Ingredient],
    ) -> List[str]:
        warnings: List[str] = []
        if allergen_hits:
            names = "、".join(i.name for i in allergen_hits)
            warnings.append(f"⚠️ 过敏原提示: 检测到与过敏相关的成分 ({names})")
        if not highlights:
            return warnings

        warnings.append("🔔 您关注的成分:")
        for ing in highlights:
            reason_parts = []
            if ing.name in profile.watch_ingredients:
                reason_parts.append("在您的关注列表中")
            if ing.category in profile.watch_categories:
                reason_parts.append(f"属于您关注的{ing.category}类")
            if ing.category in profile.avoid_categories:
                reason_parts.append(f"属于您想避开的{ing.category}类")
            if profile.allergens and set(profile.allergens).intersection(set(ing.tags)):
                reason_parts.append("匹配您的过敏原设置")
            for cond in profile.conditions:
                if cond in ing.tags or any(cond in r for r in ing.potential_risks):
                    reason_parts.append(f"与您的状况({cond})相关")
            reason = "，".join(reason_parts) if reason_parts else "匹配您的关注设置"
            risk_hint = f"；注意: {', '.join(ing.potential_risks)}" if ing.potential_risks else ""
            warnings.append(f"   • {ing.name}（{ing.category}）- {reason}{risk_hint}")
        return warnings

    def _group_by_category(self, ingredients: List[Ingredient]) -> Dict[str, List[Ingredient]]:
        grouped: Dict[str, List[Ingredient]] = {}
        for ing in ingredients:
            grouped.setdefault(ing.category, []).append(ing)
        return grouped

    def _calculate_confidence(
        self,
        matched: List[Ingredient],
        unknown: List[str],
        ingredient_section: str,
        full_text: str,
    ) -> float:
        base = 0.3
        if matched:
            base = min(0.85, 0.45 + len(matched) * 0.08)
        if ingredient_section != full_text:
            base = min(0.95, base + 0.1)
        if unknown:
            base = max(0.2, base - len(unknown) * 0.03)
        return round(base, 2)

    def _get_safety_score(self, safety_level: SafetyLevel) -> int:
        scores = {
            SafetyLevel.SAFE: 90,
            SafetyLevel.CAUTION: 70,
            SafetyLevel.WARNING: 40,
            SafetyLevel.DANGEROUS: 10,
        }
        return scores.get(safety_level, 50)

    def _calculate_overall_safety(self, scores: List[int], warnings: List[str]) -> SafetyLevel:
        if not scores:
            return SafetyLevel.SAFE
        avg_score = sum(scores) / len(scores)
        if avg_score >= 80:
            return SafetyLevel.SAFE
        if avg_score >= 60:
            return SafetyLevel.CAUTION
        if avg_score >= 30:
            return SafetyLevel.WARNING
        return SafetyLevel.DANGEROUS

    def _generate_recommendations(
        self,
        ingredients: List[Ingredient],
        warnings: List[str],
        highlights: List[Ingredient],
        profile: UserProfile,
    ) -> List[str]:
        recommendations: List[str] = []
        if highlights:
            names = "、".join(ing.name for ing in highlights)
            recommendations.append(f"该产品含有您关注的成分: {names}，请结合个人情况谨慎选择")
        if profile.allergens:
            recommendations.append("请核对您的过敏原设置，不确定时避免食用")
        if not warnings:
            recommendations.append("该食品成分相对安全，可以适量食用")
        else:
            recommendations.append("建议适量食用，注意成分表中的警告项")
        for ingredient in ingredients:
            if ingredient.safety_level in (SafetyLevel.WARNING, SafetyLevel.DANGEROUS):
                recommendations.append(f"减少含 {ingredient.name} 的食品摄入")
        if profile.conditions and highlights:
            recommendations.append("如有特殊健康状况，建议咨询医生或营养师")
        if len([w for w in warnings if w.startswith("⚠️") or w.startswith("ℹ️")]) > 2:
            recommendations.append("该食品含有多种需要注意的成分，建议选择更健康的替代品")
        return recommendations
