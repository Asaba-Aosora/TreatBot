#!/usr/bin/env python3
"""
批量解析试验库，导出 inclusion/exclusion 化验条款与需人工复核项（如 ×ULN）。
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from codes.trial_matcher import load_trials  # noqa: E402


def main():
    src = PROJECT_ROOT / "original_data" / "clinical_trials" / "trials_structured.json"
    out_dir = PROJECT_ROOT / "structured_data" / "trial_parsed"
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = out_dir / "rules_bundle.json"
    review_path = out_dir / "needs_review.jsonl"

    trials = load_trials(str(src))
    bundle = []
    review_lines = []

    for t in trials:
        tid = t.get("项目编码")
        pc = t.get("parsed_conditions") or {}
        inc = pc.get("inclusion_lab_clauses") or []
        exc = pc.get("exclusion_lab_clauses") or []
        bundle.append(
            {
                "trial_id": tid,
                "inclusion_lab_clauses": inc,
                "exclusion_lab_clauses": exc,
                "parser_version": pc.get("parser_version"),
            }
        )
        for clause in inc + exc:
            if clause.get("relative_to_uln"):
                review_lines.append(
                    json.dumps({"trial_id": tid, "clause": clause}, ensure_ascii=False)
                )

    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    review_path.write_text("\n".join(review_lines) + ("\n" if review_lines else ""), encoding="utf-8")
    print(f"已写入: {bundle_path} ({len(bundle)} 条)")
    print(f"需复核(ULN等): {review_path} ({len(review_lines)} 行)")


if __name__ == "__main__":
    main()
