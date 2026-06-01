import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from codes.geo_admin import (
    compute_geo_distance,
    find_nearest_trial_site,
    geo_score,
    parse_trial_site_pairs,
    province_prefix_match,
    resolve_coord,
)
from codes.patient_filename_infer import build_patient_disease_text, normalize_diagnosis_for_matching
from codes.lab_lexicon import METRIC_ALIASES as LEXICON_METRICS
from codes.lab_normalize import attach_lab_observations
from codes.lab_policy import HIGH_RISK_METRICS
from codes.lab_rules import evaluate_lab_rule_clauses
from codes.trial_parse import enrich_parsed_conditions

MATCHER_VERSION = "matcher_layers_v2"

# 患者核心字段：缺失时不硬拒候选，仅标注待医生核对
CORE_FIELD_META: Dict[str, Dict[str, str]] = {
    "age": {"label": "年龄", "missing_msg": "年龄缺失"},
    "gender": {"label": "性别", "missing_msg": "性别缺失"},
    "ecog": {"label": "ECOG", "missing_msg": "ECOG缺失"},
    "treatment_lines": {"label": "治疗线数", "missing_msg": "治疗线数缺失"},
}


def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ''
    return re.sub(r'\s+', '', str(text)).lower()


def split_labels(label_str: Optional[str]) -> List[str]:
    if not label_str:
        return []
    parts = re.split(r'[,，、；;]+', label_str)
    return [part.strip() for part in parts if part.strip()]

def find_location_coord(location: str) -> Optional[Tuple[float, float]]:
    """兼容旧接口：解析地名并返回 (lat, lng)。"""
    return resolve_coord(location)


def find_nearest_location(patient_location: str, province: str, city: str) -> Optional[Dict]:
    """找出试验中距患者最近的具体地点及距离，用于高亮。"""
    return find_nearest_trial_site(patient_location, province, city)


def extract_age(text: str) -> Tuple[Optional[int], Optional[int]]:
    sentences = re.split(r'[，。；\n]', text)
    for sent in sentences:
        sent_clean = re.sub(r'^\s*\d+[、.\s)]*', '', sent).strip()
        sent_clean = re.sub(r'[\(（][^\)）]*[\)）]', '', sent_clean).strip()
        if not re.search(r'年龄|年满|岁|周岁', sent_clean):
            continue
        m = re.search(r'[≥>]?\s*(\d+)\s*(?:岁|周岁)?\s*[且并、至～~-]\s*[≤<]?\s*(\d+)', sent_clean)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.search(r'[≥>]\s*(\d+)', sent_clean)
        if m:
            return int(m.group(1)), None
        m = re.search(r'[≤<]\s*(\d+)', sent_clean)
        if m:
            return None, int(m.group(1))
        m = re.search(r'(\d+)\s*岁', sent_clean)
        if m:
            return int(m.group(1)), None
    return None, None


def extract_gender(text: str) -> Optional[str]:
    sentences = re.split(r'[。；！？\n]', text)
    for sent in sentences[:3]:
        if '性别不限' in sent or '男女不限' in sent or '男性或女性' in sent:
            return '不限'
        if '男性' in sent and '女性' not in sent:
            return '男'
        if '女性' in sent and '男性' not in sent:
            return '女'
    if re.search(r'性别不限|男女不限', text):
        return '不限'
    if re.search(r'男性', text) and re.search(r'女性', text):
        return None
    if re.search(r'男性', text):
        return '男'
    if re.search(r'女性', text):
        return '女'
    return None


def extract_ecog(text: str) -> Tuple[Optional[int], Optional[int]]:
    sentences = re.split(r'[。；\n]', text)
    for sent in sentences:
        if not re.search(r'ECOG|东部肿瘤协作组', sent):
            continue
        sent_clean = re.sub(r'^\s*\d+[、.\s)]*', '', sent).strip()
        m = re.search(r'(\d+)\s*[或/]\s*(\d+)', sent_clean)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return min(a, b), max(a, b)
        m = re.search(r'(\d+)\s*[～~\-到]\s*(\d+)', sent_clean)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return min(a, b), max(a, b)
        m = re.search(r'[≤<]\s*(\d+)', sent_clean)
        if m:
            max_val = int(m.group(1))
            return 0, max_val
        m = re.search(r'[≥>]\s*(\d+)', sent_clean)
        if m:
            min_val = int(m.group(1))
            return min_val, 5
        m = re.search(r'(\d+)', sent_clean)
        if m:
            num = int(m.group(1))
            return 0, num
    return None, None


def extract_lines_min(text: str) -> Optional[int]:
    if not isinstance(text, str):
        return None
    chinese_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}

    def to_int(s: str) -> Optional[int]:
        if s in chinese_map:
            return chinese_map[s]
        try:
            return int(s)
        except Exception:
            return None

    range_arabic = re.compile(r'(\d+)\s*[至~-]\s*\d+\s*(?:线|L)', re.IGNORECASE)
    range_chinese = re.compile(r'([一二三四五六七八九十])\s*[至~-]\s*[一二三四五六七八九十]\s*(?:线|L)', re.IGNORECASE)
    single_mod_arabic = re.compile(r'(?:≥|>|至少|不少于|不低于)\s*(\d+)\s*(?:线|L)', re.IGNORECASE)
    single_mod_chinese = re.compile(r'(?:≥|>|至少|不少于|不低于)\s*([一二三四五六七八九十])\s*(?:线|L)', re.IGNORECASE)
    single_plain_arabic = re.compile(r'(\d+)\s*(?:线|L)', re.IGNORECASE)
    single_plain_chinese = re.compile(r'([一二三四五六七八九十])\s*(?:线|L)', re.IGNORECASE)

    candidates: List[int] = []
    for pattern in [range_arabic, range_chinese, single_mod_arabic, single_mod_chinese]:
        for match in pattern.findall(text):
            num_str = match[0] if isinstance(match, tuple) else match
            num = to_int(num_str)
            if num is not None:
                candidates.append(num)
    if candidates:
        return min(candidates)
    for pattern in [single_plain_arabic, single_plain_chinese]:
        for num_str in pattern.findall(text):
            num = to_int(num_str)
            if num is not None and num >= 2:
                candidates.append(num)
    return min(candidates) if candidates else None


LAB_ITEM_ALIASES = {
    "白细胞": ["白细胞", "wbc", "white blood cell"],
    "中性粒细胞": ["中性粒细胞", "anc", "neutrophil"],
    "血小板": ["血小板", "plt", "platelet"],
    "血红蛋白": ["血红蛋白", "hb", "hemoglobin"],
    "总胆红素": ["总胆红素", "tbil", "bilirubin"],
    "肌酐": ["肌酐", "creatinine", "cr"],
    "alt": ["alt", "谷丙转氨酶"],
    "ast": ["ast", "谷草转氨酶"],
}


def _normalize_lab_name(name: str) -> str:
    n = normalize_text(name)
    for canonical, aliases in LAB_ITEM_ALIASES.items():
        if any(normalize_text(alias) in n for alias in aliases):
            return canonical
    return n


def extract_lab_requirements(text: str) -> Dict[str, Dict[str, Optional[float]]]:
    reqs: Dict[str, Dict[str, Optional[float]]] = {}
    for canonical, aliases in LAB_ITEM_ALIASES.items():
        alias_pattern = "|".join(re.escape(alias) for alias in aliases)
        # 示例: 白细胞 >=3.0, 肌酐 < 1.5
        for match in re.finditer(rf"(?:{alias_pattern}).{{0,10}}([<>≤≥]=?)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE):
            op = match.group(1)
            val = float(match.group(2))
            item_req = reqs.setdefault(canonical, {"min": None, "max": None})
            if op in (">", ">=", "≥"):
                item_req["min"] = max(item_req["min"], val) if item_req["min"] is not None else val
            elif op in ("<", "<=", "≤"):
                item_req["max"] = min(item_req["max"], val) if item_req["max"] is not None else val
    return reqs


def _safe_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _metric_id_to_legacy_lab_key(metric_id: str) -> str:
    for alias in LEXICON_METRICS.get(metric_id, []):
        if any("\u4e00" <= ch <= "\u9fff" for ch in alias):
            return alias
    return metric_id


def evaluate_lab_requirements(
    patient: Dict, lab_requirements: Dict[str, Dict[str, Optional[float]]]
) -> Tuple[bool, List[str], List[str]]:
    """返回 (无明确数值违反, 违反说明列表, 缺失指标列表)。缺失不视为硬失败。"""
    if not lab_requirements:
        return True, [], []
    patient_labs = patient.get("lab_results") or []
    patient_map = {}
    for item in patient_labs:
        lab_name = _normalize_lab_name(item.get("item", ""))
        patient_map[lab_name] = _safe_float(item.get("value"))
    for obs in patient.get("lab_observations") or []:
        mid = obs.get("metric_id")
        v = obs.get("value_num")
        if mid and isinstance(v, (int, float)):
            key = _normalize_lab_name(_metric_id_to_legacy_lab_key(str(mid)))
            if key not in patient_map or patient_map[key] is None:
                patient_map[key] = float(v)

    violations: List[str] = []
    missing: List[str] = []
    for key, req in lab_requirements.items():
        value = patient_map.get(key)
        if value is None:
            missing.append(key)
            continue
        req_min = req.get("min")
        req_max = req.get("max")
        if req_min is not None and value < req_min:
            violations.append(f"{key}低于阈值({value} < {req_min})")
        if req_max is not None and value > req_max:
            violations.append(f"{key}高于阈值({value} > {req_max})")
    return len(violations) == 0, violations, missing


def _tokenize_for_semantic(text: str) -> List[str]:
    norm = normalize_text(text)
    if not norm:
        return []
    return [norm[i : i + 2] for i in range(max(0, len(norm) - 1))]


def semantic_similarity(query: str, text: str) -> float:
    q_tokens = set(_tokenize_for_semantic(query))
    t_tokens = set(_tokenize_for_semantic(text))
    if not q_tokens or not t_tokens:
        return 0.0
    inter = len(q_tokens & t_tokens)
    union = len(q_tokens | t_tokens)
    return inter / union if union else 0.0


def simple_label_match(patient_diag: str, trial_labels: List[str]) -> bool:
    return bool(find_matching_labels(patient_diag, trial_labels))


def find_matching_labels(patient_diag: str, trial_labels: List[str]) -> List[str]:
    matched: List[str] = []
    patient_norm = normalize_diagnosis_for_matching(patient_diag)
    if not patient_norm:
        return matched
    for label in trial_labels:
        label_norm = normalize_text(label)
        if not label_norm:
            continue
        label_canon = normalize_diagnosis_for_matching(label)
        if label_canon and (label_canon in patient_norm or patient_norm in label_canon):
            matched.append(label)
            continue
        if label_norm in patient_norm or patient_norm in label_norm:
            matched.append(label)
            continue
        label_words = re.split(r"[\(\)\s/-]", label_norm)
        if any(
            _label_token_valid(word) and word in patient_norm
            for word in label_words
        ):
            matched.append(label)
    return matched


def _label_token_valid(token: str) -> bool:
    if not token:
        return False
    if re.fullmatch(r"[a-zA-Z]+", token):
        return len(token) >= 2
    if re.fullmatch(r"\d+", token):
        return False
    return len(token) >= 1


def parse_trial_condition(trial: Dict) -> Dict:
    text = trial.get('入组条件', '') or ''
    age_min, age_max = extract_age(text)
    gender = extract_gender(text)
    ecog_min, ecog_max = extract_ecog(text)
    treatment_lines_min = extract_lines_min(text)
    lab_requirements = extract_lab_requirements(text)

    return {
        'age_min': age_min,
        'age_max': age_max,
        'gender': gender,
        'ecog_min': ecog_min,
        'ecog_max': ecog_max,
        'treatment_lines_min': treatment_lines_min,
        'lab_requirements': lab_requirements,
    }


def load_trials(json_path: str) -> List[Dict]:
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"试验数据文件不存在: {json_path}")
    with path.open('r', encoding='utf-8') as f:
        trials = json.load(f)

    for trial in trials:
        base = parse_trial_condition(trial)
        trial["parsed_conditions"] = enrich_parsed_conditions(trial, base)
        trial['labels'] = split_labels(trial.get('疾病三级标签', ''))
    return trials


def match_trial(patient: Dict, trial: Dict, match_mode: str = "strict") -> Dict:
    if patient.get("lab_results") and not patient.get("lab_observations"):
        attach_lab_observations(patient)

    patient_diag = build_patient_disease_text(patient)
    labels = trial.get('labels', [])
    matching_labels = find_matching_labels(patient_diag, labels)
    disease_match = bool(matching_labels)

    condition = trial.get('parsed_conditions', {})
    age_pass = True
    gender_pass = True
    ecog_pass = True
    treatment_lines_pass = True
    lab_pass = True
    reasons: List[str] = []
    checks: List[Dict[str, Any]] = []
    next_steps: List[str] = []
    exclusion_triggered = False
    inclusion_lab_failed = False
    unknown_penalty = 0.0

    age = patient.get('age')
    if age is not None:
        if condition['age_min'] is not None and age < condition['age_min']:
            age_pass = False
            reasons.append(f"年龄低于{condition['age_min']}")
        if condition['age_max'] is not None and age > condition['age_max']:
            age_pass = False
            reasons.append(f"年龄高于{condition['age_max']}")

    gender = patient.get('gender')
    if gender and condition['gender'] and condition['gender'] != '不限':
        if normalize_text(gender) != normalize_text(condition['gender']):
            gender_pass = False
            reasons.append(f"性别要求{condition['gender']}")

    ecog = patient.get('ecog')
    if ecog is not None and condition['ecog_min'] is not None and condition['ecog_max'] is not None:
        if ecog < condition['ecog_min'] or ecog > condition['ecog_max']:
            ecog_pass = False
            reasons.append(f"ECOG不在{condition['ecog_min']}~{condition['ecog_max']}范围")

    treatment_lines = patient.get('treatment_lines')
    if treatment_lines is not None and condition['treatment_lines_min'] is not None:
        if treatment_lines < condition['treatment_lines_min']:
            treatment_lines_pass = False
            reasons.append(f"治疗线数低于{condition['treatment_lines_min']}线")

    inc_clauses = condition.get("inclusion_lab_clauses") or []
    exc_clauses = condition.get("exclusion_lab_clauses") or []
    if inc_clauses or exc_clauses:
        checks, inclusion_lab_failed, exclusion_triggered, nxt = evaluate_lab_rule_clauses(
            patient, inc_clauses, exc_clauses
        )
        next_steps.extend(nxt)
        unknown_penalty = sum(1 for c in checks if c.get("status") == "unknown") * 2.0
        lab_fail_count = sum(
            1
            for c in checks
            if c.get("field") == "inclusion" and c.get("status") == "fail"
        )
        reasons.extend(c.get("message", "") for c in checks if c.get("status") == "fail")
        lab_pass = not inclusion_lab_failed and not exclusion_triggered
    else:
        lab_ok, violations, missing = evaluate_lab_requirements(
            patient, condition.get("lab_requirements", {})
        )
        lab_pass = lab_ok
        reasons.extend(violations)
        unknown_penalty = len(missing) * 2.0
        next_steps.extend(missing)
        for m in missing:
            checks.append(
                {
                    "metric_id": m,
                    "field": "inclusion",
                    "status": "unknown",
                    "message": f"缺少化验指标: {m}",
                }
            )
        lab_fail_count = len(violations)

    # 评分逻辑：疾病匹配是基础，不匹配则暂不推荐。
    base_score = 0.0
    if disease_match:
        base_score += 50
    if age_pass:
        base_score += 10
    if gender_pass:
        base_score += 5
    if ecog_pass:
        base_score += 10
    if treatment_lines_pass:
        base_score += 10
    if lab_pass:
        base_score += 10
    base_score -= unknown_penalty

    location = patient.get('location')
    province = trial.get('研究中心所在省份', '')
    city = trial.get('研究中心所在城市', '')
    geo_rank, geo_distance = geo_score(location, province, city)
    if geo_rank == 0:
        base_score += 8
    elif geo_rank == 1:
        base_score += 5
    elif geo_rank == 2:
        base_score += 2

    patient_norm = normalize_text(location)
    location_match = geo_rank in (0, 1)
    if not location_match and location:
        for prov, cit in parse_trial_site_pairs(province, city):
            if cit and normalize_text(cit) in patient_norm:
                location_match = True
                break
            if prov and province_prefix_match(location, prov):
                location_match = True
                break

    nearest_location = find_nearest_location(location, province, city)

    patient_semantic_text = " ".join(
        str(v)
        for v in [
            patient.get("diagnosis", ""),
            patient.get("cancer_stage", ""),
            " ".join(patient.get("biomarkers", []) or []),
            " ".join(
                str(o.get("metric_id", ""))
                for o in (patient.get("lab_observations") or [])
            )
            or " ".join(item.get("item", "") for item in (patient.get("lab_results") or [])),
        ]
    )
    trial_semantic_text = " ".join(
        [
            trial.get("入组条件", "") or "",
            trial.get("排除条件", "") or "",
            " ".join(labels),
        ]
    )
    semantic_score = semantic_similarity(patient_semantic_text, trial_semantic_text)
    base_score += semantic_score * 15.0

    mode = (match_mode or "strict").strip().lower()
    if mode not in ("strict", "balanced"):
        mode = "strict"

    age_required_but_missing = condition.get("age_min") is not None and age is None
    gender_required_but_missing = (
        condition.get("gender") not in (None, "", "不限") and not gender
    )
    ecog_required_but_missing = (
        (condition.get("ecog_min") is not None or condition.get("ecog_max") is not None)
        and ecog is None
    )
    lines_required_but_missing = (
        condition.get("treatment_lines_min") is not None and treatment_lines is None
    )

    missing_core_fields: List[str] = []
    if age_required_but_missing:
        missing_core_fields.append("age")
    if gender_required_but_missing:
        missing_core_fields.append("gender")
    if ecog_required_but_missing:
        missing_core_fields.append("ecog")
    if lines_required_but_missing:
        missing_core_fields.append("treatment_lines")

    for field in missing_core_fields:
        msg = CORE_FIELD_META.get(field, {}).get("missing_msg") or f"{field}缺失"
        next_steps.append(msg)

    missing_core_penalty = len(missing_core_fields) * 3.0
    base_score -= missing_core_penalty

    hard_rule_pass = (
        age_pass
        and gender_pass
        and ecog_pass
        and treatment_lines_pass
        and lab_pass
        and not exclusion_triggered
    )

    if mode == "strict":
        lab_gate = lab_pass and not exclusion_triggered
    else:
        # 平衡模式：允许最多 1 条入组化验 fail，便于后续人工复核。
        lab_gate = (not exclusion_triggered) and (lab_pass or lab_fail_count <= 1)

    # 已知数值违反或排除/化验硬失败 → 不进入候选列表
    hard_excluded = bool(
        exclusion_triggered
        or (age is not None and not age_pass)
        or (gender and not gender_pass)
        or (ecog is not None and not ecog_pass)
        or (treatment_lines is not None and not treatment_lines_pass)
        or not lab_gate
    )

    # 可确认入选：已知规则全过且无待补核心字段（供医生核对后使用）
    eligible = bool(
        disease_match
        and hard_rule_pass
        and lab_gate
        and not missing_core_fields
    )
    needs_review = bool(missing_core_fields) or any(
        c.get("status") == "unknown" for c in checks
    )

    review_items: List[Dict[str, Any]] = []
    for field in missing_core_fields:
        msg = CORE_FIELD_META.get(field, {}).get("missing_msg") or f"{field}缺失"
        review_items.append(
            {
                "metric_id": field,
                "status": "unknown",
                "priority": "p0",
                "is_high_risk": False,
                "field": "patient",
                "message": msg,
                "evidence": "",
                "decision_reason_code": "core_field_missing",
            }
        )
    for check in checks:
        status = check.get("status")
        metric_id = str(check.get("metric_id") or "")
        if status not in ("fail", "unknown"):
            continue
        is_high_risk = metric_id in HIGH_RISK_METRICS
        priority = "p0" if (status == "fail" and is_high_risk) else ("p1" if is_high_risk else "p2")
        review_items.append(
            {
                "metric_id": metric_id,
                "status": status,
                "priority": priority,
                "is_high_risk": is_high_risk,
                "field": check.get("field"),
                "message": check.get("message", ""),
                "evidence": check.get("evidence", ""),
                "decision_reason_code": check.get("decision_reason_code", ""),
            }
        )

    return {
        'trial_id': trial.get('项目编码'),
        'trial_name': trial.get('项目名称') or trial.get('研究中心所在医院') or trial.get('研究中心所在城市'),
        'disease_match': disease_match,
        'matching_labels': matching_labels,
        'location_match': location_match,
        'age_pass': age_pass,
        'gender_pass': gender_pass,
        'ecog_pass': ecog_pass,
        'treatment_lines_pass': treatment_lines_pass,
        'lab_pass': lab_pass,
        'eligible': eligible,
        'hard_excluded': hard_excluded,
        'needs_review': needs_review,
        'missing_core_fields': missing_core_fields,
        'missing_core_messages': [
            CORE_FIELD_META.get(f, {}).get("missing_msg") or f"{f}缺失"
            for f in missing_core_fields
        ],
        'exclusion_triggered': exclusion_triggered,
        'inclusion_lab_failed': inclusion_lab_failed,
        'checks': checks,
        'next_steps': list(dict.fromkeys(next_steps)),
        'matcher_version': MATCHER_VERSION,
        'match_mode': mode,
        'geo_rank': geo_rank,
        'geo_distance': geo_distance,
        'nearest_location': nearest_location,
        'semantic_score': semantic_score,
        'score': base_score,
        'reasons': reasons,
        'review_items': review_items,
        'trial': trial,
    }


def rank_trials(
    patient: Dict, trials: List[Dict], top_n: int = 20, match_mode: str = "strict"
) -> List[Dict]:
    matched = []
    for trial in trials:
        result = match_trial(patient, trial, match_mode=match_mode)
        if result["disease_match"] and not result.get("hard_excluded", False):
            matched.append(result)

    matched.sort(key=lambda x: (-x['score'], x['geo_rank'], x.get('geo_distance', 99999)))
    return matched[:top_n]


def build_patient_input(
    diagnosis: str,
    age: Optional[int] = None,
    gender: Optional[str] = None,
    ecog: Optional[int] = None,
    treatment_lines: Optional[int] = None,
    location: Optional[str] = None,
    cancer_stage: Optional[str] = None,
    biomarkers: Optional[List[str]] = None,
) -> Dict:
    return {
        'diagnosis': diagnosis,
        'age': age,
        'gender': gender,
        'ecog': ecog,
        'treatment_lines': treatment_lines,
        'location': location,
        'cancer_stage': cancer_stage,
        'biomarkers': biomarkers or [],
    }


def summarize_patient_data_quality(patient: Dict) -> Dict[str, Any]:
    labs = patient.get("lab_results") or []
    observations = patient.get("lab_observations") or []
    genomics = patient.get("genomics_raw") or []
    meta_rows = patient.get("_ocr_meta_unsorted") or []
    unknown_status = sum(
        1 for row in labs if str(row.get("status", "") or "") == "无法判断"
    )
    missing_core = [
        field
        for field in ("diagnosis", "age", "gender", "ecog", "treatment_lines", "location")
        if not patient.get(field)
    ]
    missing_core_labels = [
        CORE_FIELD_META[f]["missing_msg"]
        for f in missing_core
        if f in CORE_FIELD_META
    ]
    if "diagnosis" in missing_core:
        missing_core_labels.insert(0, "诊断缺失")
    if "location" in missing_core:
        missing_core_labels.append("地理位置缺失")
    return {
        "lab_rows_total": len(labs),
        "lab_observations_total": len(observations),
        "genomics_rows_total": len(genomics),
        "meta_rows_total": len(meta_rows),
        "unknown_status_rows": unknown_status,
        "missing_core_fields": missing_core,
        "missing_core_labels": missing_core_labels,
    }


def build_review_queue(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    queue: List[Dict[str, Any]] = []
    for item in matches or []:
        for review in item.get("review_items") or []:
            queue.append(
                {
                    "trial_id": item.get("trial_id"),
                    "trial_name": item.get("trial_name"),
                    "score": item.get("score"),
                    **review,
                }
            )
    prio_rank = {"p0": 0, "p1": 1, "p2": 2}
    queue.sort(key=lambda x: (prio_rank.get(str(x.get("priority")), 9), -float(x.get("score") or 0.0)))
    return queue


def rank_trials_with_vector(
    patient: Dict,
    trials: List[Dict],
    vector_searcher,
    top_n: int = 20,
    match_mode: str = "strict",
    rule_weight: float = 0.7,
    vector_weight: float = 0.3,
) -> List[Dict]:
    """
    融合规则匹配和向量语义匹配进行试验排序
    
    Args:
        patient: 患者信息
        trials: 试验列表
        vector_searcher: VectorSearcher 实例（加载好的 Faiss 索引）
        top_n: 返回前 n 个结果
        match_mode: "strict" 或 "balanced"
        rule_weight: 规则分数权重（默认 0.7）
        vector_weight: 向量分数权重（默认 0.3）
    
    Returns:
        按融合分数排序的试验列表，包含规则分数和向量分数
    """
    
    # 1. 向量检索：获取语义相似的候选试验
    patient_text = " ".join(
        str(v)
        for v in [
            patient.get("diagnosis", ""),
            patient.get("cancer_stage", ""),
            " ".join(patient.get("biomarkers", []) or []),
        ]
    )
    
    if not patient_text.strip():
        # 如果没有足够的患者信息，回退到纯规则匹配
        return rank_trials(patient, trials, top_n, match_mode)
    
    # 获取向量检索结果
    vector_results = vector_searcher.search(patient_text, top_k=min(40, len(trials)))
    vector_trial_ids = {item['trial_id']: item['vector_score'] for item in vector_results}
    
    # 2. 确定要评估的候选试验（向量检索 top_k 或所有试验）
    candidates_to_evaluate = []
    
    # 优先评估向量检索的 top_k 候选
    for trial in trials:
        trial_id = trial.get('项目编码')
        if trial_id in vector_trial_ids:
            candidates_to_evaluate.append(trial)
    
    # 如果向量检索结果不足，补充其他试验（最多到原来的两倍）
    if len(candidates_to_evaluate) < min(80, len(trials)):
        other_trials = [t for t in trials if t.get('项目编码') not in vector_trial_ids]
        candidates_to_evaluate.extend(other_trials[:min(80 - len(candidates_to_evaluate), len(other_trials))])
    
    # 3. 对候选试验进行规则匹配
    matched = []
    for trial in candidates_to_evaluate:
        result = match_trial(patient, trial, match_mode=match_mode)
        
        # 添加向量分数
        trial_id = trial.get('项目编码')
        vector_score = vector_trial_ids.get(trial_id, 0.0)
        result['vector_score'] = vector_score
        
        # 计算融合分数
        rule_score = result['score'] / 100.0  # 归一化规则分数
        fused_score = rule_score * rule_weight + vector_score * vector_weight
        result['fused_score'] = fused_score
        
        if result["disease_match"] and not result.get("hard_excluded", False):
            matched.append(result)
    
    # 4. 按融合分数排序
    matched.sort(
        key=lambda x: (-x['fused_score'], -x['vector_score'], x['geo_rank'], x.get('geo_distance', 99999))
    )
    
    return matched[:top_n]
