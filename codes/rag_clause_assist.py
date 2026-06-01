"""
RAG/模板辅助条款抽取：
1) 检索相似模板；
2) 用更宽松中文比较表达抽取候选 DSL。
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, List

from codes.lab_lexicon import METRIC_ALIASES
from codes.lab_rules import build_clause, normalize_metric_key

_HASH_DIM = 256


def _hash_embed(text: str, dim: int = _HASH_DIM) -> List[float]:
    """轻量哈希向量（仅用于化验模板相似度，与 Faiss 主索引无关）。"""
    vec = [0.0] * dim
    norm_text = normalize_text(text)
    if not norm_text:
        return vec
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", norm_text)
    for tok in tokens:
        digest = hashlib.md5(tok.encode("utf-8")).hexdigest()
        idx = int(digest, 16) % dim
        vec[idx] += 1.0
    length = math.sqrt(sum(v * v for v in vec))
    if length:
        vec = [v / length for v in vec]
    return vec


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()

_TEMPLATE_LIBRARY = [
    "总胆红素不超过1.5倍ULN，ALT/AST不高于2.5倍正常上限",
    "肌酐清除率应不低于60，血肌酐应小于等于1.5",
    "白细胞至少3.0，中性粒细胞绝对值至少1.5，血小板不少于100",
    "INR不超过1.5，APTT不高于正常上限1.5倍",
]
_TEMPLATE_VECS = [_hash_embed(x) for x in _TEMPLATE_LIBRARY]


def _metric_alias_pattern() -> str:
    aliases: List[str] = []
    for group in METRIC_ALIASES.values():
        aliases.extend(group)
    return "|".join(sorted({re.escape(a) for a in aliases}, key=len, reverse=True))


_METRIC_RE = _metric_alias_pattern()
_OP_HINTS = [
    ("不超过", "<="),
    ("小于等于", "<="),
    ("低于", "<"),
    ("至少", ">="),
    ("不低于", ">="),
    ("大于等于", ">="),
    ("高于", ">"),
]


def _template_similarity(text: str) -> float:
    qvec = _hash_embed(text)
    if not qvec:
        return 0.0
    return max(_cosine(qvec, tvec) for tvec in _TEMPLATE_VECS)


def extract_rag_lab_clause_candidates(
    chunk_text: str, field: str, chunk_id: str
) -> List[Dict[str, Any]]:
    text = str(chunk_text or "").strip()
    if not text:
        return []
    norm = normalize_text(text)
    sim = _template_similarity(text)
    candidates: List[Dict[str, Any]] = []
    for hint_text, op in _OP_HINTS:
        pattern = (
            rf"(?P<metric>{_METRIC_RE}).{{0,18}}{re.escape(hint_text)}\s*"
            rf"(?P<val>\d+(?:\.\d+)?)\s*(?P<uln>(?:倍|x|×)?\s*(?:uln|正常上限|上限))?"
        )
        for m in re.finditer(pattern, text, re.IGNORECASE):
            metric_id = normalize_metric_key(m.group("metric"))
            if not metric_id:
                continue
            val = float(m.group("val"))
            evidence = m.group(0).strip()
            confidence = 0.78 if sim >= 0.2 else 0.65
            candidates.append(
                build_clause(
                    metric_id=metric_id,
                    operator=op,
                    threshold=val,
                    relative_to_uln=bool(m.group("uln")),
                    field=field,
                    evidence=evidence,
                    source="rag_template",
                    confidence=confidence,
                    context=norm,
                    chunk_id=chunk_id,
                )
            )
    return candidates
