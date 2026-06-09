from codes.patient_filename_infer import (
    infer_from_filename,
    normalize_diagnosis_for_matching,
)
from codes.patient_matching_normalize import infer_cancer_stage, infer_stage_from_text
from codes.trial_matcher import find_matching_labels, load_trials, rank_trials


def test_infer_haqi_filename():
    hints = infer_from_filename("HAQI胃癌一线进展.pdf")
    assert hints.cancer_type == "胃癌"
    assert hints.treatment_lines == 1


def test_infer_chqi_filename():
    hints = infer_from_filename("CHQI胰腺癌辽宁沈阳.pdf")
    assert hints.cancer_type == "胰腺癌"
    assert hints.location_display and "沈阳" in hints.location_display


def test_infer_stage_from_haqi_diagnosis():
    diag = "胃恶性肿瘤 TXNXM1（Ⅳ）（KPS 80分）NRS0"
    assert infer_stage_from_text(diag) == "IV"
    assert infer_cancer_stage({"diagnosis": diag}) == "IV"


def test_infer_stage_explicit_period():
    assert infer_stage_from_text("胃癌 IV期") == "IV"
    assert infer_stage_from_text("胰腺癌 3期") == "III"


def test_infer_stage_paren_roman():
    assert infer_stage_from_text("腺癌 (III)") == "III"
    assert infer_stage_from_text("腺癌（2）") == "II"


def test_infer_stage_tnm_m1():
    assert infer_stage_from_text("cT2N1M1") == "IV"
    assert infer_stage_from_text("胃窦腺癌 pM1") == "IV"


def test_infer_stage_tnm_m0_not_iv():
    assert infer_stage_from_text("cT2N0M0") is None


def test_infer_stage_kps_paren_not_stage():
    assert infer_stage_from_text("（KPS 80分）") is None


def test_infer_stage_preserves_existing():
    assert infer_cancer_stage({"cancer_stage": "III期", "diagnosis": ""}) == "III"


def test_normalize_stomach_cancer_synonym():
    norm = normalize_diagnosis_for_matching("胃恶性肿瘤 TXNXM1（Ⅳ）（KPS 80分）NRS0")
    assert "胃癌" in norm or norm.startswith("胃")
    assert "txnxm" not in norm
    assert "t/nk" not in norm


def test_stomach_diagnosis_does_not_match_tnk_lymphoma():
    diag = normalize_diagnosis_for_matching(
        "胃恶性肿瘤 TXNXM1（Ⅳ）（KPS 80分）NRS0 胃癌"
    )
    matched = find_matching_labels(diag, ["T/NK细胞淋巴瘤", "胃癌"])
    assert "胃癌" in matched
    assert "T/NK细胞淋巴瘤" not in matched


def test_haqi_patient_matches_gastric_trials_not_lymphoma_only():
    root_trial = "original_data/clinical_trials/trials_structured.json"
    trials = load_trials(root_trial)
    patient = {
        "diagnosis": "胃恶性肿瘤 TXNXM1（Ⅳ）（KPS 80分）NRS0",
        "cancer_type": "胃癌",
        "age": 70,
        "gender": "男",
        "ecog": None,
        "treatment_lines": 1,
        "lab_observations": [],
    }
    matches = rank_trials(patient, trials, top_n=20, match_mode="strict")
    assert len(matches) >= 1
    assert not all(
        any("T/NK" in str(l) for l in (m.get("matching_labels") or []))
        for m in matches
    )
    assert any(
        any("胃癌" in str(l) for l in (m.get("matching_labels") or []))
        for m in matches
    )
