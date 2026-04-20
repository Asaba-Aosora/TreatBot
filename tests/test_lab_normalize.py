from codes.lab_normalize import normalize_lab_results


def test_normalize_lab_results_filters_narrative():
    rows = [
        {"item": "入院情况", "value": "36.1", "unit": "℃", "range": "", "status": ""},
        {"item": "白细胞", "value": "5.0", "unit": "10^9/L", "range": "", "status": ""},
    ]
    obs = normalize_lab_results(rows)
    assert len(obs) == 1
    assert obs[0]["metric_id"] == "wbc"


def test_normalize_dedupes_same_metric():
    rows = [
        {"item": "白细胞", "value": "5.0", "unit": "10^9/L", "range": "", "status": ""},
        {"item": "白细胞", "value": "6.0", "unit": "10^9/L", "range": "", "status": ""},
    ]
    obs = normalize_lab_results(rows)
    assert len(obs) == 1
