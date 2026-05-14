#!/usr/bin/env python3
"""
根据人工复核反馈构建持续学习工件：
- few-shot 样本
- 指标别名建议
- 回归样本集
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEEDBACK_DIR = PROJECT_ROOT / "structured_data" / "feedback"
OUT_DIR = PROJECT_ROOT / "structured_data" / "learning"


def _read_feedback_lines() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not FEEDBACK_DIR.exists():
        return items
    for fp in FEEDBACK_DIR.glob("*.jsonl"):
        for line in fp.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                items.append(json.loads(text))
            except json.JSONDecodeError:
                continue
    return items


def build_artifacts() -> Dict[str, Any]:
    rows = _read_feedback_lines()
    alias_suggestions: Dict[str, int] = {}
    few_shots: List[Dict[str, Any]] = []
    regression_cases: List[Dict[str, Any]] = []
    for row in rows:
        check = row.get("check") or {}
        metric = str(check.get("metric_id") or "").strip()
        reason = str(row.get("reason") or "").strip()
        if metric and reason:
            key = f"{metric}:{reason}"
            alias_suggestions[key] = alias_suggestions.get(key, 0) + 1
        few_shots.append(
            {
                "trial_id": row.get("trial_id"),
                "accepted": bool(row.get("accepted")),
                "reason": reason,
                "check": check,
            }
        )
        regression_cases.append(
            {
                "patient_id": row.get("patient_id"),
                "trial_id": row.get("trial_id"),
                "expected_accepted": bool(row.get("accepted")),
                "review_action": row.get("review_action"),
                "context": row.get("context", {}),
            }
        )
    ranked_alias = sorted(
        [{"signal": k, "count": v} for k, v in alias_suggestions.items()],
        key=lambda x: x["count"],
        reverse=True,
    )
    return {
        "feedback_total": len(rows),
        "alias_suggestions": ranked_alias,
        "few_shot_samples": few_shots[:200],
        "regression_cases": regression_cases,
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifacts = build_artifacts()
    (OUT_DIR / "alias_suggestions.json").write_text(
        json.dumps(artifacts["alias_suggestions"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "few_shot_samples.json").write_text(
        json.dumps(artifacts["few_shot_samples"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT_DIR / "regression_cases.json").write_text(
        json.dumps(artifacts["regression_cases"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"已生成学习工件: feedback={artifacts['feedback_total']} -> {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
