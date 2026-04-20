"""
从试验入组/排除文本中抽取可比较的化验规则，并对患者指标做保守评估。
缺失数据：unknown（不视为硬失败，仅降权）；明确违反：fail。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from codes.lab_lexicon import METRIC_ALIASES


def normalize_metric_key(name: str) -> str:
    n = re.sub(r"\s+", "", (name or "").lower())
    if not n:
        return ""
    for mid, aliases in METRIC_ALIASES.items():
        for a in aliases:
            if re.sub(r"\s+", "", a.lower()) in n:
                return mid
    return ""


def _metric_alias_pattern() -> str:
    parts = []
    for aliases in METRIC_ALIASES.values():
        for a in aliases:
            parts.append(re.escape(a))
    return "|".join(sorted(set(parts), key=len, reverse=True))


_METRIC_RE = _metric_alias_pattern()


def extract_lab_rule_clauses(text: str, field: str) -> List[Dict[str, Any]]:
    """
    从自由文本抽取简单数值比较规则（与 trial_matcher 中原逻辑一致，扩展为列表+证据）。
    field: inclusion | exclusion
    """
    if not text:
        return []
    clauses: List[Dict[str, Any]] = []
    for m in re.finditer(
        rf"(?P<metric>{_METRIC_RE}).{{0,20}}(?P<op>[<>≤≥]=?)\s*(?P<val>\d+(?:\.\d+)?)\s*(?:x?\s*(?:uln|正常上限|上限)|×\s*(?:uln|正常上限))?",
        text,
        re.IGNORECASE,
    ):
        raw_metric = m.group("metric")
        metric_id = normalize_metric_key(raw_metric)
        if metric_id not in METRIC_ALIASES:
            continue
        op = m.group("op")
        val = float(m.group("val"))
        span = m.group(0)
        clauses.append(
            {
                "metric_id": metric_id,
                "operator": op,
                "threshold": val,
                "relative_to_uln": "uln" in m.group(0).lower() or "正常上限" in m.group(0),
                "field": field,
                "severity": "must",
                "evidence": span.strip(),
            }
        )
    return clauses


def _patient_metric_map(patient: Dict) -> Dict[str, float]:
    """优先使用规范化后的 lab_observations。"""
    out: Dict[str, float] = {}
    for obs in patient.get("lab_observations") or []:
        mid = obs.get("metric_id")
        v = obs.get("value_num")
        if mid and isinstance(v, (int, float)):
            out[str(mid)] = float(v)
    if out:
        return out
    for row in patient.get("lab_results") or []:
        mid = normalize_metric_key(row.get("item", ""))
        if not mid:
            continue
        raw = row.get("value")
        try:
            out[mid] = float(str(raw).strip())
        except (TypeError, ValueError):
            continue
    return out


def _compare(op: str, patient_val: float, threshold: float) -> bool:
    if op == ">":
        return patient_val > threshold
    if op in (">=", "≥"):
        return patient_val >= threshold
    if op == "<":
        return patient_val < threshold
    if op in ("<=", "≤"):
        return patient_val <= threshold
    return False


def evaluate_lab_rule_clauses(
    patient: Dict,
    inclusion_clauses: List[Dict[str, Any]],
    exclusion_clauses: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], bool, bool, List[str]]:
    """
    Returns:
      checks: 每条规则评估结果
      inclusion_failed: 入组化验明确违反
      exclusion_triggered: 排除化验命中
      next_steps: 建议补检的 metric_id
    """
    pmap = _patient_metric_map(patient)
    checks: List[Dict[str, Any]] = []
    next_steps: List[str] = []
    inclusion_failed = False
    exclusion_triggered = False

    for clause in inclusion_clauses:
        mid = clause["metric_id"]
        op = clause["operator"]
        thr = float(clause["threshold"])
        pv = pmap.get(mid)
        if clause.get("relative_to_uln"):
            checks.append(
                {
                    "metric_id": mid,
                    "field": "inclusion",
                    "status": "unknown",
                    "message": "需实验室ULN才能判定相对阈值",
                    "evidence": clause.get("evidence"),
                }
            )
            next_steps.append(mid)
            continue
        if pv is None:
            checks.append(
                {
                    "metric_id": mid,
                    "field": "inclusion",
                    "status": "unknown",
                    "message": "患者数据缺少该指标",
                    "evidence": clause.get("evidence"),
                }
            )
            next_steps.append(mid)
            continue
        ok = _compare(op, pv, thr)
        # 入组条件通常表达为下限或上限；这里按字面比较符解释
        if not ok:
            inclusion_failed = True
            checks.append(
                {
                    "metric_id": mid,
                    "field": "inclusion",
                    "status": "fail",
                    "message": f"不满足入组要求: {mid} 当前{pv}, 要求 {op}{thr}",
                    "patient_value": pv,
                    "threshold": thr,
                    "operator": op,
                    "evidence": clause.get("evidence"),
                }
            )
        else:
            checks.append(
                {
                    "metric_id": mid,
                    "field": "inclusion",
                    "status": "pass",
                    "patient_value": pv,
                    "threshold": thr,
                    "operator": op,
                    "evidence": clause.get("evidence"),
                }
            )

    for clause in exclusion_clauses:
        mid = clause["metric_id"]
        op = clause["operator"]
        thr = float(clause["threshold"])
        pv = pmap.get(mid)
        if pv is None:
            checks.append(
                {
                    "metric_id": mid,
                    "field": "exclusion",
                    "status": "unknown",
                    "message": "无法判断是否触发排除（缺指标）",
                    "evidence": clause.get("evidence"),
                }
            )
            continue
        if _compare(op, pv, thr):
            exclusion_triggered = True
            checks.append(
                {
                    "metric_id": mid,
                    "field": "exclusion",
                    "status": "fail",
                    "message": f"命中排除: {mid}={pv} 满足排除条件 {op}{thr}",
                    "patient_value": pv,
                    "threshold": thr,
                    "operator": op,
                    "evidence": clause.get("evidence"),
                }
            )
        else:
            checks.append(
                {
                    "metric_id": mid,
                    "field": "exclusion",
                    "status": "pass",
                    "patient_value": pv,
                    "threshold": thr,
                    "operator": op,
                    "evidence": clause.get("evidence"),
                }
            )

    return checks, inclusion_failed, exclusion_triggered, list(dict.fromkeys(next_steps))
