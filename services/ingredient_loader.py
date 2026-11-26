"""成分库加载（兼容层，实际数据来自 SQLite）"""

import jieba

from services.ingredient_store import IngredientStore, get_ingredient_store


def load_ingredient_database(store: IngredientStore = None):
    """返回 (ingredient_db, alias_map, ocr_correction_map, matchable_names, matcher)"""
    s = store or get_ingredient_store()
    return (
        s.ingredient_db,
        s.alias_map,
        s.ocr_correction_map,
        s.matchable_names,
        s.matcher,
    )


def register_jieba_dictionary(ingredient_db, alias_map) -> None:
    for name in ingredient_db:
        jieba.add_word(name, freq=2000, tag="n")
    for alias in alias_map:
        jieba.add_word(alias, freq=2000, tag="n")
