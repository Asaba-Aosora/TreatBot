#!/usr/bin/env python3
"""
将临床试验原始 Excel 第一个 sheet（招募中项目）导出为 trials_structured.json。

用法（项目根目录）:
    python scripts/sync_xlsx_to_trials_json.py

可选参数:
    --xlsx   原始 Excel 路径
    --sheet  sheet 名称或索引（默认 0，即第一个 sheet）
    --output 输出 JSON 路径
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_XLSX = (
    PROJECT_ROOT
    / "original_data"
    / "clinical_trials"
    / "临床试验数据20250908-原始数据.xlsx"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "original_data" / "clinical_trials" / "trials_structured.json"
)


def _cell_to_json(value):
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if pd.isna(value):
        return None
    if hasattr(value, "item"):  # numpy scalar
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    return value


def xlsx_sheet_to_trials(
    xlsx_path: Path,
    sheet=0,
) -> list[dict]:
    df = pd.read_excel(xlsx_path, sheet_name=sheet)
    records = []
    for row in df.to_dict(orient="records"):
        records.append({str(k): _cell_to_json(v) for k, v in row.items()})
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Excel 招募中项目 → trials_structured.json")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX, help="原始 Excel 路径")
    parser.add_argument(
        "--sheet",
        default=0,
        help="sheet 名称或索引（默认 0 = 第一个 sheet）",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="输出 JSON 路径")
    args = parser.parse_args()

    xlsx_path = args.xlsx if args.xlsx.is_absolute() else PROJECT_ROOT / args.xlsx
    output_path = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output

    if not xlsx_path.exists():
        print(f"[ERROR] 找不到 Excel: {xlsx_path}", file=sys.stderr)
        return 1

    sheet = args.sheet
    if isinstance(sheet, str) and sheet.isdigit():
        sheet = int(sheet)

    xl = pd.ExcelFile(xlsx_path)
    sheet_label = xl.sheet_names[sheet] if isinstance(sheet, int) else sheet
    print(f"读取: {xlsx_path}")
    print(f"sheet: {sheet_label}")

    trials = xlsx_sheet_to_trials(xlsx_path, sheet=sheet)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(trials, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"已写入: {output_path}")
    print(f"   试验条数: {len(trials)}")
    if trials:
        print(f"   字段数: {len(trials[0])}")
        print(f"   字段示例: {', '.join(list(trials[0].keys())[:6])}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
