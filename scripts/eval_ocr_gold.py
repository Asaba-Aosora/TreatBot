#!/usr/bin/env python3
"""
对比 OCR 原始 JSON 与医生修订 JSON（gold），输出结构化质量指标。

示例:
python scripts/eval_ocr_gold.py \
  --raw output_patients/CHQI胰腺癌辽宁沈阳_患者信息.json \
  --gold output_patients/CHQI胰腺癌辽宁沈阳_患者信息_fixed.json \
  --save structured_data/eval/chqi_gold_baseline.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _norm_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", "", text)


def _norm_num(value: Any) -> str:
    raw = str(value or "").strip()
    if raw == "":
        return ""
    try:
        num = float(raw)
        if num.is_integer():
            return str(int(num))
        return f"{num:.6g}"
    except ValueError:
        return _norm_text(raw)


def _row_key(row: Dict[str, Any]) -> str:
    item = _norm_text(row.get("item", ""))
    value = _norm_num(row.get("value", ""))
    return f"{item}|{value}"


def _build_index(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        key = _row_key(row)
        if key and key not in idx:
            idx[key] = row
    return idx


def _extract_range_and_flag(row: Dict[str, Any]) -> Tuple[str, str]:
    raw_range = (
        row.get("reference_range_raw")
        or row.get("range")
        or ""
    )
    flag = row.get("source_abnormal_flag")
    if flag is None:
        unit = str(row.get("unit") or "")
        if unit in ("↑", "↓"):
            flag = unit
        else:
            flag = ""
    return _norm_text(raw_range), _norm_text(flag)


def evaluate(
    raw_patient: Dict[str, Any], gold_patient: Dict[str, Any]
) -> Dict[str, Any]:
    raw_labs = raw_patient.get("lab_results") or []
    gold_labs = gold_patient.get("lab_results") or []

    raw_idx = _build_index(raw_labs)
    gold_idx = _build_index(gold_labs)

    raw_keys = set(raw_idx.keys())
    gold_keys = set(gold_idx.keys())
    matched_keys = sorted(raw_keys & gold_keys)

    tp = len(matched_keys)
    fp = len(raw_keys - gold_keys)
    fn = len(gold_keys - raw_keys)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    unit_hit = 0
    range_hit = 0
    status_hit = 0
    flag_hit = 0
    for key in matched_keys:
        raw_row = raw_idx[key]
        gold_row = gold_idx[key]
        if _norm_text(raw_row.get("unit", "")) == _norm_text(
            gold_row.get("unit", "")
        ):
            unit_hit += 1
        raw_range, raw_flag = _extract_range_and_flag(raw_row)
        gold_range, gold_flag = _extract_range_and_flag(gold_row)
        if raw_range == gold_range:
            range_hit += 1
        if _norm_text(raw_row.get("status", "")) == _norm_text(
            gold_row.get("status", "")
        ):
            status_hit += 1
        if raw_flag == gold_flag:
            flag_hit += 1

    denom = len(matched_keys) or 1
    meta_unsorted = gold_patient.get("_ocr_meta_unsorted") or []
    genomics_raw = gold_patient.get("genomics_raw") or []
    total_input = len(raw_labs)
    diverted = len(meta_unsorted) + len(genomics_raw)
    diversion_rate = diverted / total_input if total_input else 0.0

    return {
        "counts": {
            "raw_lab_results": len(raw_labs),
            "gold_lab_results": len(gold_labs),
            "matched_rows": len(matched_keys),
            "raw_only_rows": fp,
            "gold_only_rows": fn,
            "gold_meta_unsorted": len(meta_unsorted),
            "gold_genomics_raw": len(genomics_raw),
        },
        "entity_metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        },
        "field_metrics": {
            "unit_accuracy_on_matched": round(unit_hit / denom, 4),
            "range_accuracy_on_matched": round(range_hit / denom, 4),
            "status_accuracy_on_matched": round(status_hit / denom, 4),
            "abnormal_flag_accuracy_on_matched": round(flag_hit / denom, 4),
        },
        "noise_metrics": {
            "diverted_rows": diverted,
            "diversion_rate_from_raw": round(diversion_rate, 4),
        },
        "samples": {
            "raw_only_examples": sorted(list(raw_keys - gold_keys))[:10],
            "gold_only_examples": sorted(list(gold_keys - raw_keys))[:10],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="评测 OCR 输出与医生修订数据差异"
    )
    parser.add_argument("--raw", required=True, help="原始 OCR JSON 路径")
    parser.add_argument("--gold", required=True, help="医生修订 JSON 路径")
    parser.add_argument("--save", default="", help="可选：保存评测结果 JSON")
    args = parser.parse_args()

    raw_obj = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    gold_obj = json.loads(Path(args.gold).read_text(encoding="utf-8"))
    report = evaluate(
        raw_obj.get("patient") or {}, gold_obj.get("patient") or {}
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.save:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n已保存: {save_path}")


if __name__ == "__main__":
    main()
