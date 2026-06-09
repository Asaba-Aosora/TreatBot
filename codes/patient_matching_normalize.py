"""
按 docs/MATCHING_CHECKLIST.md 将 OCR 患者 JSON 整理为匹配引擎可用的结构。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from codes.geo_admin import apply_location_to_patient
from codes.lab_lexicon import METRIC_ALIASES
from codes.lab_normalize import attach_lab_observations, normalize_ocr_lab_payload
from codes.lab_rules import normalize_metric_key
from codes.patient_filename_infer import apply_filename_hints, infer_from_filename
from codes.trial_matcher import summarize_patient_data_quality

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHECKLIST = PROJECT_ROOT / "structured_data" / "matching_checklist.json"

EXTRA_ITEM_METRIC_HINTS: List[Tuple[str, str]] = [
    ("中性粒细胞绝对值", "anc"),
    ("粒细胞计数", "anc"),
    ("ne#", "anc"),
    ("anc", "anc"),
    ("血红蛋白(hb)浓度", "hb"),
    ("hgb", "hb"),
    ("白细胞计数", "wbc"),
    ("wbc", "wbc"),
    ("血小板计数", "plt"),
    ("plt", "plt"),
    ("pt国际标准化比值", "inr"),
    ("inr", "inr"),
    ("血浆凝血酶原时间", "pt"),
    ("凝血酶原时间", "pt"),
    ("活化部分凝血活酶时间", "aptt"),
    ("aptt", "aptt"),
    ("丙氨酸氨基转移酶", "alt"),
    ("天门冬氨酸氨基转移酶", "ast"),
    ("总胆红素", "tbil"),
    ("肌酐", "cr"),
    ("白蛋白", "alb"),
]

STAGE_PATTERNS = [
    (r"[Ⅳ4]期|IV期|iv期", "IV"),
    (r"[Ⅲ3]期|III期", "III"),
    (r"[Ⅱ2]期|II期", "II"),
    (r"[Ⅰ1]期|I期", "I"),
]

# 括号内临床分期，如 （Ⅳ）、(IV)
PAREN_STAGE_RE = re.compile(r"[（(]\s*([^）)]+?)\s*[）)]")

# TNM M1 / TXNXM1 → 临床 IV 期（远处转移）
TNM_M1_RE = re.compile(
    r"TXNXM1\b|"
    r"T[0-9Xx][cCp]?[Nn][0-9Xx][cCp]?[Mm]1\b|"
    r"[cp]M1\b|"
    r"(?<![A-Za-z0-9])M1(?![0-9])",
    re.I,
)

_PAREN_STAGE_TOKEN: Dict[str, str] = {
    "Ⅳ": "IV",
    "4": "IV",
    "IV": "IV",
    "Ⅲ": "III",
    "3": "III",
    "III": "III",
    "Ⅱ": "II",
    "2": "II",
    "II": "II",
    "Ⅰ": "I",
    "1": "I",
    "I": "I",
}


def _stage_from_paren_token(token: str) -> Optional[str]:
    t = re.sub(r"\s+", "", (token or "").strip())
    if not t or len(t) > 6:
        return None
    if t in _PAREN_STAGE_TOKEN:
        return _PAREN_STAGE_TOKEN[t]
    upper = t.upper()
    if upper in _PAREN_STAGE_TOKEN:
        return _PAREN_STAGE_TOKEN[upper]
    for prefix, stage in (("IV", "IV"), ("III", "III"), ("II", "II")):
        if upper.startswith(prefix):
            return stage
    if t.startswith("Ⅳ"):
        return "IV"
    if t.startswith("Ⅲ"):
        return "III"
    if t.startswith("Ⅱ"):
        return "II"
    if t.startswith("Ⅰ"):
        return "I"
    return None


def infer_stage_from_text(text: str) -> Optional[str]:
    """从诊断等自由文本推断罗马数字分期（I–IV）。"""
    blob = str(text or "")
    if not blob:
        return None
    for pat, stage in STAGE_PATTERNS:
        if re.search(pat, blob, re.I):
            return stage
    for m in PAREN_STAGE_RE.finditer(blob):
        stage = _stage_from_paren_token(m.group(1))
        if stage:
            return stage
    if TNM_M1_RE.search(blob):
        return "IV"
    return None

#  Item 含以下子串时，勿映射到某些 metric（避免 Hb/MCHC、白蛋白/前白蛋白混淆）
EXCLUDE_IF_CONTAINS: Dict[str, List[str]] = {
    "hb": ["mchc", "mch", "mcv", "rdw", "压积", "hct"],
    "alb": ["前白蛋白"],
    "cr": ["清除率", "ccr", "胱抑素"],
    "wbc": ["幼稚", "幼稚粒"],
}


def load_matching_checklist(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or DEFAULT_CHECKLIST
    return json.loads(p.read_text(encoding="utf-8"))


def checklist_metric_ids(checklist: Optional[Dict[str, Any]] = None) -> List[str]:
    cl = checklist or load_matching_checklist()
    return [m["metric_id"] for m in cl.get("lab_metrics", [])]


def resolve_metric_id(item: str) -> str:
    mid = normalize_metric_key(item)
    if mid:
        return mid
    norm = re.sub(r"\s+", "", (item or "")).lower()
    for hint, metric_id in EXTRA_ITEM_METRIC_HINTS:
        if hint in norm:
            return metric_id
    return ""


def _row_excluded_for_metric(item: str, metric_id: str) -> bool:
    norm = re.sub(r"\s+", "", (item or "")).lower()
    for bad in EXCLUDE_IF_CONTAINS.get(metric_id, []):
        if bad in norm:
            return True
    return False


def _score_row_for_metric(row: Dict[str, Any], metric_id: str) -> float:
    item = str(row.get("item") or "")
    if _row_excluded_for_metric(item, metric_id):
        return -1.0
    mid = resolve_metric_id(item)
    if mid != metric_id:
        return -1.0
    norm = re.sub(r"\s+", "", item).lower()
    score = 0.0
    aliases = METRIC_ALIASES.get(metric_id, [])
    for idx, alias in enumerate(aliases):
        a = re.sub(r"\s+", "", alias).lower()
        if not a:
            continue
        if norm == a or a == norm:
            score += 100
        elif a in norm:
            score += max(10, 30 - idx * 2)
    if row.get("status") and row.get("status") != "无法判断":
        score += 2
    if row.get("range_low") is not None or row.get("range_high") is not None:
        score += 1
    return score


def _parse_flag_and_value(raw_val: str) -> Tuple[str, Optional[str]]:
    text = (raw_val or "").strip()
    flag = None
    if text.endswith("↑"):
        flag = "↑"
        text = text[:-1].strip()
    elif text.endswith("↓"):
        flag = "↓"
        text = text[:-1].strip()
    return text, flag


def _parse_range_pair(text: str) -> Tuple[Optional[float], Optional[float]]:
    t = (text or "").replace("～", "-").replace("--", "-").replace("~", "-")
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)", t)
    if not m:
        return None, None
    try:
        return float(m.group(1)), float(m.group(2))
    except ValueError:
        return None, None


def _lab_row(
    item: str,
    value: str,
    unit: Optional[str] = None,
    range_raw: str = "",
    flag: Optional[str] = None,
    status: str = "",
) -> Dict[str, Any]:
    val_clean, inline_flag = _parse_flag_and_value(value)
    flag = flag or inline_flag
    rlo, rhi = _parse_range_pair(range_raw)
    st = status
    if not st and flag == "↑":
        st = "偏高"
    elif not st and flag == "↓":
        st = "偏低"
    return {
        "item": item,
        "value": val_clean,
        "unit": unit or None,
        "range_low": rlo,
        "range_high": rhi,
        "reference_range_raw": range_raw,
        "status": st or "正常" if (rlo is not None or rhi is not None) else "",
        "source_abnormal_flag": flag,
        "range": range_raw,
    }


def parse_labs_from_ocr_text(text: str) -> List[Dict[str, Any]]:
    """从 raw_ocr 表格行解析化验项。"""
    rows: List[Dict[str, Any]] = []
    if not text:
        return rows

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("注"):
            continue

        # 项目名称\t缩写\t结果\t异常\t单位\t参考范围（异常列可能为空）
        parts = [p.strip() for p in re.split(r"\t+", line) if p.strip() or True]
        parts = [p.strip() for p in re.split(r"\t+", line)]
        if len(parts) >= 5:
            abbr = parts[1].upper() if len(parts) > 1 else ""
            name = parts[0]
            item_guess = f"{name} {parts[1]}".strip() if len(parts) > 1 else name
            mid = resolve_metric_id(item_guess) or resolve_metric_id(abbr)
            if mid:
                val, flag = _parse_flag_and_value(parts[2])
                if len(parts) >= 6:
                    unit = parts[4] if parts[4] not in ("--", "-", "—", "") else None
                    rng = parts[5]
                else:
                    unit = parts[3] if len(parts) > 3 and parts[3] not in ("--", "-", "—", "↑", "↓", "") else None
                    rng = parts[4] if len(parts) > 4 else ""
                    if parts[3] in ("↑", "↓"):
                        flag = flag or parts[3]
                rows.append(_lab_row(item_guess, val, unit=unit, range_raw=rng, flag=flag))
                continue

        # 项目名称\t结果\t参考范围\t单位  (肝功常见)
        if len(parts) == 4:
            item, val_raw, rng, unit = parts
            if resolve_metric_id(item):
                val, flag = _parse_flag_and_value(val_raw)
                rows.append(_lab_row(item, val, unit=unit or None, range_raw=rng, flag=flag))
            continue

        # 项目名称    缩写    结果 ... (空格分隔血常规)
        m = re.match(
            r"^(.+?)\s{2,}([A-Za-z#]+)?\s*([\d.]+)\s*(↑|↓)?\s*(\S+)?\s*([\d.\-]+(?:\s*-\s*[\d.]+)?)?",
            line,
        )
        if m:
            name = m.group(1).strip()
            abbr = (m.group(2) or "").strip()
            item = f"{name} {abbr}".strip() if abbr else name
            if resolve_metric_id(item):
                rows.append(
                    _lab_row(
                        item,
                        m.group(3),
                        unit=m.group(5) if m.group(5) and not re.match(r"[\d.\-]", m.group(5)) else None,
                        range_raw=m.group(6) or "",
                        flag=m.group(4),
                    )
                )
    return rows


def extract_biomarkers(patient: Dict[str, Any], raw_ocr_texts: List[str]) -> List[str]:
    markers: List[str] = []
    seen: Set[str] = set()

    def add(tag: str) -> None:
        t = tag.strip()
        if t and t not in seen:
            seen.add(t)
            markers.append(t)

    for row in patient.get("genomics_raw") or []:
        info = str(row.get("gene_info") or row.get("item") or "")
        m = re.match(r"^([A-Za-z0-9]+)", info)
        if not m:
            continue
        gene = m.group(1).upper()
        mut = re.search(r"p\.([A-Za-z0-9]+)", info)
        if "拷贝数缺失" in info or "纯合缺失" in info:
            add(f"{gene} 拷贝数缺失")
        elif mut:
            add(f"{gene} {mut.group(0)}")
        else:
            add(gene)

    blob = "\n".join(raw_ocr_texts or [])
    if re.search(r"MSI[- ]?H", blob, re.I):
        if re.search(r"未检测到\s*MSI[- ]?H|未检出.*MSI", blob):
            add("MSI 稳定型")
        else:
            add("MSI-H")
    if re.search(r"PD[- ]?L1", blob, re.I):
        cps = re.search(r"CPS\s*[=＝]\s*(\d+(?:\.\d+)?)", blob, re.I)
        tps = re.search(r"TPS\s*[<≤]\s*(\d+)", blob, re.I)
        if cps:
            add(f"PD-L1 CPS={cps.group(1)}")
        elif tps:
            add("PD-L1 TPS<1%")
        else:
            add("PD-L1")
    tmb = re.search(r"TMB[^\n]*?(\d+(?:\.\d+)?)\s*个突变", blob, re.I)
    if tmb:
        add(f"TMB {tmb.group(1)} mut/Mb")

    return markers


def infer_cancer_stage(patient: Dict[str, Any]) -> Optional[str]:
    existing = patient.get("cancer_stage")
    if existing:
        normalized = infer_stage_from_text(str(existing))
        return normalized or str(existing).strip() or None
    return infer_stage_from_text(str(patient.get("diagnosis") or ""))


def _merge_metric_rows(
    *sources: List[Dict[str, Any]],
    allowed_metrics: Optional[Set[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    best: Dict[str, Dict[str, Any]] = {}
    best_score: Dict[str, float] = {}
    metrics = allowed_metrics or set(METRIC_ALIASES.keys())
    for rows in sources:
        for row in rows:
            item = str(row.get("item") or "")
            for mid in metrics:
                sc = _score_row_for_metric(row, mid)
                if sc < 0:
                    continue
                if mid not in best or sc > best_score.get(mid, -1):
                    best[mid] = row
                    best_score[mid] = sc
    return best


def normalize_patient_for_matching(
    patient: Dict[str, Any],
    *,
    raw_ocr_texts: Optional[List[str]] = None,
    source_hint: str = "",
    pdf_file: str = "",
    checklist: Optional[Dict[str, Any]] = None,
    preserve_meta: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    整理 patient 字段，返回 (patient, normalize_report)。
    会原地更新 patient。
    """
    cl = checklist or load_matching_checklist()
    allowed = set(checklist_metric_ids(cl))
    raw_ocr_texts = raw_ocr_texts or []

    # 保留原始 lab 快照
    if preserve_meta and "_lab_results_raw" not in patient:
        patient["_lab_results_raw"] = list(patient.get("lab_results") or [])

    from_rows = list(patient.get("lab_results") or [])
    from_ocr: List[Dict[str, Any]] = []
    for chunk in raw_ocr_texts:
        from_ocr.extend(parse_labs_from_ocr_text(chunk))

    merged = _merge_metric_rows(from_rows, from_ocr, allowed_metrics=allowed)
    # 每个 metric 只保留一行，item 标注规范名便于追溯
    curated: List[Dict[str, Any]] = []
    for mid, row in sorted(merged.items()):
        row = dict(row)
        aliases = METRIC_ALIASES.get(mid, [mid])
        label = next((a for a in aliases if re.search(r"[\u4e00-\u9fff]", a)), aliases[0])
        row["item"] = label
        curated.append(row)

    existing_genomics = list(patient.get("genomics_raw") or [])
    existing_meta = list(patient.get("_ocr_meta_unsorted") or [])

    patient["lab_results"] = curated
    normalize_ocr_lab_payload(patient)

    if existing_genomics:
        by_gene = {str(g.get("gene_info") or ""): g for g in existing_genomics}
        for g in patient.get("genomics_raw") or []:
            by_gene.setdefault(str(g.get("gene_info") or ""), g)
        patient["genomics_raw"] = list(by_gene.values())
    if existing_meta:
        patient["_ocr_meta_unsorted"] = existing_meta

    attach_lab_observations(patient)

    # 核心字段：文件名 → 癌种/线数/地点（仅补缺失）
    filename_hints = infer_from_filename(pdf_file, source_hint)
    filename_applied = apply_filename_hints(
        patient,
        filename_hints,
        raw_ocr_texts=raw_ocr_texts,
        pdf_file=pdf_file,
        source_hint=source_hint,
    )

    patient["cancer_stage"] = infer_cancer_stage(patient)

    patient["biomarkers"] = extract_biomarkers(patient, raw_ocr_texts)

    name = str(patient.get("name") or "").strip()
    if name in ("性别:", "性别", "") or len(name) <= 2:
        patient["name"] = None

    obs_ids = {o.get("metric_id") for o in patient.get("lab_observations") or []}
    p0 = [m["metric_id"] for m in cl.get("lab_metrics", []) if m.get("priority") == "P0"]
    p1 = [m["metric_id"] for m in cl.get("lab_metrics", []) if m.get("priority") == "P1"]
    missing_p0 = [m for m in p0 if m not in obs_ids]
    missing_p1 = [m for m in p1 if m not in obs_ids]

    report = {
        "checklist_version": cl.get("version"),
        "lab_results_curated_count": len(curated),
        "lab_observations_count": len(obs_ids),
        "lab_observations_present": sorted(obs_ids),
        "missing_p0_metrics": missing_p0,
        "missing_p1_metrics": missing_p1,
        "biomarkers": patient.get("biomarkers") or [],
        "location": patient.get("location"),
        "location_adcode": patient.get("location_adcode"),
        "location_source": patient.get("location_source"),
        "cancer_type": patient.get("cancer_type"),
        "cancer_type_source": patient.get("cancer_type_source"),
        "treatment_lines": patient.get("treatment_lines"),
        "treatment_lines_source": patient.get("treatment_lines_source"),
        "filename_inferred": filename_applied.get("filename_inferred"),
        "filename_fields_applied": filename_applied.get("fields_applied"),
        "filename_conflicts": filename_applied.get("conflicts"),
        "data_quality": summarize_patient_data_quality(patient),
        "genomics_raw_count": len(patient.get("genomics_raw") or []),
        "ocr_meta_count": len(patient.get("_ocr_meta_unsorted") or []),
    }
    patient["_matching_normalize_report"] = report
    return patient, report


def normalize_ocr_envelope(
    envelope: Dict[str, Any],
    *,
    checklist: Optional[Dict[str, Any]] = None,
    source_hint: str = "",
) -> Dict[str, Any]:
    """整理 OCR 输出 envelope（含 patient、raw_ocr_texts）。"""
    patient = envelope.get("patient")
    if not isinstance(patient, dict):
        raise ValueError("envelope 缺少 patient 对象")

    hint = source_hint or str(envelope.get("pdf_file") or "")
    normalize_patient_for_matching(
        patient,
        raw_ocr_texts=envelope.get("raw_ocr_texts") or [],
        source_hint=hint,
        checklist=checklist,
        pdf_file=str(envelope.get("pdf_file") or ""),
    )
    envelope["patient"] = patient
    envelope["_matching_checklist_applied"] = True
    return envelope
