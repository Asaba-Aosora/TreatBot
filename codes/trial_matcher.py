import json
import re
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from codes.lab_lexicon import METRIC_ALIASES as LEXICON_METRICS
from codes.lab_normalize import attach_lab_observations
from codes.lab_rules import evaluate_lab_rule_clauses
from codes.trial_parse import enrich_parsed_conditions

MATCHER_VERSION = "matcher_layers_v1"


def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ''
    return re.sub(r'\s+', '', str(text)).lower()


def split_labels(label_str: Optional[str]) -> List[str]:
    if not label_str:
        return []
    parts = re.split(r'[,，、；;]+', label_str)
    return [part.strip() for part in parts if part.strip()]

LOCATION_COORDS = {
    # 省会 / 直辖市
    '北京': (39.9042, 116.4074),
    '天津': (39.0842, 117.2000),
    '上海': (31.2304, 121.4737),
    '重庆': (29.4316, 106.9123),
    '广州': (23.1291, 113.2644),
    '深圳': (22.5431, 114.0579),
    '杭州': (30.2741, 120.1551),
    '南京': (32.0603, 118.7969),
    '武汉': (30.5928, 114.3055),
    '成都': (30.5728, 104.0668),
    '西安': (34.3416, 108.9398),
    '沈阳': (41.8057, 123.4328),
    '长春': (43.8171, 125.3235),
    '哈尔滨': (45.8038, 126.5349),
    '济南': (36.6512, 117.1201),
    '青岛': (36.0671, 120.3826),
    '郑州': (34.7466, 113.6254),
    '长沙': (28.2282, 112.9388),
    '合肥': (31.8206, 117.2272),
    '福州': (26.0745, 119.2965),
    '南昌': (28.6820, 115.8579),
    '南宁': (22.8170, 108.3669),
    '昆明': (24.8801, 102.8329),
    '贵阳': (26.6470, 106.6302),
    '西宁': (36.6171, 101.7782),
    '兰州': (36.0611, 103.8343),
    '乌鲁木齐': (43.8256, 87.6168),
    '呼和浩特': (40.8170, 111.7652),
    '南通': (31.9802, 120.8943),
    '无锡': (31.5704, 120.2886),
    '常州': (31.8106, 119.9747),
    '苏州': (31.2989, 120.5853),
    '厦门': (24.4798, 118.0894),
    '沈阳': (41.8057, 123.4328),
    '大连': (38.9140, 121.6147),
    '哈尔滨': (45.8038, 126.5349),
    '郑州': (34.7466, 113.6254),
    '济南': (36.6512, 117.1201),
    '长沙': (28.2282, 112.9388),
    '石家庄': (38.0428, 114.5143),
    '太原': (37.8706, 112.5489),
    '南昌': (28.6820, 115.8579),
    '福州': (26.0745, 119.2965),
    '合肥': (31.8206, 117.2272),
    '海南省': (20.0174, 110.3492),
    '河北省': (38.0428, 114.5143),
    '河南省': (34.7655, 113.7536),
    '湖南省': (28.1127, 112.9834),
    '湖北省': (30.5454, 114.3423),
    '山东省': (36.6758, 117.0009),
    '山西省': (37.8570, 112.5492),
    '陕西省': (34.3416, 108.9398),
    '江西省': (28.6742, 115.9100),
    '浙江省': (29.1832, 120.0934),
    '江苏省': (32.0617, 118.7778),
    '安徽省': (31.8612, 117.2857),
    '广东省': (23.1317, 113.2665),
    '广西壮族自治区': (23.8298, 108.7881),
    '云南省': (25.0389, 102.7183),
    '贵州省': (26.5982, 106.7074),
    '四川省': (30.6595, 104.0657),
    '重庆市': (29.4316, 106.9123),
    '天津市': (39.0842, 117.2000),
    '北京市': (39.9042, 116.4074),
    '上海市': (31.2304, 121.4737),
    '内蒙古自治区': (40.8170, 111.7652),
    '宁夏回族自治区': (38.4884, 106.2385),
    '新疆维吾尔自治区': (43.7928, 87.6177),
    '西藏自治区': (29.6520, 91.1721),
    '海南省': (20.0174, 110.3492),
    '青海省': (36.6203, 101.7782),
    '贵州省': (26.5982, 106.7074),
    '甘肃省': (36.0611, 103.8343),
    '辽宁省': (41.2959, 123.1238),
    '吉林省': (43.8965, 125.3268),
    '黑龙江省': (45.7420, 126.6625),
}


def normalize_location_name(name: str) -> str:
    norm = normalize_text(name)
    if not norm:
        return ''
    return re.sub(r'(省|市|自治区|特别行政区|地区|盟|州)$', '', norm)


def find_location_coord(location: str) -> Optional[Tuple[float, float]]:
    if not location:
        return None
    norm = normalize_text(location)
    if not norm:
        return None

    candidates = []
    for name, coord in LOCATION_COORDS.items():
        raw_norm = normalize_text(name)
        stripped = normalize_location_name(name)
        candidates.append((raw_norm, coord))
        if stripped and stripped != raw_norm:
            candidates.append((stripped, coord))

    candidates.sort(key=lambda x: len(x[0]), reverse=True)
    for name_norm, coord in candidates:
        if name_norm and name_norm in norm:
            return coord
    return None


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * asin(min(1, sqrt(a)))
    return r * c


def compute_geo_distance(patient_location: str, province: str, city: str) -> Optional[float]:
    """计算患者位置与试验地点的最短距离（支持多地点试验）"""
    patient_coord = find_location_coord(patient_location)
    if not patient_coord:
        return None
    
    distances = []
    
    # 如果city包含多个地点（用逗号/中文逗号分隔），计算到每个地点的距离
    if city:
        cities = re.split(r'[,，]', city)
        for c in cities:
            c = c.strip()
            if c:
                trial_coord = find_location_coord(c)
                if trial_coord:
                    dist = haversine(patient_coord[0], patient_coord[1], trial_coord[0], trial_coord[1])
                    distances.append(dist)
    
    # 如果没有找到city的坐标，尝试用province
    if not distances and province:
        provinces = re.split(r'[,，]', province)
        for p in provinces:
            p = p.strip()
            if p:
                trial_coord = find_location_coord(p)
                if trial_coord:
                    dist = haversine(patient_coord[0], patient_coord[1], trial_coord[0], trial_coord[1])
                    distances.append(dist)
    
    # 返回最短距离
    return min(distances) if distances else None


def find_nearest_location(patient_location: str, province: str, city: str) -> Optional[Dict]:
    """找出试验中距患者最近的具体地点及距离，用于高亮"""
    patient_coord = find_location_coord(patient_location)
    if not patient_coord:
        return None
    
    nearest = None
    min_dist = float('inf')
    
    # 检查city中的每个地点
    if city:
        cities = re.split(r'[,，]', city)
        for c in cities:
            c = c.strip()
            if c:
                trial_coord = find_location_coord(c)
                if trial_coord:
                    dist = haversine(patient_coord[0], patient_coord[1], trial_coord[0], trial_coord[1])
                    if dist < min_dist:
                        min_dist = dist
                        nearest = {'location': c, 'distance': dist, 'type': 'city'}
    
    # 如果city中没找到，检查province
    if (not nearest or min_dist == float('inf')) and province:
        provinces = re.split(r'[,，]', province)
        for p in provinces:
            p = p.strip()
            if p:
                trial_coord = find_location_coord(p)
                if trial_coord:
                    dist = haversine(patient_coord[0], patient_coord[1], trial_coord[0], trial_coord[1])
                    if dist < min_dist:
                        min_dist = dist
                        nearest = {'location': p, 'distance': dist, 'type': 'province'}
    
    return nearest if nearest and min_dist < float('inf') else None


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
    patient_norm = normalize_text(patient_diag)
    if not patient_norm:
        return False
    for label in trial_labels:
        label_norm = normalize_text(label)
        if not label_norm:
            continue
        if label_norm in patient_norm or patient_norm in label_norm:
            return True
        # use keyword intersection for phrases
        label_words = re.split(r'[\(\)\s/-]', label_norm)
        if any(word and word in patient_norm for word in label_words):
            return True
    return False


def find_matching_labels(patient_diag: str, trial_labels: List[str]) -> List[str]:
    matched = []
    patient_norm = normalize_text(patient_diag)
    if not patient_norm:
        return matched
    for label in trial_labels:
        label_norm = normalize_text(label)
        if not label_norm:
            continue
        if label_norm in patient_norm or patient_norm in label_norm:
            matched.append(label)
            continue
        label_words = re.split(r'[\(\)\s/-]', label_norm)
        if any(word and word in patient_norm for word in label_words):
            matched.append(label)
    return matched


def geo_score(patient_location: str, province: str, city: str) -> Tuple[int, Optional[float]]:
    distance = compute_geo_distance(patient_location, province, city)
    if distance is None:
        patient_norm = normalize_text(patient_location)
        province_norm = normalize_text(province)
        if province_norm and province_norm in patient_norm:
            return 1, None
        return 2, None
    if distance < 50:
        return 0, distance
    if distance < 200:
        return 1, distance
    return 2, distance


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


def match_trial(patient: Dict, trial: Dict) -> Dict:
    if patient.get("lab_results") and not patient.get("lab_observations"):
        attach_lab_observations(patient)

    patient_diag = patient.get('diagnosis') or patient.get('cancer_type') or ''
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
    city_norm = normalize_text(city)
    province_norm = normalize_text(province)
    location_match = False
    if geo_rank in (0, 1):
        location_match = True
    elif patient_norm and (city_norm and city_norm in patient_norm or province_norm and province_norm in patient_norm):
        location_match = True

    # 找出最近的地点（用于HTML高亮）
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

    eligible = bool(disease_match and not exclusion_triggered and lab_pass)

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
        'exclusion_triggered': exclusion_triggered,
        'inclusion_lab_failed': inclusion_lab_failed,
        'checks': checks,
        'next_steps': list(dict.fromkeys(next_steps)),
        'matcher_version': MATCHER_VERSION,
        'geo_rank': geo_rank,
        'geo_distance': geo_distance,
        'nearest_location': nearest_location,
        'semantic_score': semantic_score,
        'score': base_score,
        'reasons': reasons,
        'trial': trial,
    }


def rank_trials(patient: Dict, trials: List[Dict], top_n: int = 20) -> List[Dict]:
    matched = []
    for trial in trials:
        result = match_trial(patient, trial)
        if result['disease_match'] and result.get('eligible', True):
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
