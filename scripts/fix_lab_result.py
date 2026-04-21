"""
修复 CHQI 胰腺癌病例 JSON 的 lab_results 字段
处理 5 个问题：
  1) ↑/↓ 从 unit 挪到 status
  2) status 填充 偏高/偏低/正常/异常
  3) 非化验项移出 lab_results → 另立 patient_meta / pathology / genomics
  4) 基因突变 VAF 从 range 挪到独立字段
  5) range "7--40" 解析为 {low: 7, high: 40}
运行:  python3 fix_lab_results.py input.json output.json
"""
import json, re, sys
from pathlib import Path

ARROW_MAP = {"↑": "偏高", "↓": "偏低"}

# 一行 item 就能被识别为"不是化验项"的关键词
NON_LAB_TOKENS = [
    "姓名", "性别", "籍贯", "年龄", "院号", "入院情况", "出院医嘱",
    "体格检查", "临床诊断", "送检材料", "订单编号", "报告版本",
    "目前", "门诊", "病理",
]

# 基因 / 分子检测 item 特征
GENE_TOKENS = ["错义突变", "exon", "::", "p.G", "p.R", "p.K", "HGVS", "c."]

RANGE_RE = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*-{1,2}\s*([-+]?\d+(?:\.\d+)?)\s*$")


def parse_range(s: str):
    """Return (low, high) or (None, None)."""
    if not s:
        return None, None
    m = RANGE_RE.match(str(s).strip())
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


def judge_status(value_str: str, low, high, arrow_hint: str = "") -> str:
    """Decide 正常 / 偏高 / 偏低 / 异常 / 无法判断."""
    if arrow_hint in ARROW_MAP:
        return ARROW_MAP[arrow_hint]
    try:
        v = float(value_str)
    except (TypeError, ValueError):
        return "无法判断"
    if low is None or high is None:
        return "无法判断"
    if low <= v <= high:
        return "正常"
    # Soft tolerance: within 10% of range band counts as 偏高/偏低 (not 异常)
    band = high - low
    if band <= 0:
        return "异常"
    if v < low:
        return "偏低" if (low - v) <= band * 0.2 else "异常"
    if v > high:
        return "偏高" if (v - high) <= band * 0.2 else "异常"
    return "无法判断"


def is_non_lab(item: dict) -> bool:
    it = str(item.get("item", ""))
    return any(tok in it for tok in NON_LAB_TOKENS)


def is_gene_record(item: dict) -> bool:
    it = str(item.get("item", ""))
    return any(tok in it for tok in GENE_TOKENS)


def fix(src_path: Path, dst_path: Path):
    data = json.loads(src_path.read_text(encoding="utf-8"))
    patient = data.get("patient", {})
    labs = patient.get("lab_results", [])

    clean_labs = []
    meta_entries = []   # 人口学/入院记录
    genomics = []       # 基因突变记录

    for item in labs:
        # --- 提取基因突变记录 ---
        if is_gene_record(item):
            genomics.append({
                "gene_info": item.get("item", ""),
                "vaf_percent": item.get("value"),    # 原 value 就是 VAF
                "unit": item.get("unit", "%"),
                "reference_vaf": item.get("range"),  # 原 range 其实是参考 VAF（存疑，建议重新校对）
                "raw": item,
            })
            continue

        # --- 提取非化验项 ---
        if is_non_lab(item):
            meta_entries.append(item)
            continue

        # --- 规范化 ↑/↓ ---
        unit_raw = str(item.get("unit", ""))
        arrow_hint = ""
        unit_clean = unit_raw
        for sym in ARROW_MAP:
            if sym in unit_raw:
                arrow_hint = sym
                unit_clean = unit_raw.replace(sym, "").strip()
                break

        # --- 规范化 range 为 low/high ---
        low, high = parse_range(item.get("range", ""))

        # --- 判断 status ---
        status = judge_status(
            value_str=item.get("value", ""),
            low=low, high=high,
            arrow_hint=arrow_hint,
        )

        clean_labs.append({
            "item": item.get("item", ""),
            "value": item.get("value", ""),
            "unit": unit_clean or None,
            "range_low": low,
            "range_high": high,
            "reference_range_raw": item.get("range", ""),
            "status": status,
            "source_abnormal_flag": arrow_hint or None,
        })

    patient["lab_results"] = clean_labs
    patient["_ocr_meta_unsorted"] = meta_entries      # 待再分类
    patient["genomics_raw"] = genomics                # 待基因团队复核
    data["patient"] = patient

    # 记录本次修复的统计
    data["_fix_report"] = {
        "total_input": len(labs),
        "kept_as_lab": len(clean_labs),
        "moved_to_genomics": len(genomics),
        "moved_to_meta": len(meta_entries),
        "status_distribution": {
            s: sum(1 for x in clean_labs if x["status"] == s)
            for s in ("正常", "偏高", "偏低", "异常", "无法判断")
        },
    }

    dst_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Fix report:", json.dumps(data["_fix_report"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        src = Path(sys.argv[1])
        dst = Path(sys.argv[2])
    else:
        src = Path(__file__).parent / "CHQI胰腺癌辽宁沈阳_患者信息.json"
        dst = src.with_name(src.stem + "_fixed.json")
    fix(src, dst)
    print(f"Saved: {dst}")
