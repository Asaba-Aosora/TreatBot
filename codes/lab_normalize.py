"""
将 OCR 产出的 lab_results 清洗为 lab_observations（窄表），供匹配引擎使用。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from codes.lab_lexicon import GENOMICS_HINTS, NARRATIVE_HINTS
from codes.lab_rules import normalize_metric_key


def _classify_row(item: str, value: str, unit: str) -> str:
    blob = f"{item} {value} {unit}".lower()
    if any(h in blob for h in GENOMICS_HINTS):
        return "genomics"
    if any(h in item for h in NARRATIVE_HINTS) or len(item) > 40:
        return "narrative"
    return "lab"


def _parse_scalar(raw: str) -> Tuple[Optional[float], str]:
    s = (raw or "").strip()
    if not s:
        return None, ""
    comp = ""
    if s[0] in "<>≤≥":
        comp = s[0]
        if len(s) > 1 and s[1] == "=":
            comp = s[:2]
            s = s[2:].strip()
        else:
            s = s[1:].strip()
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None, comp
    return float(m.group(1)), comp


def _convert_creatinine_umol_to_mgdl(val: float) -> float:
    return val / 88.4


def normalize_lab_results(lab_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    observations: List[Dict[str, Any]] = []
    for row in lab_results or []:
        item = str(row.get("item", "") or "")
        value = str(row.get("value", "") or "")
        unit = str(row.get("unit", "") or "")
        kind = _classify_row(item, value, unit)
        if kind != "lab":
            continue
        mid = normalize_metric_key(item)
        if not mid:
            continue
        num, comp = _parse_scalar(value)
        if num is None:
            continue
        unit_l = unit.lower()
        value_num = num
        unit_norm = unit or ""
        if mid == "cr" and ("μmol" in unit or "umol" in unit_l or "μmol/l" in unit_l):
            value_num = _convert_creatinine_umol_to_mgdl(num)
            unit_norm = "mg/dL"
        conf = 0.85 if len(item) < 25 else 0.65
        observations.append(
            {
                "metric_id": mid,
                "value_num": value_num,
                "unit_norm": unit_norm,
                "comparator": comp or None,
                "confidence": conf,
                "raw": {"item": item, "value": value, "unit": unit, "range": row.get("range", "")},
            }
        )
    # 同 metric 保留置信度最高的一条
    best: dict[str, Dict[str, Any]] = {}
    for obs in observations:
        mid = obs["metric_id"]
        if mid not in best or obs["confidence"] > best[mid]["confidence"]:
            best[mid] = obs
    return list(best.values())


def attach_lab_observations(patient: Dict[str, Any]) -> Dict[str, Any]:
    raw = patient.get("lab_results") or []
    patient["lab_observations"] = normalize_lab_results(raw)
    return patient
