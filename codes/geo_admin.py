"""中国行政区划解析与地理距离（cpca + 民政部 adcode 坐标）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cpca
import pandas as pd

Coord = Tuple[float, float]

MATCH_LEVEL_LABELS = {
    0: "同市",
    1: "同省",
    2: "邻省",
    3: "较远",
}

# 省级 adcode 前 2 位邻接关系（用于地理排序，非精确距离）
NEIGHBOR_PROVINCE_PREFIXES: Dict[str, frozenset] = {
    "11": frozenset({"12", "13"}),
    "12": frozenset({"11", "13"}),
    "13": frozenset({"11", "12", "14", "15", "21", "37", "41"}),
    "14": frozenset({"13", "15", "61", "41", "37"}),
    "15": frozenset({"14", "13", "21", "22", "23", "61", "62", "64"}),
    "21": frozenset({"13", "15", "22", "23"}),
    "22": frozenset({"15", "21", "23"}),
    "23": frozenset({"15", "22", "21"}),
    "31": frozenset({"32", "33"}),
    "32": frozenset({"31", "33", "34", "37"}),
    "33": frozenset({"31", "32", "34", "36", "35"}),
    "34": frozenset({"32", "33", "37", "41", "42"}),
    "35": frozenset({"33", "36", "43", "44"}),
    "36": frozenset({"33", "34", "42", "43", "44"}),
    "37": frozenset({"13", "14", "32", "34", "41"}),
    "41": frozenset({"13", "14", "37", "34", "42", "43", "61"}),
    "42": frozenset({"34", "36", "41", "43", "50", "52"}),
    "43": frozenset({"35", "36", "42", "44", "45", "52", "50"}),
    "44": frozenset({"35", "36", "43", "45", "46"}),
    "45": frozenset({"43", "44", "52", "53"}),
    "46": frozenset({"44"}),
    "50": frozenset({"42", "43", "51", "52", "61"}),
    "51": frozenset({"50", "52", "53", "61", "62", "54"}),
    "52": frozenset({"42", "43", "45", "50", "51", "53", "61"}),
    "53": frozenset({"45", "51", "52"}),
    "54": frozenset({"51", "62", "63", "65"}),
    "61": frozenset({"14", "15", "41", "50", "51", "52", "62", "64"}),
    "62": frozenset({"51", "54", "61", "63", "64", "65"}),
    "63": frozenset({"54", "62", "65"}),
    "64": frozenset({"15", "61", "62", "65"}),
    "65": frozenset({"54", "62", "63", "64"}),
}


@dataclass
class GeoMatchResult:
    geo_rank: int = 3
    geo_distance: Optional[float] = None
    nearest_location: Optional[Dict[str, Any]] = None
    match_level: str = "较远"
    matched_centers: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LocationInfo:
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    adcode: Optional[str] = None
    display: str = ""
    source: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "province": self.province,
            "city": self.city,
            "district": self.district,
            "adcode": self.adcode,
            "display": self.display,
            "source": self.source,
            "lat": self.lat,
            "lng": self.lng,
        }


def _is_valid_cell(val: Any) -> bool:
    if val is None:
        return False
    s = str(val).strip()
    return bool(s) and s.lower() not in ("nan", "none")


def normalize_adcode(adcode: Any) -> Optional[str]:
    if not _is_valid_cell(adcode):
        return None
    s = str(adcode).strip()
    if "." in s:
        s = s.split(".")[0]
    return s.zfill(6)[:6]


def adcode_storage_key(adcode: Any) -> Optional[str]:
    code = normalize_adcode(adcode)
    if not code:
        return None
    return code + "000000"


def adcode_specificity(adcode: Optional[str]) -> int:
    """数值越大越具体：省(1) < 市(2) < 区县(3)。"""
    code = normalize_adcode(adcode)
    if not code:
        return 0
    if code[4:6] != "00":
        return 3
    if code[2:4] != "00":
        return 2
    return 1


@lru_cache(maxsize=1)
def _load_adcode_coords() -> Dict[str, Coord]:
    adc_path = Path(cpca.__file__).parent / "resources" / "adcodes.csv"
    df = pd.read_csv(adc_path)
    out: Dict[str, Coord] = {}
    for _, row in df.iterrows():
        if not _is_valid_cell(row.get("adcode")):
            continue
        key = str(int(row["adcode"])).zfill(12)
        out[key] = (float(row["latitude"]), float(row["longitude"]))
    return out


def get_coord_by_adcode(adcode: Optional[str]) -> Optional[Coord]:
    key = adcode_storage_key(adcode)
    if not key:
        return None
    coords = _load_adcode_coords()
    if key in coords:
        return coords[key]
    prov_key = key[:2] + "0000000000"
    return coords.get(prov_key)


def _format_display(province: Optional[str], city: Optional[str], district: Optional[str]) -> str:
    parts: List[str] = []
    if _is_valid_cell(province):
        parts.append(str(province).strip())
    if _is_valid_cell(city) and str(city).strip() not in ("市辖区", "县"):
        city_s = str(city).strip()
        if not parts or city_s not in parts[-1]:
            parts.append(city_s)
    if _is_valid_cell(district):
        dist_s = str(district).strip()
        if not parts or dist_s not in parts[-1]:
            parts.append(dist_s)
    return "".join(parts)


@lru_cache(maxsize=4096)
def _parse_location_cached(text: str) -> LocationInfo:
    info = LocationInfo()
    if not text:
        return info
    try:
        df = cpca.transform([text])
    except Exception:
        return info
    if df.empty:
        return info

    row = df.iloc[0]
    info.province = str(row["省"]).strip() if _is_valid_cell(row.get("省")) else None
    info.city = str(row["市"]).strip() if _is_valid_cell(row.get("市")) else None
    info.district = str(row["区"]).strip() if _is_valid_cell(row.get("区")) else None
    info.adcode = normalize_adcode(row.get("adcode"))
    info.display = _format_display(info.province, info.city, info.district)
    coord = get_coord_by_adcode(info.adcode)
    if coord:
        info.lat, info.lng = coord
    return info


def parse_location(text: str, source: str = "") -> LocationInfo:
    normalized = (text or "").strip()
    if not normalized:
        return LocationInfo(source=source)
    core = _parse_location_cached(normalized)
    if source:
        return replace(core, source=source)
    return core


def _normalize_lookup_text(text: Optional[str]) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _province_prefix(adcode: Optional[str]) -> Optional[str]:
    code = normalize_adcode(adcode)
    return code[:2] if code else None


def _city_prefix(adcode: Optional[str]) -> Optional[str]:
    code = normalize_adcode(adcode)
    if not code:
        return None
    if adcode_specificity(code) >= 2:
        return code[:4]
    return None


def is_neighbor_province(prov_a: Optional[str], prov_b: Optional[str]) -> bool:
    if not prov_a or not prov_b or prov_a == prov_b:
        return False
    neighbors = NEIGHBOR_PROVINCE_PREFIXES.get(prov_a, frozenset())
    if prov_b in neighbors:
        return True
    return prov_a in NEIGHBOR_PROVINCE_PREFIXES.get(prov_b, frozenset())


def _site_match_rank(patient_info: LocationInfo, site: Dict[str, Any]) -> int:
    patient_adcode = patient_info.adcode
    site_adcode = site.get("adcode")
    patient_city = _city_prefix(patient_adcode)
    site_city = _city_prefix(site_adcode)
    if patient_city and site_city and patient_city == site_city:
        return 0

    patient_prov = _province_prefix(patient_adcode)
    site_prov = _province_prefix(site_adcode)
    if patient_prov and site_prov:
        if patient_prov == site_prov:
            return 1
        if is_neighbor_province(patient_prov, site_prov):
            return 2
        return 3

    patient_norm = _normalize_lookup_text(patient_info.display or patient_info.city or patient_info.province)
    site_city_norm = _normalize_lookup_text(site.get("city"))
    site_prov_norm = _normalize_lookup_text(site.get("province"))
    if site_city_norm and site_city_norm in patient_norm:
        return 0
    if site_prov_norm and site_prov_norm in patient_norm:
        return 1
    return 3


def format_center_display(province: str, city: str, hospital: str) -> str:
    parts = [part.strip() for part in (province, city, hospital) if part and str(part).strip()]
    return " · ".join(parts)


def parse_trial_center_triples(
    province: str,
    city: str,
    hospital: str,
) -> List[Tuple[str, str, str]]:
    provinces = [p.strip() for p in re.split(r"[,，]", province or "") if p.strip()]
    cities = [c.strip() for c in re.split(r"[,，]", city or "") if c.strip()]
    hospitals = [h.strip() for h in re.split(r"[,，]", hospital or "") if h.strip()]
    if not provinces and not cities and not hospitals:
        return []
    if provinces and cities and hospitals and len(provinces) == len(cities) == len(hospitals):
        return list(zip(provinces, cities, hospitals))
    count = max(len(provinces), len(cities), len(hospitals))
    triples: List[Tuple[str, str, str]] = []
    for i in range(count):
        prov = provinces[i] if i < len(provinces) else (provinces[0] if len(provinces) == 1 else "")
        cit = cities[i] if i < len(cities) else (cities[0] if len(cities) == 1 else "")
        hosp = hospitals[i] if i < len(hospitals) else (hospitals[0] if len(hospitals) == 1 else "")
        triples.append((prov, cit, hosp))
    return triples


def build_trial_centers(province: str, city: str, hospital: str) -> List[Dict[str, Any]]:
    seen: set = set()
    centers: List[Dict[str, Any]] = []
    for prov, cit, hosp in parse_trial_center_triples(province, city, hospital):
        site_text = combine_province_city(prov, cit)
        info = parse_location(site_text)
        dedupe_key = (
            _normalize_lookup_text(info.province or prov),
            _normalize_lookup_text(info.city or cit),
            _normalize_lookup_text(hosp),
        )
        if not any(dedupe_key) or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        centers.append(
            {
                "province": info.province or prov,
                "city": info.city or cit,
                "hospital": hosp,
                "display": format_center_display(info.province or prov, info.city or cit, hosp),
                "location_display": info.display or site_text,
                "adcode": info.adcode,
                "location": hosp or cit or prov,
                "type": "city" if cit else "province",
            }
        )
    return centers


def build_trial_sites(province: str, city: str) -> List[Dict[str, Any]]:
    seen: set = set()
    sites: List[Dict[str, Any]] = []
    for prov, cit in parse_trial_site_pairs(province, city):
        site_text = combine_province_city(prov, cit)
        info = parse_location(site_text)
        dedupe_key = info.adcode or (
            _normalize_lookup_text(info.province or prov),
            _normalize_lookup_text(info.city or cit),
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        sites.append(
            {
                "province": info.province or prov,
                "city": info.city or cit,
                "display": info.display or site_text,
                "adcode": info.adcode,
                "location": cit or prov,
                "type": "city" if cit else "province",
            }
        )
    return sites


def geo_match_admin(
    patient_info: LocationInfo,
    sites: List[Dict[str, Any]],
) -> GeoMatchResult:
    if not patient_info.display or not sites:
        return GeoMatchResult()

    ranked_centers: List[Tuple[int, Dict[str, Any]]] = []
    best_rank = 3
    for site in sites:
        rank = _site_match_rank(patient_info, site)
        ranked_centers.append((rank, site))
        if rank < best_rank:
            best_rank = rank

    matched = [site for rank, site in ranked_centers if rank == best_rank]
    if not matched:
        return GeoMatchResult()

    match_level = MATCH_LEVEL_LABELS.get(best_rank, "较远")
    best_site = matched[0]
    nearest = {
        "location": best_site.get("hospital") or best_site.get("location"),
        "province": best_site.get("province"),
        "city": best_site.get("city"),
        "hospital": best_site.get("hospital"),
        "display": best_site.get("display") or best_site.get("location_display"),
        "distance": None,
        "match_level": match_level,
        "type": best_site.get("type"),
        "adcode": best_site.get("adcode"),
    }
    matched_centers = []
    for site in matched:
        matched_centers.append(
            {
                **site,
                "match_level": match_level,
                "geo_rank": best_rank,
            }
        )
    return GeoMatchResult(
        geo_rank=best_rank,
        geo_distance=None,
        nearest_location=nearest,
        match_level=match_level,
        matched_centers=matched_centers,
    )


def ensure_patient_location_info(patient: Dict[str, Any]) -> LocationInfo:
    cached = patient.get("_location_info")
    if isinstance(cached, LocationInfo):
        return cached
    if patient.get("location"):
        info = parse_location(str(patient["location"]), source="patient")
    else:
        info = LocationInfo(source="patient")
    patient["_location_info"] = info
    return info


def resolve_coord(text: str) -> Optional[Coord]:
    info = parse_location(text)
    if info.lat is not None and info.lng is not None:
        return (info.lat, info.lng)
    return None


def _source_priority(source: str) -> int:
    primary = (source or "").split("+")[0]
    return {"patient": 3, "filename": 2, "ocr_籍贯": 1}.get(primary, 0)


def merge_location_info(*candidates: LocationInfo) -> LocationInfo:
    """合并多来源位置，优先取 adcode 最具体的；必要时合并省+市。"""
    valid = [c for c in candidates if c and c.display]
    if not valid:
        return LocationInfo()

    best = max(
        valid,
        key=lambda c: (adcode_specificity(c.adcode), len(c.display), _source_priority(c.source)),
    )
    if adcode_specificity(best.adcode) >= 2:
        return best

    province_info = max(
        [c for c in valid if adcode_specificity(c.adcode) == 1],
        key=lambda c: len(c.display),
        default=None,
    )
    city_info = max(
        [c for c in valid if adcode_specificity(c.adcode) >= 2],
        key=lambda c: adcode_specificity(c.adcode),
        default=None,
    )
    if province_info and city_info and province_info.adcode and city_info.adcode:
        if province_info.adcode[:2] == city_info.adcode[:2]:
            return LocationInfo(
                province=city_info.province or province_info.province,
                city=city_info.city,
                district=city_info.district,
                adcode=city_info.adcode,
                display=city_info.display or province_info.display,
                source=f"{province_info.source}+{city_info.source}",
                lat=city_info.lat,
                lng=city_info.lng,
            )
    return best


def infer_patient_location(
    patient: Dict[str, Any],
    *,
    source_hint: str = "",
    raw_ocr_texts: Optional[List[str]] = None,
    pdf_file: str = "",
) -> LocationInfo:
    candidates: List[LocationInfo] = []
    if patient.get("location"):
        candidates.append(parse_location(str(patient["location"]), source="patient"))
    for hint in (source_hint, pdf_file):
        if hint:
            candidates.append(parse_location(hint, source="filename"))
    for chunk in (raw_ocr_texts or [])[:5]:
        m = re.search(r"籍贯[\s:：\t]+(\S+)", chunk)
        if m:
            candidates.append(parse_location(m.group(1), source="ocr_籍贯"))
    return merge_location_info(*candidates)


def apply_location_to_patient(
    patient: Dict[str, Any],
    *,
    source_hint: str = "",
    raw_ocr_texts: Optional[List[str]] = None,
    pdf_file: str = "",
) -> LocationInfo:
    info = infer_patient_location(
        patient,
        source_hint=source_hint,
        raw_ocr_texts=raw_ocr_texts,
        pdf_file=pdf_file,
    )
    if info.display:
        patient["location"] = info.display
    if info.adcode:
        patient["location_adcode"] = info.adcode
    if info.source:
        patient["location_source"] = info.source
    return info


def parse_trial_site_pairs(province: str, city: str) -> List[Tuple[str, str]]:
    provinces = [p.strip() for p in re.split(r"[,，]", province or "") if p.strip()]
    cities = [c.strip() for c in re.split(r"[,，]", city or "") if c.strip()]
    if not cities and not provinces:
        return []
    if cities and len(provinces) == len(cities):
        return list(zip(provinces, cities))
    if cities:
        return [(provinces[i] if i < len(provinces) else "", c) for i, c in enumerate(cities)]
    return [(p, "") for p in provinces]


def combine_province_city(province: str, city: str) -> str:
    if city:
        parsed = parse_location(city)
        if parsed.display:
            return parsed.display
        if province:
            return f"{province}{city}"
        return city
    return province


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return r * 2 * asin(min(1, sqrt(a)))


def compute_geo_distance(patient_location: str, province: str, city: str) -> Optional[float]:
    patient_coord = resolve_coord(patient_location)
    if not patient_coord:
        return None

    distances: List[float] = []
    for prov, cit in parse_trial_site_pairs(province, city):
        site_text = combine_province_city(prov, cit)
        trial_coord = resolve_coord(site_text)
        if trial_coord:
            distances.append(
                haversine_km(
                    patient_coord[0],
                    patient_coord[1],
                    trial_coord[0],
                    trial_coord[1],
                )
            )
    return min(distances) if distances else None


def find_nearest_trial_site(
    patient_location: str,
    province: str,
    city: str,
    *,
    patient_info: Optional[LocationInfo] = None,
    sites: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    pinfo = patient_info or parse_location(patient_location)
    site_list = sites if sites is not None else build_trial_sites(province, city)
    return geo_match_admin(pinfo, site_list).nearest_location


def geo_score(
    patient_location: str,
    province: str,
    city: str,
    *,
    patient_info: Optional[LocationInfo] = None,
    sites: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[int, Optional[float]]:
    pinfo = patient_info or parse_location(patient_location)
    site_list = sites if sites is not None else build_trial_sites(province, city)
    result = geo_match_admin(pinfo, site_list)
    return result.geo_rank, result.geo_distance


def province_prefix_match(
    patient_location: str,
    trial_province: str,
    *,
    patient_info: Optional[LocationInfo] = None,
) -> bool:
    patient = patient_info or parse_location(patient_location)
    trial_info = parse_location(trial_province)
    if patient.adcode and trial_info.adcode:
        return patient.adcode[:2] == trial_info.adcode[:2]
    if patient.province and trial_info.province:
        return trial_info.province in patient.display or patient.province in trial_info.province
    return False
