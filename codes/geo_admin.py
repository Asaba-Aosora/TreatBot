"""中国行政区划解析与地理距离（cpca + 民政部 adcode 坐标）。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cpca
import pandas as pd

Coord = Tuple[float, float]


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


def parse_location(text: str, source: str = "") -> LocationInfo:
    text = (text or "").strip()
    info = LocationInfo(source=source)
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
) -> Optional[Dict[str, Any]]:
    patient_coord = resolve_coord(patient_location)
    if not patient_coord:
        return None

    nearest: Optional[Dict[str, Any]] = None
    min_dist = float("inf")
    for prov, cit in parse_trial_site_pairs(province, city):
        site_text = combine_province_city(prov, cit)
        trial_coord = resolve_coord(site_text)
        if not trial_coord:
            continue
        dist = haversine_km(
            patient_coord[0],
            patient_coord[1],
            trial_coord[0],
            trial_coord[1],
        )
        if dist < min_dist:
            min_dist = dist
            site_type = "city" if cit else "province"
            nearest = {
                "location": cit or prov,
                "display": site_text,
                "distance": dist,
                "type": site_type,
                "adcode": parse_location(site_text).adcode,
            }
    return nearest if nearest else None


def geo_score(patient_location: str, province: str, city: str) -> Tuple[int, Optional[float]]:
    distance = compute_geo_distance(patient_location, province, city)
    if distance is None:
        patient_info = parse_location(patient_location)
        if patient_info.adcode:
            patient_prefix = patient_info.adcode[:2]
            for prov, cit in parse_trial_site_pairs(province, city):
                site = parse_location(combine_province_city(prov, cit))
                if site.adcode and site.adcode[:2] == patient_prefix:
                    return 1, None
        return 2, None
    if distance < 50:
        return 0, distance
    if distance < 200:
        return 1, distance
    return 2, distance


def province_prefix_match(patient_location: str, trial_province: str) -> bool:
    patient_info = parse_location(patient_location)
    trial_info = parse_location(trial_province)
    if patient_info.adcode and trial_info.adcode:
        return patient_info.adcode[:2] == trial_info.adcode[:2]
    if patient_info.province and trial_info.province:
        return trial_info.province in patient_info.display or patient_info.province in trial_info.province
    return False
