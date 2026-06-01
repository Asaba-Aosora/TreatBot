"""从 PDF/JSON 文件名推断癌种、治疗线数等（业务命名约定）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from codes.geo_admin import apply_location_to_patient, infer_patient_location

# 与试验库「疾病三级标签」对齐；长词优先匹配
CANCER_TYPES: List[str] = [
    "胃食管结合部癌",
    "非鳞状非小细胞肺癌",
    "鳞状非小细胞肺癌",
    "肝内胆管癌",
    "肝外胆管癌",
    "弥漫大B细胞淋巴瘤",
    "外周T细胞淋巴瘤",
    "T/NK细胞淋巴瘤",
    "小细胞肺癌",
    "肝细胞癌",
    "前列腺癌",
    "乳腺癌",
    "卵巢癌",
    "宫颈癌",
    "食管癌",
    "胰腺癌",
    "胆管癌",
    "胆道癌",
    "结肠癌",
    "直肠癌",
    "结直肠癌",
    "胃癌",
    "肺癌",
    "肝癌",
    "肾癌",
    "膀胱癌",
    "黑色素瘤",
    "胶质瘤",
    "淋巴瘤",
    "白血病",
    "间皮瘤",
    "胸腺癌",
    "甲状腺癌",
    "鼻咽癌",
    "口咽癌",
    "脑膜瘤",
]

LINE_MAP: Dict[str, int] = {
    "一线": 1,
    "二线": 2,
    "三线": 3,
    "四线": 4,
    "五线": 5,
    "1线": 1,
    "2线": 2,
    "3线": 3,
    "4线": 4,
    "5线": 5,
}

CANCER_SYNONYMS: Dict[str, str] = {
    "胃恶性肿瘤": "胃癌",
    "胃腺癌": "胃癌",
    "胰恶性肿瘤": "胰腺癌",
    "胰腺恶性肿瘤": "胰腺癌",
    "肝恶性肿瘤": "肝癌",
    "肺恶性肿瘤": "肺癌",
    "结直肠恶性肿瘤": "结直肠癌",
    "直肠恶性肿瘤": "直肠癌",
    "结肠恶性肿瘤": "结肠癌",
    "胆道恶性肿瘤": "胆道癌",
    "胆管恶性肿瘤": "胆管癌",
}

_FILENAME_SUFFIXES = (
    "_患者信息_fixed_matching",
    "_患者信息_matching",
    "_患者信息_fixed",
    "_患者信息",
    "_fixed_matching",
    "_matching",
    "_fixed",
)


@dataclass
class FilenameHints:
    cancer_type: Optional[str] = None
    treatment_lines: Optional[int] = None
    location_display: Optional[str] = None
    raw_stem: str = ""
    source: str = "filename"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cancer_type": self.cancer_type,
            "treatment_lines": self.treatment_lines,
            "location_display": self.location_display,
            "raw_stem": self.raw_stem,
            "source": self.source,
            "notes": self.notes,
        }


def clean_filename_stem(name: str) -> str:
    stem = Path(str(name or "")).stem
    for suffix in _FILENAME_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem.strip()


def _strip_patient_code(stem: str) -> str:
    """去掉 CHQI / HAQI 等内部前缀码。"""
    return re.sub(r"^[A-Za-z]{2,6}\d*", "", stem).strip()


def infer_from_filename(*names: str) -> FilenameHints:
    hints = FilenameHints()
    for name in names:
        if not name:
            continue
        stem = _strip_patient_code(clean_filename_stem(name))
        if not stem:
            continue
        hints.raw_stem = stem
        hints.source = "filename"

        for cancer in sorted(CANCER_TYPES, key=len, reverse=True):
            if cancer in stem:
                hints.cancer_type = cancer
                stem = stem.replace(cancer, "", 1)
                break

        for label, num in sorted(LINE_MAP.items(), key=lambda x: -len(x[0])):
            if label in stem:
                hints.treatment_lines = num
                hints.notes.append(f"文件名含「{label}」→ treatment_lines={num}")
                stem = stem.replace(label, "", 1)
                break

        loc = infer_patient_location({}, source_hint=stem, pdf_file="")
        if loc.display:
            hints.location_display = loc.display

        if hints.cancer_type or hints.treatment_lines or hints.location_display:
            break
    return hints


def canonicalize_cancer_name(text: str) -> str:
    if not text:
        return ""
    result = str(text).strip()
    for src, dst in sorted(CANCER_SYNONYMS.items(), key=lambda x: -len(x[0])):
        result = result.replace(src, dst)
    return result


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def normalize_diagnosis_for_matching(text: str) -> str:
    """去掉 TNM/KPS 等噪声并做癌种同义词规范化，供疾病标签匹配。"""
    if not text:
        return ""
    s = str(text)
    s = re.sub(r"TXNXM\d+", " ", s, flags=re.I)
    s = re.sub(r"\bT[0-9Xx][cC]?[Nn][0-9Xx][Mm][0-9Xx]\b", " ", s)
    s = re.sub(r"KPS\s*\d+\s*分?", " ", s, flags=re.I)
    s = re.sub(r"NRS\s*\d+", " ", s, flags=re.I)
    s = canonicalize_cancer_name(s)
    s = re.sub(r"\s+", "", s)
    return _normalize_text(s)


def build_patient_disease_text(patient: Dict[str, Any]) -> str:
    parts: List[str] = []
    if patient.get("cancer_type"):
        parts.append(str(patient["cancer_type"]))
    if patient.get("diagnosis"):
        parts.append(str(patient["diagnosis"]))
    combined = " ".join(parts)
    return _normalize_text(combined) if combined else ""


def _label_token_valid(token: str) -> bool:
    if not token:
        return False
    if re.fullmatch(r"[a-zA-Z]+", token):
        return len(token) >= 2
    if re.fullmatch(r"\d+", token):
        return False
    return len(token) >= 1


def apply_filename_hints(
    patient: Dict[str, Any],
    hints: FilenameHints,
    *,
    raw_ocr_texts: Optional[List[str]] = None,
    pdf_file: str = "",
    source_hint: str = "",
) -> Dict[str, Any]:
    """将文件名推断写入 patient（仅补缺失；冲突写入 notes）。"""
    applied: Dict[str, Any] = {"filename_inferred": hints.to_dict(), "fields_applied": []}
    conflicts: List[str] = []

    if hints.cancer_type:
        existing = patient.get("cancer_type")
        if not existing:
            patient["cancer_type"] = hints.cancer_type
            patient["cancer_type_source"] = "filename"
            applied["fields_applied"].append("cancer_type")
        elif str(existing) != hints.cancer_type:
            conflicts.append(f"cancer_type: OCR/已有={existing}, 文件名={hints.cancer_type}")

    if hints.treatment_lines is not None and patient.get("treatment_lines") is None:
        patient["treatment_lines"] = hints.treatment_lines
        patient["treatment_lines_source"] = "filename"
        applied["fields_applied"].append("treatment_lines")

    apply_location_to_patient(
        patient,
        source_hint=source_hint,
        raw_ocr_texts=raw_ocr_texts,
        pdf_file=pdf_file,
    )
    if hints.location_display and patient.get("location_source") == "filename":
        applied["fields_applied"].append("location")

    if conflicts:
        applied["conflicts"] = conflicts
    return applied
