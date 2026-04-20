from codes.trial_matcher import (
    evaluate_lab_requirements,
    extract_lab_requirements,
    semantic_similarity,
)


def test_extract_lab_requirements():
    text = "白细胞 >= 3.0 且 肌酐 ≤1.5"
    req = extract_lab_requirements(text)
    assert req["白细胞"]["min"] == 3.0
    assert req["肌酐"]["max"] == 1.5


def test_evaluate_lab_requirements():
    patient = {"lab_results": [{"item": "白细胞", "value": "4.5"}, {"item": "肌酐", "value": "1.2"}]}
    req = {"白细胞": {"min": 3.0, "max": None}, "肌酐": {"min": None, "max": 1.5}}
    passed, violations, missing = evaluate_lab_requirements(patient, req)
    assert passed is True
    assert violations == []
    assert missing == []


def test_semantic_similarity():
    score = semantic_similarity("胆管癌 IIIB", "适应症包含胆管癌患者")
    assert score > 0
