"""
试验入排文本：条款切片 + 与 lab_rules 联动的扩展解析结果。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from codes.lab_rules import extract_lab_rule_clauses
from codes.rag_clause_assist import extract_rag_lab_clause_candidates


def split_criteria_chunks(text: str, prefix: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"[。；;\n]+", text) if p.strip()]
    out: List[Dict[str, Any]] = []
    for i, p in enumerate(parts):
        out.append({"chunk_id": f"{prefix}_{i}", "text": p})
    return out


def enrich_parsed_conditions(trial: Dict[str, Any], base: Dict[str, Any]) -> Dict[str, Any]:
    inc = trial.get("入组条件", "") or ""
    exc = trial.get("排除条件", "") or ""
    base = dict(base)
    inc_chunks = split_criteria_chunks(inc, "inc")
    exc_chunks = split_criteria_chunks(exc, "exc")
    base["inclusion_chunks"] = inc_chunks
    base["exclusion_chunks"] = exc_chunks
    # 按条款切片分别抽取，避免跨句误匹配
    inc_clauses: List[Dict[str, Any]] = []
    for ch in inc_chunks:
        text = ch["text"]
        inc_clauses.extend(extract_lab_rule_clauses(text, "inclusion"))
        inc_clauses.extend(
            extract_rag_lab_clause_candidates(text, "inclusion", chunk_id=ch["chunk_id"])
        )
    exc_clauses: List[Dict[str, Any]] = []
    for ch in exc_chunks:
        text = ch["text"]
        exc_clauses.extend(extract_lab_rule_clauses(text, "exclusion"))
        exc_clauses.extend(
            extract_rag_lab_clause_candidates(text, "exclusion", chunk_id=ch["chunk_id"])
        )
    base["inclusion_lab_clauses"] = _dedup_clauses(inc_clauses)
    base["exclusion_lab_clauses"] = _dedup_clauses(exc_clauses)
    base["parser_version"] = "trial_parse_v2"
    return base


def _dedup_clauses(clauses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    for clause in clauses:
        metric_id = str(clause.get("metric_id") or "")
        operator = str(clause.get("operator") or "")
        threshold = clause.get("threshold")
        field = str(clause.get("field") or "")
        context = str(clause.get("context") or "")
        key = f"{field}|{metric_id}|{operator}|{threshold}|{context}"
        current = best.get(key)
        if current is None:
            best[key] = clause
            continue
        if float(clause.get("confidence", 0.0) or 0.0) > float(
            current.get("confidence", 0.0) or 0.0
        ):
            best[key] = clause
    return list(best.values())
