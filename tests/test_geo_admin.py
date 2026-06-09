from codes.geo_admin import (
    build_trial_centers,
    build_trial_sites,
    compute_geo_distance,
    find_nearest_trial_site,
    geo_match_admin,
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
    assert nearest.get("match_level") == "同市"


def test_backward_compat_wrappers():
    assert find_location_coord("沈阳市") is not None
    assert resolve_coord("沈阳市") == find_location_coord("沈阳市")
    nearest = find_nearest_location("辽宁沈阳", "北京市,辽宁省", "北京市,沈阳市")
    assert nearest is not None


def test_geo_score_local():
    rank, distance = geo_score("辽宁沈阳", "辽宁省", "沈阳市")
    assert rank == 0
    assert distance is None


def test_geo_match_admin_same_province():
    patient = parse_location("辽宁沈阳")
    centers = build_trial_centers(
        "辽宁省,辽宁省",
        "大连市,沈阳市",
        "大连市中心医院,辽宁省肿瘤医院",
    )
    result = geo_match_admin(patient, centers)
    assert result.geo_rank == 0
    assert result.match_level == "同市"
    assert result.nearest_location is not None
    assert len(result.matched_centers) == 1
    assert result.matched_centers[0]["hospital"] == "辽宁省肿瘤医院"
    assert "沈阳" in result.matched_centers[0]["city"]


def test_geo_match_admin_neighbor_province():
    patient = parse_location("辽宁沈阳")
    centers = build_trial_centers("吉林省", "长春市", "吉林省肿瘤医院")
    result = geo_match_admin(patient, centers)
    assert result.geo_rank == 2
    assert result.match_level == "邻省"
    assert len(result.matched_centers) == 1


def test_build_trial_centers_dedupes_triples():
    centers = build_trial_centers(
        "北京市,北京市",
        "北京市,北京市",
        "北京医院,北京医院",
    )
    assert len(centers) == 1
    assert centers[0]["hospital"] == "北京医院"
