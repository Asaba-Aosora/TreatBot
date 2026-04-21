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


def _parse_range_bounds(range_raw: str) -> Tuple[Optional[float], Optional[float]]:
    text = (range_raw or "").strip()
    if not text or text in ("--", "-", "—"):
        return None, None
    cleaned = text.replace("~", "-").replace("～", "-").replace("--", "-")
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)", cleaned)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            return None, None
    return None, None


def _derive_status(
    value_raw: str,
    range_low: Optional[float],
    range_high: Optional[float],
    source_flag: Optional[str],
    old_status: str,
) -> str:
    if old_status in ("正常", "偏高", "偏低", "异常", "无法判断"):
        return old_status
    flag = (source_flag or "").strip()
    if flag == "↑":
        return "偏高"
    if flag == "↓":
        return "偏低"

    try:
        value = float(str(value_raw).strip())
    except (TypeError, ValueError):
        return "无法判断"
    if range_low is not None and value < range_low:
        return "偏低"
    if range_high is not None and value > range_high:
        return "偏高"
    if range_low is not None or range_high is not None:
        return "正常"
    return "无法判断"


def normalize_ocr_lab_payload(patient: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 OCR 原始 lab_results 分流并补齐标准字段。
    返回修改后的 patient（原地更新并返回）。
    """
    raw_rows = patient.get("lab_results") or []
    if not isinstance(raw_rows, list):
        patient["lab_results"] = []
        patient["_ocr_meta_unsorted"] = []
        patient["genomics_raw"] = []
        patient["_fix_report"] = {
            "total_input": 0,
            "kept_as_lab": 0,
            "moved_to_genomics": 0,
            "moved_to_meta": 0,
        }
        return patient

    lab_rows: List[Dict[str, Any]] = []
    genomics_rows: List[Dict[str, Any]] = []
    meta_rows: List[Dict[str, Any]] = []

    for row in raw_rows:
        item = str(row.get("item", "") or "")
        value = str(row.get("value", "") or "")
        unit = row.get("unit", "")
        unit_text = "" if unit is None else str(unit)
        source_flag = unit_text if unit_text in ("↑", "↓") else None
        range_raw = str(
            row.get("reference_range_raw") or row.get("range") or ""
        ).strip()
        range_low = row.get("range_low")
        range_high = row.get("range_high")
        if range_low is None and range_high is None:
            range_low, range_high = _parse_range_bounds(range_raw)
        old_status = str(row.get("status", "") or "")
        status = _derive_status(
            value, range_low, range_high, source_flag, old_status
        )

        cleaned = {
            "item": item,
            "value": value,
            "unit": (None if unit in (None, "") else unit_text),
            "range_low": range_low,
            "range_high": range_high,
            "reference_range_raw": range_raw,
            "status": status,
            "source_abnormal_flag": source_flag,
            # 向后兼容旧字段
            "range": range_raw,
        }
        kind = _classify_row(item, value, unit_text)
        if kind == "genomics":
            genomics_rows.append(
                {
                    "gene_info": item,
                    "vaf_percent": value,
                    "unit": unit if unit != "" else None,
                    "reference_vaf": range_raw,
                    "raw": {
                        "item": item,
                        "value": value,
                        "unit": unit_text,
                        "range": range_raw,
                        "status": old_status,
                    },
                }
            )
            continue
        if kind == "narrative":
            meta_rows.append(
                {
                    "item": item,
                    "value": value,
                    "unit": unit_text,
                    "range": range_raw,
                    "status": old_status,
                }
            )
            continue
        lab_rows.append(cleaned)

    status_dist: Dict[str, int] = {
        "正常": 0,
        "偏高": 0,
        "偏低": 0,
        "异常": 0,
        "无法判断": 0,
    }
    for row in lab_rows:
        status = str(row.get("status") or "无法判断")
        if status in status_dist:
            status_dist[status] += 1
        else:
            status_dist["无法判断"] += 1

    patient["lab_results"] = lab_rows
    patient["genomics_raw"] = genomics_rows
    patient["_ocr_meta_unsorted"] = meta_rows
    patient["_fix_report"] = {
        "total_input": len(raw_rows),
        "kept_as_lab": len(lab_rows),
        "moved_to_genomics": len(genomics_rows),
        "moved_to_meta": len(meta_rows),
        "status_distribution": status_dist,
    }
    return patient


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


def normalize_lab_results(
    lab_results: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
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
        if mid == "cr" and (
            "μmol" in unit or "umol" in unit_l or "μmol/l" in unit_l
        ):
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
                "raw": {
                    "item": item,
                    "value": value,
                    "unit": unit,
                    "range": row.get("range", ""),
                },
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
