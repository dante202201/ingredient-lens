"""未知成分模糊匹配建议"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Tuple


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def suggest_ingredients(
    unknown_items: Iterable[str],
    canonical_names: Iterable[str],
    alias_to_canonical: Dict[str, str],
    *,
    min_score: float = 0.72,
    max_suggestions: int = 3,
) -> Dict[str, List[str]]:
    """为未收录成分推荐可能的标准名称"""
    patterns: Dict[str, str] = {}
    for name in canonical_names:
        patterns[name] = name
    for alias, canonical in alias_to_canonical.items():
        patterns[alias] = canonical

    suggestions: Dict[str, List[str]] = {}
    for raw in unknown_items:
        text = raw.strip()
        if len(text) < 2:
            continue

        scored: List[Tuple[float, str]] = []
        for pattern, canonical in patterns.items():
            score = _similarity(text, pattern)
            if score >= min_score:
                scored.append((score, canonical))

        if not scored:
            continue

        scored.sort(key=lambda x: (-x[0], x[1]))
        unique: List[str] = []
        for _, name in scored:
            if name not in unique:
                unique.append(name)
            if len(unique) >= max_suggestions:
                break
        if unique:
            suggestions[text] = unique

    return suggestions
