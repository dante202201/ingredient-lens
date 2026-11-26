"""初始化数据库并从 YAML/CSV 导入成分数据"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from models.database import DB_PATH, init_db, ingredient_count
from services.ingredient_store import IngredientStore


def main(force: bool = False) -> None:
    if force and DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
    store = IngredientStore()
    if force:
        store.sync_from_files()
        store.reload()
    count = len(store.ingredient_db)
    print(f"Database ready: {DB_PATH}")
    print(f"Ingredients loaded: {count}")
    print(f"Aliases: {len(store.alias_map)}")
    print(f"OCR corrections: {len(store.ocr_correction_map)}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force=force)
