"""成分数据存储：YAML/CSV 导入 SQLite，启动时加载到内存"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from models.database import DB_PATH, get_connection, init_db, ingredient_count
from models.schemas import Ingredient, IngredientType, SafetyLevel
from services.matcher import IngredientMatcher

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INGREDIENTS_DIR = DATA_DIR / "ingredients"
SEED_CSV = DATA_DIR / "seed" / "ingredients_bulk.csv"
LEGACY_YAML = DATA_DIR / "ingredients.yaml"


class IngredientStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        init_db(db_path)
        if ingredient_count(db_path) == 0:
            self.sync_from_files()
        (
            self.ingredient_db,
            self.alias_map,
            self.ocr_correction_map,
            self.matchable_names,
            self.matcher,
        ) = self._load_from_db()

    def sync_from_files(self) -> int:
        """从 YAML 目录 + CSV 种子文件导入 SQLite"""
        rows = self._collect_file_rows()
        return self._upsert_rows(rows)

    def reload(self) -> None:
        (
            self.ingredient_db,
            self.alias_map,
            self.ocr_correction_map,
            self.matchable_names,
            self.matcher,
        ) = self._load_from_db()

    def _collect_file_rows(self) -> List[dict]:
        rows: List[dict] = []
        sources: List[Path] = []

        if INGREDIENTS_DIR.exists():
            sources.extend(sorted(INGREDIENTS_DIR.glob("*.yaml")))
        if LEGACY_YAML.exists() and not (INGREDIENTS_DIR / "additives.yaml").exists():
            sources.append(LEGACY_YAML)
        if SEED_CSV.exists():
            rows.extend(self._load_csv(SEED_CSV))

        for path in sources:
            rows.extend(self._load_yaml(path))
        return self._dedupe_rows(rows)

    @staticmethod
    def _dedupe_rows(rows: List[dict]) -> List[dict]:
        seen = set()
        result = []
        for row in rows:
            name = row["name"]
            if name in seen:
                continue
            seen.add(name)
            result.append(row)
        return result

    def _load_yaml(self, path: Path) -> List[dict]:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        default_type = raw.get("default_type", "additive")
        rows = []
        for name, data in (raw.get("ingredients") or {}).items():
            rows.append(self._normalize_row(name, data, default_type))
        return rows

    def _load_csv(self, path: Path) -> List[dict]:
        rows = []
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for item in reader:
                name = (item.get("name") or "").strip()
                if not name:
                    continue
                aliases = [a.strip() for a in (item.get("aliases") or "").split("|") if a.strip()]
                ocr = [a.strip() for a in (item.get("ocr_corrections") or "").split("|") if a.strip()]
                tags = [a.strip() for a in (item.get("tags") or "").split("|") if a.strip()]
                products = [a.strip() for a in (item.get("common_products") or "").split("|") if a.strip()]
                risks = [a.strip() for a in (item.get("potential_risks") or "").split("|") if a.strip()]
                rows.append(
                    {
                        "name": name,
                        "ingredient_type": item.get("ingredient_type") or "additive",
                        "category": item.get("category") or "其他",
                        "safety_level": item.get("safety_level") or "safe",
                        "description": item.get("description") or name,
                        "safe_limits": item.get("safe_limits") or None,
                        "e_number": item.get("e_number") or None,
                        "potential_risks": risks,
                        "common_products": products,
                        "tags": tags,
                        "aliases": aliases,
                        "ocr_corrections": ocr,
                    }
                )
        return rows

    @staticmethod
    def _normalize_row(name: str, data: dict, default_type: str) -> dict:
        return {
            "name": name,
            "ingredient_type": data.get("ingredient_type") or default_type,
            "category": data["category"],
            "safety_level": data["safety_level"],
            "description": data.get("description") or name,
            "safe_limits": data.get("safe_limits"),
            "e_number": data.get("e_number"),
            "potential_risks": data.get("potential_risks") or [],
            "common_products": data.get("common_products") or [],
            "tags": data.get("tags") or [],
            "aliases": data.get("aliases") or [],
            "ocr_corrections": data.get("ocr_corrections") or [],
        }

    def _upsert_rows(self, rows: List[dict]) -> int:
        conn = get_connection(self.db_path)
        count = 0
        try:
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO ingredients (
                        name, ingredient_type, category, safety_level, description,
                        safe_limits, e_number, potential_risks, common_products, tags
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        ingredient_type=excluded.ingredient_type,
                        category=excluded.category,
                        safety_level=excluded.safety_level,
                        description=excluded.description,
                        safe_limits=excluded.safe_limits,
                        e_number=excluded.e_number,
                        potential_risks=excluded.potential_risks,
                        common_products=excluded.common_products,
                        tags=excluded.tags,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        row["name"],
                        row["ingredient_type"],
                        row["category"],
                        row["safety_level"],
                        row["description"],
                        row.get("safe_limits"),
                        row.get("e_number"),
                        json.dumps(row.get("potential_risks") or [], ensure_ascii=False),
                        json.dumps(row.get("common_products") or [], ensure_ascii=False),
                        json.dumps(row.get("tags") or [], ensure_ascii=False),
                    ),
                )
                for alias in row.get("aliases") or []:
                    conn.execute(
                        """
                        INSERT INTO ingredient_aliases (ingredient_name, alias, alias_type)
                        VALUES (?, ?, 'alias')
                        ON CONFLICT(alias) DO UPDATE SET ingredient_name=excluded.ingredient_name
                        """,
                        (row["name"], alias),
                    )
                for correction in row.get("ocr_corrections") or []:
                    conn.execute(
                        """
                        INSERT INTO ingredient_aliases (ingredient_name, alias, alias_type)
                        VALUES (?, ?, 'ocr_correction')
                        ON CONFLICT(alias) DO UPDATE SET ingredient_name=excluded.ingredient_name
                        """,
                        (row["name"], correction),
                    )
                    conn.execute(
                        """
                        INSERT INTO ocr_corrections (ocr_text, canonical_name, source)
                        VALUES (?, ?, 'seed')
                        ON CONFLICT(ocr_text) DO UPDATE SET
                            canonical_name=excluded.canonical_name,
                            hit_count=hit_count+1
                        """,
                        (correction, row["name"]),
                    )
                if row.get("e_number"):
                    conn.execute(
                        """
                        INSERT INTO ingredient_aliases (ingredient_name, alias, alias_type)
                        VALUES (?, ?, 'e_number')
                        ON CONFLICT(alias) DO UPDATE SET ingredient_name=excluded.ingredient_name
                        """,
                        (row["name"], row["e_number"]),
                    )
                count += 1
            conn.commit()
        finally:
            conn.close()
        return count

    def _load_from_db(
        self,
    ) -> Tuple[Dict[str, Ingredient], Dict[str, str], Dict[str, str], List[str], IngredientMatcher]:
        conn = get_connection(self.db_path)
        ingredient_db: Dict[str, Ingredient] = {}
        alias_map: Dict[str, str] = {}
        ocr_correction_map: Dict[str, str] = {}
        matchable_names: List[str] = []

        try:
            rows = conn.execute("SELECT * FROM ingredients ORDER BY length(name) DESC").fetchall()
            for row in rows:
                ing = Ingredient(
                    name=row["name"],
                    ingredient_type=IngredientType(row["ingredient_type"]),
                    category=row["category"],
                    safety_level=SafetyLevel(row["safety_level"]),
                    description=row["description"],
                    potential_risks=json.loads(row["potential_risks"] or "[]"),
                    safe_limits=row["safe_limits"],
                    common_products=json.loads(row["common_products"] or "[]"),
                    e_number=row["e_number"],
                    tags=json.loads(row["tags"] or "[]"),
                )
                ingredient_db[row["name"]] = ing
                matchable_names.append(row["name"])

            alias_rows = conn.execute(
                "SELECT alias, ingredient_name, alias_type FROM ingredient_aliases"
            ).fetchall()
            for row in alias_rows:
                alias_map[row["alias"]] = row["ingredient_name"]
                matchable_names.append(row["alias"])
                if row["alias_type"] == "ocr_correction":
                    ocr_correction_map[row["alias"]] = row["ingredient_name"]

            ocr_rows = conn.execute(
                "SELECT ocr_text, canonical_name FROM ocr_corrections"
            ).fetchall()
            for row in ocr_rows:
                ocr_correction_map[row["ocr_text"]] = row["canonical_name"]
                matchable_names.append(row["ocr_text"])
        finally:
            conn.close()

        matchable_names = sorted(set(matchable_names), key=len, reverse=True)
        matcher = IngredientMatcher(matchable_names)
        return ingredient_db, alias_map, ocr_correction_map, matchable_names, matcher

    def save_scan(
        self,
        *,
        user_id: Optional[str],
        source_type: str,
        raw_text: str,
        ingredient_section: str,
        matched: List[str],
        unknown: List[str],
        confidence: float,
    ) -> int:
        conn = get_connection(self.db_path)
        try:
            cur = conn.execute(
                """
                INSERT INTO scan_history (
                    user_id, source_type, raw_text, ingredient_section,
                    matched_json, unknown_json, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    source_type,
                    raw_text,
                    ingredient_section,
                    json.dumps(matched, ensure_ascii=False),
                    json.dumps(unknown, ensure_ascii=False),
                    confidence,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def list_scans(self, user_id: Optional[str] = None, limit: int = 20) -> List[dict]:
        conn = get_connection(self.db_path)
        try:
            if user_id:
                rows = conn.execute(
                    """
                    SELECT * FROM scan_history
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM scan_history
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def add_ocr_correction(self, ocr_text: str, canonical_name: str, source: str = "manual") -> None:
        if canonical_name not in self.ingredient_db:
            raise ValueError(f"标准名称不存在: {canonical_name}")
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO ocr_corrections (ocr_text, canonical_name, source)
                VALUES (?, ?, ?)
                ON CONFLICT(ocr_text) DO UPDATE SET
                    canonical_name=excluded.canonical_name,
                    hit_count=hit_count+1,
                    source=excluded.source,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (ocr_text, canonical_name, source),
            )
            conn.execute(
                """
                INSERT INTO ingredient_aliases (ingredient_name, alias, alias_type)
                VALUES (?, ?, 'ocr_correction')
                ON CONFLICT(alias) DO UPDATE SET ingredient_name=excluded.ingredient_name
                """,
                (canonical_name, ocr_text),
            )
            conn.commit()
        finally:
            conn.close()
        self.reload()

    def learn_from_unknown(self, min_hits: int = 3) -> int:
        """从扫描历史中统计高频 unknown，供人工审核（返回候选数）"""
        return len(self.list_unknown_candidates(min_hits=min_hits, limit=1000))

    def search_ingredients(
        self,
        q: Optional[str] = None,
        ingredient_type: Optional[str] = None,
        category: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        conn = get_connection(self.db_path)
        try:
            clauses = ["1=1"]
            params: list = []
            if q:
                clauses.append(
                    "(name LIKE ? OR description LIKE ? OR category LIKE ? "
                    "OR name IN (SELECT ingredient_name FROM ingredient_aliases WHERE alias LIKE ?))"
                )
                like = f"%{q}%"
                params.extend([like, like, like, like])
            if ingredient_type:
                clauses.append("ingredient_type = ?")
                params.append(ingredient_type)
            if category:
                clauses.append("category = ?")
                params.append(category)

            where = " AND ".join(clauses)
            total = conn.execute(
                f"SELECT COUNT(*) AS c FROM ingredients WHERE {where}", params
            ).fetchone()["c"]
            offset = (page - 1) * page_size
            rows = conn.execute(
                f"""
                SELECT * FROM ingredients WHERE {where}
                ORDER BY name COLLATE NOCASE
                LIMIT ? OFFSET ?
                """,
                params + [page_size, offset],
            ).fetchall()
            items = [self._row_to_ingredient(row).model_dump() for row in rows]
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "pages": (total + page_size - 1) // page_size if page_size else 0,
            }
        finally:
            conn.close()

    def get_ingredient_detail(self, name: str) -> Optional[dict]:
        conn = get_connection(self.db_path)
        try:
            row = conn.execute("SELECT * FROM ingredients WHERE name = ?", (name,)).fetchone()
            if not row:
                return None
            ing = self._row_to_ingredient(row)
            alias_rows = conn.execute(
                """
                SELECT alias, alias_type FROM ingredient_aliases
                WHERE ingredient_name = ?
                """,
                (name,),
            ).fetchall()
            aliases = [r["alias"] for r in alias_rows if r["alias_type"] == "alias"]
            ocr = [r["alias"] for r in alias_rows if r["alias_type"] == "ocr_correction"]
            e_numbers = [r["alias"] for r in alias_rows if r["alias_type"] == "e_number"]
            if ing.e_number and ing.e_number not in e_numbers:
                e_numbers.append(ing.e_number)
            data = ing.model_dump()
            data["aliases"] = aliases
            data["ocr_corrections"] = ocr
            if e_numbers and not data.get("e_number"):
                data["e_number"] = e_numbers[0]
            return data
        finally:
            conn.close()

    def upsert_ingredient(self, row: dict) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute(
                "DELETE FROM ingredient_aliases WHERE ingredient_name = ?", (row["name"],)
            )
            conn.commit()
        finally:
            conn.close()
        self._upsert_rows([row])

    def delete_ingredient(self, name: str) -> bool:
        conn = get_connection(self.db_path)
        try:
            cur = conn.execute("DELETE FROM ingredients WHERE name = ?", (name,))
            conn.execute(
                "DELETE FROM ingredient_aliases WHERE ingredient_name = ?", (name,)
            )
            conn.execute(
                "DELETE FROM ocr_corrections WHERE canonical_name = ?", (name,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def rename_ingredient(self, old_name: str, new_name: str, row: dict) -> None:
        conn = get_connection(self.db_path)
        try:
            conn.execute("DELETE FROM ingredients WHERE name = ?", (old_name,))
            conn.execute(
                "DELETE FROM ingredient_aliases WHERE ingredient_name = ?", (old_name,)
            )
            conn.commit()
        finally:
            conn.close()
        self.upsert_ingredient(row)

    def get_stats(self) -> dict:
        conn = get_connection(self.db_path)
        try:
            total = conn.execute("SELECT COUNT(*) AS c FROM ingredients").fetchone()["c"]
            aliases = conn.execute("SELECT COUNT(*) AS c FROM ingredient_aliases").fetchone()["c"]
            ocr = conn.execute("SELECT COUNT(*) AS c FROM ocr_corrections").fetchone()["c"]
            scans = conn.execute("SELECT COUNT(*) AS c FROM scan_history").fetchone()["c"]
            type_rows = conn.execute(
                """
                SELECT ingredient_type, COUNT(*) AS c
                FROM ingredients GROUP BY ingredient_type
                """
            ).fetchall()
            by_type = {r["ingredient_type"]: r["c"] for r in type_rows}
        finally:
            conn.close()
        top_unknown = self.list_unknown_candidates(min_hits=2, limit=10)
        return {
            "total_ingredients": total,
            "total_aliases": aliases,
            "total_ocr_corrections": ocr,
            "total_scans": scans,
            "by_type": by_type,
            "top_unknown": top_unknown,
        }

    def list_unknown_candidates(self, min_hits: int = 2, limit: int = 50) -> List[dict]:
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                "SELECT unknown_json FROM scan_history ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
        finally:
            conn.close()

        freq: Dict[str, int] = {}
        for row in rows:
            for item in json.loads(row["unknown_json"] or "[]"):
                if len(item) >= 2:
                    freq[item] = freq.get(item, 0) + 1

        ranked = sorted(
            [{"text": k, "hit_count": v} for k, v in freq.items() if v >= min_hits],
            key=lambda x: (-x["hit_count"], x["text"]),
        )
        return ranked[:limit]

    def list_ocr_corrections(self, limit: int = 50) -> List[dict]:
        conn = get_connection(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT ocr_text, canonical_name, hit_count, source, updated_at
                FROM ocr_corrections
                ORDER BY hit_count DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @staticmethod
    def _row_to_ingredient(row) -> Ingredient:
        return Ingredient(
            name=row["name"],
            ingredient_type=IngredientType(row["ingredient_type"]),
            category=row["category"],
            safety_level=SafetyLevel(row["safety_level"]),
            description=row["description"],
            potential_risks=json.loads(row["potential_risks"] or "[]"),
            safe_limits=row["safe_limits"],
            common_products=json.loads(row["common_products"] or "[]"),
            e_number=row["e_number"],
            tags=json.loads(row["tags"] or "[]"),
        )

    def export_to_yaml_dict(self) -> dict:
        """导出成 YAML 结构，按 ingredient_type 分组"""
        conn = get_connection(self.db_path)
        grouped: Dict[str, dict] = {
            "base": {},
            "additive": {},
            "allergen": {},
            "composite": {},
        }
        try:
            rows = conn.execute("SELECT * FROM ingredients ORDER BY name COLLATE NOCASE").fetchall()
            for row in rows:
                detail = self.get_ingredient_detail(row["name"]) or {}
                ing_type = row["ingredient_type"]
                grouped.setdefault(ing_type, {})
                grouped[ing_type][row["name"]] = {
                    "ingredient_type": ing_type,
                    "category": row["category"],
                    "safety_level": row["safety_level"],
                    "description": row["description"],
                    "potential_risks": json.loads(row["potential_risks"] or "[]"),
                    "safe_limits": row["safe_limits"],
                    "common_products": json.loads(row["common_products"] or "[]"),
                    "e_number": row["e_number"],
                    "tags": json.loads(row["tags"] or "[]"),
                    "aliases": detail.get("aliases") or [],
                    "ocr_corrections": detail.get("ocr_corrections") or [],
                }
        finally:
            conn.close()
        return grouped


_store: Optional[IngredientStore] = None


def get_ingredient_store() -> IngredientStore:
    global _store
    if _store is None:
        _store = IngredientStore()
    return _store
