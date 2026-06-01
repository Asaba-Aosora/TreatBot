from codes.geo_admin import (
    compute_geo_distance,
    find_nearest_trial_site,
    geo_score,
    infer_patient_location,
    parse_location,
    resolve_coord,
)
from codes.trial_matcher import find_location_coord, find_nearest_location


def test_parse_location_shenyang():
    info = parse_location("辽宁沈阳")
    assert info.adcode == "210100"
    assert "沈阳" in info.display
    assert info.lat is not None


def test_parse_location_from_filename():
    info = parse_location("CHQI胰腺癌辽宁沈阳_患者信息_fixed.json")
    assert info.adcode == "210100"


def test_ocr_hometown_merged_with_filename():
    patient = {}
    ocr = ["姓名\t性别\t女\t年龄\t62\t籍贯\t辽宁\t民族\t汉"]
    info = infer_patient_location(
        patient,
        source_hint="CHQI胰腺癌辽宁沈阳.pdf",
        raw_ocr_texts=ocr,
    )
    assert info.adcode == "210100"
    assert "沈阳" in info.display


def test_same_city_zero_distance():
    dist = compute_geo_distance("辽宁沈阳", "辽宁省", "沈阳市")
    assert dist is not None
    assert dist < 1.0


def test_multi_site_shortest_distance():
    dist = compute_geo_distance("辽宁沈阳", "北京市,辽宁省", "北京市,沈阳市")
    assert dist is not None
    assert dist < 50


def test_find_nearest_trial_site():
    nearest = find_nearest_trial_site("辽宁沈阳", "北京市,辽宁省", "北京市,沈阳市")
    assert nearest is not None
    assert "沈阳" in nearest["location"]
    assert nearest["distance"] < 50


def test_backward_compat_wrappers():
    assert find_location_coord("沈阳市") is not None
    assert resolve_coord("沈阳市") == find_location_coord("沈阳市")
    nearest = find_nearest_location("辽宁沈阳", "北京市,辽宁省", "北京市,沈阳市")
    assert nearest is not None


def test_geo_score_local():
    rank, distance = geo_score("辽宁沈阳", "辽宁省", "沈阳市")
    assert rank == 0
    assert distance is not None
    assert distance < 50
