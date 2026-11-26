from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


class SafetyLevel(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    WARNING = "warning"
    DANGEROUS = "dangerous"


class IngredientType(str, Enum):
    BASE = "base"           # 基础原料
    ADDITIVE = "additive"   # 食品添加剂
    ALLERGEN = "allergen"   # 过敏原相关
    COMPOSITE = "composite" # 复合/模糊配料


class Ingredient(BaseModel):
    name: str
    ingredient_type: IngredientType = IngredientType.ADDITIVE
    category: str
    safety_level: SafetyLevel
    description: str
    potential_risks: List[str]
    safe_limits: Optional[str]
    common_products: List[str]
    e_number: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    conditions: List[str] = Field(default_factory=list)
    watch_categories: List[str] = Field(default_factory=list)
    watch_ingredients: List[str] = Field(default_factory=list)
    avoid_categories: List[str] = Field(default_factory=list)
    allergens: List[str] = Field(default_factory=list)  # 如：花生、乳、麸质


class LayeredIngredients(BaseModel):
    """分层识别结果"""
    user_focus: List[Ingredient] = Field(default_factory=list)
    allergens: List[Ingredient] = Field(default_factory=list)
    additives: List[Ingredient] = Field(default_factory=list)
    base_ingredients: List[Ingredient] = Field(default_factory=list)
    composites: List[Ingredient] = Field(default_factory=list)
    unknown: List[str] = Field(default_factory=list)


class FoodItem(BaseModel):
    name: str
    ingredients: List[Ingredient]
    overall_safety: SafetyLevel
    warnings: List[str]
    recommendations: List[str]


class IngredientSuggestion(BaseModel):
    unknown: str
    candidates: List[str]


class AnalysisResult(BaseModel):
    food_item: FoodItem
    confidence: float
    processed_text: str
    ingredient_section: str = ""
    matched_ingredients: List[str]
    unknown_ingredients: List[str]
    by_category: Dict[str, List[Ingredient]] = Field(default_factory=dict)
    by_type: LayeredIngredients = Field(default_factory=LayeredIngredients)
    user_highlights: List[Ingredient] = Field(default_factory=list)
    needs_attention: List[Ingredient] = Field(default_factory=list)
    personal_warnings: List[str] = Field(default_factory=list)
    coverage: Dict[str, Any] = Field(default_factory=dict)
    ingredient_suggestions: List[IngredientSuggestion] = Field(default_factory=list)


class AnalysisRequest(BaseModel):
    image_url: Optional[str] = None
    text_input: Optional[str] = None
    user_notes: Optional[str] = None
    user_profile: Optional[UserProfile] = None
    user_id: Optional[str] = None


class ImageAnalysisRequest(BaseModel):
    image_url: str
    user_notes: Optional[str] = None
    user_profile: Optional[UserProfile] = None
    user_id: Optional[str] = None


class TextAnalysisRequest(BaseModel):
    text_input: str
    user_notes: Optional[str] = None
    user_profile: Optional[UserProfile] = None
    user_id: Optional[str] = None


class ScanHistoryItem(BaseModel):
    id: int
    user_id: Optional[str]
    source_type: str
    matched_count: int
    unknown_count: int
    matched_ingredients: List[str]
    unknown_ingredients: List[str]
    created_at: str


class OcrCorrectionRequest(BaseModel):
    ocr_text: str
    canonical_name: str


class IngredientUpsert(BaseModel):
    name: str
    ingredient_type: IngredientType = IngredientType.ADDITIVE
    category: str
    safety_level: SafetyLevel = SafetyLevel.SAFE
    description: str = ""
    potential_risks: List[str] = Field(default_factory=list)
    safe_limits: Optional[str] = None
    common_products: List[str] = Field(default_factory=list)
    e_number: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    ocr_corrections: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class IngredientDetail(Ingredient):
    ocr_corrections: List[str] = Field(default_factory=list)


class UnknownCandidate(BaseModel):
    text: str
    hit_count: int


class AdminStats(BaseModel):
    total_ingredients: int
    total_aliases: int
    total_ocr_corrections: int
    total_scans: int
    by_type: Dict[str, int]
    top_unknown: List[UnknownCandidate]


class AnalysisResponse(BaseModel):
    code: int
    message: str
    data: Dict[str, Any]
