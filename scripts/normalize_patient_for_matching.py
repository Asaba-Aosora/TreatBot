#!/usr/bin/env python3
"""
按 MATCHING_CHECKLIST 整理 OCR 患者 JSON，便于规则匹配。

用法:
    python scripts/normalize_patient_for_matching.py --file output_patients/CHQI..._fixed.json
    python scripts/normalize_patient_for_matching.py --file input.json --output output.json
    python scripts/normalize_patient_for_matching.py --file input.json --in-place
    python scripts/normalize_patient_for_matching.py --file input.json --run-match
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from codes.patient_matching_normalize import normalize_ocr_envelope  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="按 MATCHING_CHECKLIST 整理患者 OCR JSON")
    parser.add_argument("--file", required=True, help="OCR 患者 JSON 路径")
    parser.add_argument("--output", default="", help="输出路径（默认: 原文件名 _matching.json）")
    parser.add_argument("--in-place", action="store_true", help="覆盖原文件")
    parser.add_argument("--run-match", action="store_true", help="整理后立即跑 rank_trials 并打印 Top5")
    parser.add_argument("--match-mode", default="strict", choices=["strict", "balanced"])
    parser.add_argument("--top-n", type=int, default=10)
    args = parser.parse_args()

    src = Path(args.file)
    if not src.is_absolute():
        src = PROJECT_ROOT / src
    if not src.exists():
        print(f"[ERROR] 文件不存在: {src}", file=sys.stderr)
        return 1

    envelope = json.loads(src.read_text(encoding="utf-8"))
    normalize_ocr_envelope(envelope, source_hint=src.name)

    if args.in_place:
        out = src
    elif args.output:
        out = Path(args.output)
        if not out.is_absolute():
            out = PROJECT_ROOT / out
    else:
        out = src.with_name(src.stem + "_matching.json")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")

    report = envelope["patient"].get("_matching_normalize_report") or {}
    print(f"已写入: {out}")
    print(f"  lab_observations: {report.get('lab_observations_present')}")
    print(f"  缺失 P0: {report.get('missing_p0_metrics')}")
    print(f"  缺失 P1: {report.get('missing_p1_metrics')}")
    print(f"  biomarkers: {report.get('biomarkers')}")

    if args.run_match:
        from codes.trial_matcher import load_trials, rank_trials  # noqa: E402

        trial_path = PROJECT_ROOT / "original_data" / "clinical_trials" / "trials_structured.json"
        trials = load_trials(str(trial_path))
        patient = envelope["patient"]
        matches = rank_trials(patient, trials, top_n=args.top_n, match_mode=args.match_mode)
        print(f"\n匹配模式: {args.match_mode} | 候选数: {len(matches)} | Top {args.top_n}:")
        for i, m in enumerate(matches[: args.top_n], 1):
            review = "待核对" if m.get("needs_review") else "可确认"
            print(
                f"  {i}. {m.get('trial_id')} score={m.get('score', 0):.1f} "
                f"eligible={m.get('eligible')} {review} "
                f"reasons={m.get('reasons')[:2]}"
            )
            if m.get("missing_core_messages"):
                print(f"      缺失: {', '.join(m['missing_core_messages'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
