"""
从试验入组/排除文本中抽取可比较的化验规则，并对患者指标做保守评估。
缺失数据：unknown（不视为硬失败，仅降权）；明确违反：fail。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

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
        rf"(?P<metric>{_METRIC_RE}).{{0,20}}(?P<op>[<>≤≥]=?)\s*"
        rf"(?P<val>\d+(?:\.\d+)?)\s*(?:x?\s*(?:uln|正常上限|上限)|×\s*(?:uln|正常上限))?",
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
                "relative_to_uln": (
                    "uln" in m.group(0).lower() or "正常上限" in m.group(0)
                ),
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


def _patient_metric_meta(patient: Dict) -> Dict[str, Dict[str, Any]]:
    meta: Dict[str, Dict[str, Any]] = {}
    for obs in patient.get("lab_observations") or []:
        mid = str(obs.get("metric_id") or "")
        if not mid:
            continue
        raw = obs.get("raw") or {}
        meta[mid] = {
            "unit_norm": str(obs.get("unit_norm") or ""),
            "raw_unit": str(raw.get("unit") or ""),
            "raw_range": str(raw.get("range") or ""),
        }
    return meta


def _suspect_unit_mismatch(
    metric_id: str,
    patient_val: float,
    threshold: float,
    op: str,
    meta: Dict[str, Any],
) -> bool:
    # 常见场景：试验写的是 xULN 倍数，但 OCR/解析得到绝对值且单位缺失，避免误判硬失败。
    if op not in ("<", "<=", "≤"):
        return False
    if threshold > 5:
        return False
    raw_range = str(meta.get("raw_range") or "")
    raw_unit = str(meta.get("raw_unit") or "")
    unit_norm = str(meta.get("unit_norm") or "")
    if not raw_range and not raw_unit and not unit_norm:
        return False
    if patient_val <= threshold * 8:
        return False
    # 对这些常见肝肾相关指标启用保护，避免误拒绝
    return metric_id in {"cr", "tbil", "alt", "ast", "alb"}


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
    pmeta = _patient_metric_meta(patient)
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
            if _suspect_unit_mismatch(mid, pv, thr, op, pmeta.get(mid, {})):
                checks.append(
                    {
                        "metric_id": mid,
                        "field": "inclusion",
                        "status": "unknown",
                        "message": "疑似单位不一致，转为待人工核对",
                        "patient_value": pv,
                        "threshold": thr,
                        "operator": op,
                        "evidence": clause.get("evidence"),
                    }
                )
                next_steps.append(mid)
                continue
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

    return (
        checks,
        inclusion_failed,
        exclusion_triggered,
        list(dict.fromkeys(next_steps)),
    )
