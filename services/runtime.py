"""运行时服务引用，避免循环导入"""

from typing import Optional

_analysis_service = None


def set_analysis_service(service) -> None:
    global _analysis_service
    _analysis_service = service


def sync_analysis_from_store(store) -> None:
    if _analysis_service is None:
        return
    _analysis_service.store = store
    _analysis_service.ingredient_db = store.ingredient_db
    _analysis_service.alias_map = store.alias_map
    _analysis_service.ocr_correction_map = store.ocr_correction_map
    _analysis_service.matchable_names = store.matchable_names
    _analysis_service.matcher = store.matcher
