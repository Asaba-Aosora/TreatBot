import json
from pathlib import Path

from codes.lab_normalize import attach_lab_observations
from codes.lab_rules import evaluate_lab_rule_clauses
from codes.trial_matcher import (
    evaluate_lab_requirements,
    extract_lab_requirements,
    load_trials,
    rank_trials,
    semantic_similarity,
)


def test_extract_lab_requirements():
    text = "白细胞 >= 3.0 且 肌酐 ≤1.5"
    req = extract_lab_requirements(text)
    assert req["白细胞"]["min"] == 3.0
    assert req["肌酐"]["max"] == 1.5


def test_evaluate_lab_requirements():
    patient = {
        "lab_results": [
            {"item": "白细胞", "value": "4.5"},
            {"item": "肌酐", "value": "1.2"},
        ]
    }
    req = {"白细胞": {"min": 3.0, "max": None}, "肌酐": {"min": None, "max": 1.5}}
    passed, violations, missing = evaluate_lab_requirements(patient, req)
    assert passed is True
    assert violations == []
    assert missing == []


def test_semantic_similarity():
    score = semantic_similarity("胆管癌 IIIB", "适应症包含胆管癌患者")
    assert score > 0


def test_unit_mismatch_fallback_to_unknown():
    patient = {
        "lab_observations": [
            {
                "metric_id": "cr",
                "value_num": 46.0,
                "raw": {"range": "41--81", "unit": ""},
            }
        ]
    }
    checks, inclusion_failed, exclusion_triggered, next_steps = (
        evaluate_lab_rule_clauses(
            patient,
            inclusion_clauses=[
                {
                    "metric_id": "cr",
                    "operator": "<=",
                    "threshold": 1.5,
                    "relative_to_uln": False,
                    "field": "inclusion",
                    "evidence": "肌酐 <=1.5",
                }
            ],
            exclusion_clauses=[],
        )
    )
    assert inclusion_failed is False
    assert exclusion_triggered is False
    assert checks[0]["status"] == "unknown"
    assert "cr" in next_steps


def test_fixed_patient_can_recall_candidates_balanced():
    root = Path(__file__).resolve().parent.parent
    patient_path = (
        root / "output_patients" / "CHQI胰腺癌辽宁沈阳_患者信息_fixed.json"
    )
    trial_path = root / "original_data" / "clinical_trials" / "trials_structured.json"
    if not patient_path.exists() or not trial_path.exists():
        return
    patient = json.loads(patient_path.read_text(encoding="utf-8"))["patient"]
    attach_lab_observations(patient)
    trials = load_trials(str(trial_path))
    matches = rank_trials(patient, trials, top_n=20, match_mode="balanced")
    assert len(matches) >= 1
