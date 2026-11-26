# IngredientLens — Food Label OCR & Additive Risk Analysis API

> A production FastAPI service that reads food-ingredient labels with OCR and turns messy, real-world text into structured, personalized safety analysis. Built end-to-end by one engineer.

`FastAPI` · `Python` · `SQLite` · `Aho-Corasick` · `OCR Integration` · `Pydantic` · `pytest`

---

## The problem

Food labels are photographed in the wild: low light, curved packaging, blurred text. OCR output is noisy — characters are misread (`非甲酸钠` for `苯甲酸钠`), ingredient names run together without separators, and one product can contain dozens of additives. A naive keyword search produces both false positives (`柠檬酸` matching inside `柠檬酸钠`) and silent misses.

This service solves that end to end: OCR → text cleanup → ingredient extraction → per-user risk analysis → structured JSON, with a feedback loop that lets an admin correct OCR errors so the same mistake never recurs.

## What it does

- **Dual OCR backends** behind one interface (`ali` official SDK / `tysbgpu` marketplace AppCode), selected by config. Sync SDK work is offloaded to a thread executor so the async API stays responsive. Returns text **plus confidence metadata** (`avg_confidence`, `low_confidence_words`) so downstream code can decide when to distrust a read.
- **Ingredient extraction from noisy text.** A hand-written **Aho-Corasick multi-pattern matcher** (trie + failure links, greedy longest non-overlapping match) scans the whole label in one pass — `配料：柠檬酸钠咖啡因` correctly yields two ingredients, not a false `柠檬酸`.
- **A 560+ entry knowledge base** with aliases, E-numbers, OCR correction rules, safety levels, risk notes and tags, stored in YAML/CSV and synced into SQLite on startup, then loaded into memory with the matcher rebuilt on every admin edit.
- **Unknown-ingredient handling.** Unrecognized tokens are collected per user and ranked by frequency; an admin reviews the top candidates, and `SequenceMatcher`-based fuzzy suggestions propose likely canonical names. Confirmed mappings become `ocr_corrections` — the system learns from its own failures.
- **Personalized risk analysis.** A user profile (allergens, watched/avoided categories, conditions such as PKU or "children") drives layered output: allergens, additives, base ingredients, composites, user-focus items, plus warnings, coverage rate and a confidence score.
- **Admin CMS** with token auth (`X-Admin-Token`): ingredient CRUD, search/pagination, OCR-correction management, unknown-candidate review, YAML/CSV re-import and YAML export.
- **Production hygiene:** CORS allow-list, structured HTTP errors, temp-file cleanup in `finally`, env-based secrets with `.env.example`, health/index endpoints, and a 3-file pytest suite (362 lines) including a regression case built from a real noisy OCR capture.

## Architecture

```
Client (App / Web)
      │  POST /api/analyze  (image_url)  or  /api/analyze-text (text)
      ▼
FastAPI  ── validation, CORS, auth on admin routes
      │
      ├─ OCRService ── AliOCR (async SDK)  |  TYSBGPU OCR (thread executor)
      │                    └── text + confidence metadata
      │
      ▼
AnalysisService
      ├─ ingredient-section extraction (regex, noise filtering)
      ├─ IngredientMatcher (Aho-Corasick, one-pass longest match)
      ├─ alias / E-number / OCR-correction resolution
      ├─ fuzzy suggestions for unknowns (SequenceMatcher)
      └─ safety scoring + personalized profile rules
      │
      ▼
IngredientStore (SQLite)  ←→  YAML/CSV seed  ←→  Admin CMS (token auth)
      │
      └─ scan history + ocr_corrections → feedback loop
```

## Example

```bash
curl -X POST http://localhost:8000/api/analyze-text \
  -F 'text_input=配料：水、小麦粉、苯甲酸钠、阿斯巴甜(含苯丙氨酸)、安赛蜜' \
  -F 'user_profile={"allergens":["花生"],"watch_categories":["甜味剂"],"conditions":["苯丙酮尿症"]}'
```

Response (abridged):

```json
{
  "code": 1,
  "message": "success",
  "data": {
    "analysis_result": {
      "confidence": 0.85,
      "coverage": {"matched_count": 5, "unknown_count": 0, "coverage_rate": 1.0},
      "matched_ingredients": ["水", "小麦粉", "苯甲酸钠", "阿斯巴甜", "安赛蜜"],
      "needs_attention": ["苯甲酸钠", "阿斯巴甜", "安赛蜜"],
      "personal_warnings": ["Allergen alert ...", "Ingredients you follow ..."],
      "by_type": {"additives": [], "base_ingredients": [], "user_focus": []},
      "ingredient_suggestions": []
    }
  }
}
```

For a **real production response on a noisy photographed label** — 46 ingredient candidates, 33 matched, 13 unknowns surfaced, 5 fuzzy suggestions, confidence 0.56 — see [`examples/API_EXAMPLE.md`](examples/API_EXAMPLE.md) and the [full JSON](examples/response-full.json). That example is the more interesting one: it shows how the service behaves when OCR is dirty and the knowledge base does not know every token.

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env          # add OCR credentials (or use text-only endpoint)
python scripts/build_seed_data.py
python scripts/init_db.py --force
python run.py                 # http://localhost:8000  ·  docs at /docs
pytest tests/ -v
```

Two endpoints work **without any cloud credentials**: `POST /api/analyze-text` and `GET /api/health` — so the core analysis pipeline can be reviewed offline.

## Tech notes / tradeoffs

- **Why Aho-Corasick instead of regex or repeated `str.find`?** One pass over the label regardless of dictionary size, and deterministic longest-match resolution avoids `柠檬酸` / `柠檬酸钠` false positives. The matcher is ~100 lines with no external dependency.
- **Why SQLite + in-memory load?** The dictionary is read-heavy and small; rebuilding the trie on admin edits gives instant consistency without a query per token.
- **Why confidence metadata from OCR?** Low-confidence words can be routed to the correction queue instead of silently producing a wrong risk verdict — critical in a health-adjacent product.
- **Honest scope:** this is a deterministic rules + fuzzy-matching pipeline, **not** an LLM application. The design deliberately avoids a black box for safety decisions; every warning is traceable to a rule and a knowledge-base entry.

---

*Built end-to-end by one engineer: API design, matching engine, OCR integration, data pipeline, admin tools and regression tests — iterated against real photographed labels.*
