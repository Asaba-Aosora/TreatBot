#!/usr/bin/env python3
"""
离线回归：用固定患者 fixture 跑 rank_trials，防止解析/匹配改动引入回归。
用法: python scripts/eval_regression.py
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from codes.lab_normalize import attach_lab_observations  # noqa: E402
from codes.trial_matcher import load_trials, rank_trials  # noqa: E402


def main():
    fixture_path = PROJECT_ROOT / "structured_data" / "eval" / "fixture_patient.json"
    trial_path = PROJECT_ROOT / "original_data" / "clinical_trials" / "trials_structured.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    patient = data["patient"]
    attach_lab_observations(patient)
    expect_id = data["expect_trial_id_in_top"]
    top_n = int(data.get("top_n", 30))

    trials = load_trials(str(trial_path))
    matches = rank_trials(patient, trials, top_n=top_n)
    ids = [m.get("trial_id") for m in matches]
    if expect_id not in ids:
        print("FAIL: 期望试验不在 Top 列表内")
        print("expect:", expect_id)
        print("got (first 10):", ids[:10])
        sys.exit(1)
    print("OK: 回归通过, 期望试验在候选内, 条数=", len(matches))


if __name__ == "__main__":
    main()
