"""Aho-Corasick 多模式匹配，用于大规模成分名识别"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Set, Tuple


@dataclass
class _Node:
    children: Dict[str, int] = field(default_factory=dict)
    fail: int = 0
    outputs: List[str] = field(default_factory=list)


class IngredientMatcher:
    """多模式字符串匹配器，支持一次扫描提取所有命中模式"""

    def __init__(self, patterns: List[str]):
        self._nodes: List[_Node] = [_Node()]
        self._pattern_set: Set[str] = set()
        for pattern in sorted(set(patterns), key=len, reverse=True):
            if pattern:
                self._insert(pattern)
        self._build_fail_links()

    def _insert(self, pattern: str) -> None:
        if pattern in self._pattern_set:
            return
        self._pattern_set.add(pattern)
        node_idx = 0
        for ch in pattern:
            if ch not in self._nodes[node_idx].children:
                self._nodes[node_idx].children[ch] = len(self._nodes)
                self._nodes.append(_Node())
            node_idx = self._nodes[node_idx].children[ch]
        if pattern not in self._nodes[node_idx].outputs:
            self._nodes[node_idx].outputs.append(pattern)

    def _build_fail_links(self) -> None:
        queue: deque[int] = deque()
        for child_idx in self._nodes[0].children.values():
            self._nodes[child_idx].fail = 0
            queue.append(child_idx)

        while queue:
            current = queue.popleft()
            for ch, child_idx in self._nodes[current].children.items():
                queue.append(child_idx)
                fail_state = self._nodes[current].fail
                while fail_state and ch not in self._nodes[fail_state].children:
                    fail_state = self._nodes[fail_state].fail
                self._nodes[child_idx].fail = self._nodes[fail_state].children.get(ch, 0)
                self._nodes[child_idx].outputs.extend(
                    self._nodes[self._nodes[child_idx].fail].outputs
                )

    def find_all(self, text: str) -> List[Tuple[int, str]]:
        """返回 (起始位置, 匹配模式) 列表，按位置排序"""
        if not text:
            return []
        hits: List[Tuple[int, str]] = []
        state = 0
        for i, ch in enumerate(text):
            while state and ch not in self._nodes[state].children:
                state = self._nodes[state].fail
            state = self._nodes[state].children.get(ch, 0)
            for pattern in self._nodes[state].outputs:
                hits.append((i - len(pattern) + 1, pattern))
        hits.sort(key=lambda x: (x[0], -len(x[1])))
        return hits

    def decompose(self, text: str) -> Tuple[List[str], str]:
        """贪心选取不重叠最长匹配，返回 (命中模式列表, 未匹配残余)"""
        hits = self.find_all(text)
        if not hits:
            return [], text

        selected: List[Tuple[int, int, str]] = []
        occupied: Set[int] = set()

        # 优先更长、更靠前的匹配
        for start, pattern in sorted(hits, key=lambda x: (-len(x[1]), x[0])):
            end = start + len(pattern)
            if any(pos in occupied for pos in range(start, end)):
                continue
            for pos in range(start, end):
                occupied.add(pos)
            selected.append((start, end, pattern))

        selected.sort(key=lambda x: x[0])
        patterns = [p for _, _, p in selected]
        remainder = "".join(text[i] for i in range(len(text)) if i not in occupied).strip()
        return patterns, remainder

    def contains_any(self, text: str) -> bool:
        return bool(self.find_all(text))
