import json
from pathlib import Path

from codes.lab_normalize import attach_lab_observations, normalize_ocr_lab_payload
from codes.lab_rules import evaluate_lab_rule_clauses
from codes.trial_matcher import (
    build_review_queue,
    evaluate_lab_requirements,
    extract_lab_requirements,
    load_trials,
    rank_trials,
    semantic_similarity,
)
from codes.trial_parse import enrich_parsed_conditions


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


def test_missing_ecog_still_lists_candidates_strict():
    root = Path(__file__).resolve().parent.parent
    trial_path = root / "original_data" / "clinical_trials" / "trials_structured.json"
    if not trial_path.exists():
        return
    patient = {
        "diagnosis": "胃癌",
        "age": 70,
        "gender": "男",
        "ecog": None,
        "treatment_lines": None,
        "lab_observations": [],
    }
    trials = load_trials(str(trial_path))
    matches = rank_trials(patient, trials, top_n=20, match_mode="strict")
    assert len(matches) >= 1
    assert all(not m.get("hard_excluded") for m in matches)
    assert any(m.get("needs_review") for m in matches)
    assert all(not m.get("eligible") for m in matches if m.get("missing_core_fields"))


def test_known_ecog_fail_hard_excludes():
    from codes.trial_matcher import match_trial, parse_trial_condition
    from codes.trial_parse import enrich_parsed_conditions

    patient = {"diagnosis": "胃癌", "age": 70, "gender": "男", "ecog": 3, "treatment_lines": 1}
    trial = {
        "项目编码": "MOCK",
        "项目名称": "Mock",
        "疾病三级标签": "胃癌",
        "labels": ["胃癌"],
        "入组条件": "ECOG评分0-2分",
        "排除条件": "",
        "研究中心所在省份": "",
        "研究中心所在城市": "",
    }
    base = parse_trial_condition(trial)
    trial["parsed_conditions"] = enrich_parsed_conditions(trial, base)
    result = match_trial(patient, trial, match_mode="strict")
    assert result["hard_excluded"] is True
    assert result.get("ecog_pass") is False


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


def test_api_like_preprocess_path_builds_observations():
    patient = {"lab_results": [{"item": "白细胞", "value": "5.5", "unit": "10^9/L"}]}
    normalize_ocr_lab_payload(patient)
    attach_lab_observations(patient)
    assert len(patient.get("lab_observations") or []) == 1


def test_rag_assist_extracts_chinese_comparator_clause():
    trial = {
        "入组条件": "总胆红素不超过1.5倍ULN；白细胞至少3.0",
        "排除条件": "",
    }
    base = {"lab_requirements": {}}
    parsed = enrich_parsed_conditions(trial, base)
    clauses = parsed.get("inclusion_lab_clauses") or []
    assert any(c.get("metric_id") == "tbil" for c in clauses)
    assert any(c.get("source") in ("regex", "rag_template") for c in clauses)


def test_uln_clause_can_be_computed_from_reference_range():
    patient = {
        "lab_observations": [
            {
                "metric_id": "alt",
                "value_num": 60.0,
                "raw": {"range": "0-40", "unit": "U/L"},
            }
        ]
    }
    checks, inclusion_failed, _, _ = evaluate_lab_rule_clauses(
        patient,
        inclusion_clauses=[
            {
                "metric_id": "alt",
                "operator": "<=",
                "threshold": 2.0,
                "relative_to_uln": True,
                "field": "inclusion",
                "source": "rag_template",
                "confidence": 0.9,
                "evidence": "ALT不超过2倍ULN",
            }
        ],
        exclusion_clauses=[],
    )
    assert inclusion_failed is False
    assert checks[0]["status"] == "pass"
    assert checks[0]["decision_reason_code"] == "uln_ratio_computed"


def test_review_queue_prioritizes_high_risk_failures():
    matches = [
        {
            "trial_id": "T1",
            "trial_name": "Trial1",
            "score": 88.0,
            "review_items": [
                {"metric_id": "alt", "status": "fail", "priority": "p0", "field": "inclusion"},
                {"metric_id": "foo", "status": "unknown", "priority": "p2", "field": "inclusion"},
            ],
        }
    ]
    queue = build_review_queue(matches)
    assert queue[0]["metric_id"] == "alt"
