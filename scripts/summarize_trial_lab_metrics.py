#!/usr/bin/env python3
"""
从试验库入排条件统计化验指标提及频率（基于 lab_lexicon 别名 + 已解析数值条款）。

用法（项目根目录）:
    python scripts/summarize_trial_lab_metrics.py

输出:
    structured_data/trial_parsed/lab_metric_frequency.json
    structured_data/trial_parsed/lab_metric_frequency.md
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from codes.lab_lexicon import METRIC_ALIASES  # noqa: E402
from codes.trial_matcher import load_trials  # noqa: E402

DEFAULT_TRIALS = PROJECT_ROOT / "original_data" / "clinical_trials" / "trials_structured.json"
OUT_DIR = PROJECT_ROOT / "structured_data" / "trial_parsed"
JSON_OUT = OUT_DIR / "lab_metric_frequency.json"
MD_OUT = OUT_DIR / "lab_metric_frequency.md"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", (text or "")).lower()


def _alias_in_text(alias: str, norm_text: str) -> bool:
    a = _normalize(alias)
    if not a:
        return False
    if re.fullmatch(r"[a-z0-9]+", a):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(a)}(?![a-z0-9])", norm_text))
    return a in norm_text


def detect_metrics_in_text(text: str) -> Set[str]:
    """返回文本中提及到的 metric_id 集合（每个 metric 至多计一次）。"""
    norm = _normalize(text)
    if not norm:
        return set()
    found: Set[str] = set()
    for metric_id, aliases in METRIC_ALIASES.items():
        sorted_aliases = sorted(aliases, key=len, reverse=True)
        for alias in sorted_aliases:
            if _alias_in_text(alias, norm):
                found.add(metric_id)
                break
    return found


def _first_evidence_snippet(text: str, metric_id: str, width: int = 80) -> str:
    aliases = sorted(METRIC_ALIASES.get(metric_id, []), key=len, reverse=True)
    raw = text or ""
    norm_raw = raw.lower()
    for alias in aliases:
        pos = -1
        if re.fullmatch(r"[a-z0-9]+", alias.lower()):
            m = re.search(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", norm_raw)
            if m:
                pos = m.start()
        else:
            pos = _normalize(raw).find(_normalize(alias))
        if pos >= 0:
            start = max(0, pos - 20)
            end = min(len(raw), pos + width)
            snippet = re.sub(r"\s+", " ", raw[start:end]).strip()
            return snippet
    return ""


def summarize_trial_lab_metrics(trials_path: Path) -> Dict[str, Any]:
    trials = load_trials(str(trials_path))
    total = len(trials)

    mention_inc: Dict[str, Set[str]] = defaultdict(set)
    mention_exc: Dict[str, Set[str]] = defaultdict(set)
    parsed_inc: Dict[str, Set[str]] = defaultdict(set)
    parsed_exc: Dict[str, Set[str]] = defaultdict(set)
    evidence_pool: Dict[str, List[str]] = defaultdict(list)

    for trial in trials:
        tid = str(trial.get("项目编码") or "")
        inc_text = trial.get("入组条件") or ""
        exc_text = trial.get("排除条件") or ""
        pc = trial.get("parsed_conditions") or {}

        for mid in detect_metrics_in_text(inc_text):
            mention_inc[mid].add(tid)
            if len(evidence_pool[mid]) < 3:
                snip = _first_evidence_snippet(inc_text, mid)
                if snip and snip not in evidence_pool[mid]:
                    evidence_pool[mid].append(snip)

        for mid in detect_metrics_in_text(exc_text):
            mention_exc[mid].add(tid)

        for clause in pc.get("inclusion_lab_clauses") or []:
            mid = str(clause.get("metric_id") or "")
            if mid in METRIC_ALIASES:
                parsed_inc[mid].add(tid)
        for clause in pc.get("exclusion_lab_clauses") or []:
            mid = str(clause.get("metric_id") or "")
            if mid in METRIC_ALIASES:
                parsed_exc[mid].add(tid)

    rows: List[Dict[str, Any]] = []
    for metric_id in METRIC_ALIASES:
        inc_ids = mention_inc.get(metric_id, set())
        exc_ids = mention_exc.get(metric_id, set())
        any_ids = inc_ids | exc_ids
        rows.append(
            {
                "metric_id": metric_id,
                "aliases": METRIC_ALIASES[metric_id],
                "trials_mention_total": len(any_ids),
                "trials_mention_inclusion": len(inc_ids),
                "trials_mention_exclusion": len(exc_ids),
                "trials_with_parsed_inclusion_clause": len(parsed_inc.get(metric_id, set())),
                "trials_with_parsed_exclusion_clause": len(parsed_exc.get(metric_id, set())),
                "mention_rate": round(len(any_ids) / total, 4) if total else 0.0,
                "sample_evidence": evidence_pool.get(metric_id, []),
            }
        )

    rows.sort(
        key=lambda r: (
            -r["trials_mention_total"],
            -r["trials_with_parsed_inclusion_clause"],
            r["metric_id"],
        )
    )

    return {
        "total_trials": total,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(trials_path),
        "lexicon_size": len(METRIC_ALIASES),
        "note": (
            "trials_mention_* 为入排原文别名提及（不要求有数值阈值）；"
            "trials_with_parsed_*_clause 为正则/RAG 解析出的数值条款。"
        ),
        "metrics": rows,
    }


def _write_markdown(report: Dict[str, Any], path: Path) -> None:
    total = report["total_trials"]
    lines = [
        "# 试验库化验指标提及频率",
        "",
        f"- 试验总数: **{total}**",
        f"- 数据来源: `{report['source']}`",
        f"- 生成时间: {report['generated_at']}",
        "",
        "| 排名 | metric_id | 入组提及 | 排除提及 | 合计提及 | 提及率 | 入组数值条款 | 排除数值条款 | 别名示例 |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for idx, row in enumerate(report["metrics"], start=1):
        alias_sample = "、".join(row["aliases"][:3])
        rate_pct = f"{row['mention_rate'] * 100:.1f}%"
        lines.append(
            f"| {idx} | `{row['metric_id']}` | {row['trials_mention_inclusion']} "
            f"| {row['trials_mention_exclusion']} | **{row['trials_mention_total']}** "
            f"| {rate_pct} | {row['trials_with_parsed_inclusion_clause']} "
            f"| {row['trials_with_parsed_exclusion_clause']} | {alias_sample} |"
        )

    lines.extend(["", "## 说明", "", report.get("note", ""), ""])
    for row in report["metrics"][:5]:
        if not row.get("sample_evidence"):
            continue
        lines.append(f"### `{row['metric_id']}` 原文示例")
        for snip in row["sample_evidence"]:
            lines.append(f"- {snip}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    trials_path = DEFAULT_TRIALS
    if not trials_path.exists():
        print(f"[ERROR] 找不到试验库: {trials_path}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = summarize_trial_lab_metrics(trials_path)

    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report, MD_OUT)

    print(f"已写入: {JSON_OUT}")
    print(f"已写入: {MD_OUT}")
    print(f"试验总数: {report['total_trials']}")
    print("\nTop 10 提及频率:")
    for idx, row in enumerate(report["metrics"][:10], start=1):
        print(
            f"  {idx}. {row['metric_id']:5s}  "
            f"合计={row['trials_mention_total']:3d}  "
            f"入组={row['trials_mention_inclusion']:3d}  "
            f"数值条款={row['trials_with_parsed_inclusion_clause']:3d}  "
            f"({row['mention_rate']*100:.1f}%)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
