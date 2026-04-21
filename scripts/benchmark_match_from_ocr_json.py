#!/usr/bin/env python3
"""
用本地 OCR 产出的患者 JSON 批量压测匹配性能。

示例:
python scripts/benchmark_match_from_ocr_json.py --dir output_patients --top-n 20 --match-mode strict
python scripts/benchmark_match_from_ocr_json.py --file "output_patients/CHQI胰腺癌辽宁沈阳_患者信息.json"
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from codes.lab_normalize import attach_lab_observations  # noqa: E402
from codes.trial_matcher import load_trials, rank_trials  # noqa: E402


def _extract_patient(payload: Dict) -> Dict:
    patient = payload.get("patient")
    if not isinstance(patient, dict):
        raise ValueError("缺少 patient 字段")

    normalized = {
        "diagnosis": patient.get("diagnosis") or patient.get("cancer_type") or "",
        "age": patient.get("age"),
        "gender": patient.get("gender"),
        "ecog": patient.get("ecog"),
        "treatment_lines": patient.get("treatment_lines"),
        "location": patient.get("location"),
        "cancer_stage": patient.get("cancer_stage"),
        "biomarkers": patient.get("biomarkers") or [],
        "lab_results": patient.get("lab_results") or [],
    }
    return normalized


def _collect_files(single_file: Path, folder: Path) -> List[Path]:
    if single_file:
        return [single_file]
    files = sorted(folder.glob("*_患者信息.json"))
    if files:
        return files
    return sorted(folder.glob("*.json"))


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    values_sorted = sorted(values)
    rank = (len(values_sorted) - 1) * p
    low = int(rank)
    high = min(low + 1, len(values_sorted) - 1)
    weight = rank - low
    return values_sorted[low] * (1 - weight) + values_sorted[high] * weight


def main():
    parser = argparse.ArgumentParser(description="基于 OCR JSON 压测匹配性能")
    parser.add_argument("--file", type=str, default="", help="单个 OCR JSON 文件路径")
    parser.add_argument("--dir", type=str, default="output_patients", help="OCR JSON 目录")
    parser.add_argument("--trial-json", type=str, default="original_data/clinical_trials/trials_structured.json")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--match-mode", type=str, default="strict", choices=["strict", "balanced"])
    args = parser.parse_args()

    single_file = Path(args.file) if args.file else None
    folder = Path(args.dir)
    trial_path = Path(args.trial_json)

    if single_file and not single_file.exists():
        raise FileNotFoundError(f"文件不存在: {single_file}")
    if not folder.exists() and not single_file:
        raise FileNotFoundError(f"目录不存在: {folder}")
    if not trial_path.exists():
        raise FileNotFoundError(f"试验库不存在: {trial_path}")

    files = _collect_files(single_file, folder)
    if not files:
        print("未找到 OCR JSON 文件")
        return

    trials = load_trials(str(trial_path))
    print(f"加载试验数: {len(trials)}")
    print(f"待测样本数: {len(files)} | 模式: {args.match_mode} | top_n: {args.top_n}")

    durations_ms: List[float] = []
    total_candidates = 0
    per_file_summary: List[Tuple[str, int, float, str]] = []

    for fp in files:
        payload = json.loads(fp.read_text(encoding="utf-8"))
        patient = _extract_patient(payload)
        attach_lab_observations(patient)

        t0 = time.perf_counter()
        matches = rank_trials(patient, trials, top_n=args.top_n, match_mode=args.match_mode)
        dt_ms = (time.perf_counter() - t0) * 1000

        durations_ms.append(dt_ms)
        total_candidates += len(matches)
        top_trial = matches[0].get("trial_id", "-") if matches else "-"
        per_file_summary.append((fp.name, len(matches), dt_ms, str(top_trial)))

    avg_ms = statistics.mean(durations_ms)
    med_ms = statistics.median(durations_ms)
    p95_ms = _percentile(durations_ms, 0.95)
    max_ms = max(durations_ms)
    min_ms = min(durations_ms)
    avg_candidates = total_candidates / len(files)

    print("\n=== 性能汇总 ===")
    print(f"平均耗时: {avg_ms:.2f} ms/例")
    print(f"中位耗时: {med_ms:.2f} ms/例")
    print(f"P95耗时: {p95_ms:.2f} ms/例")
    print(f"最慢/最快: {max_ms:.2f} / {min_ms:.2f} ms")
    print(f"平均候选数: {avg_candidates:.2f}")

    print("\n=== 单例明细（前20）===")
    for name, cnt, dt_ms, top_trial in per_file_summary[:20]:
        print(f"{name} | {dt_ms:.2f} ms | 候选 {cnt} | Top1 {top_trial}")


if __name__ == "__main__":
    main()

