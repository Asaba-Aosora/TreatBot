from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi import Request
from pydantic import BaseModel, Field
import time
import uuid

from codes.lab_normalize import attach_lab_observations
from codes.ocr_cloud import process_pdf_with_cloud_ocr
from codes.trial_matcher import (
    build_patient_input,
    load_trials,
    rank_trials,
    summarize_patient_data_quality,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRIAL_JSON_PATH = PROJECT_ROOT / "original_data" / "clinical_trials" / "trials_structured.json"

app = FastAPI(title="有救AI API", version="0.3.0")
METRICS = {"requests_total": 0, "requests_failed": 0, "latency_ms_sum": 0.0}


class OCRRequest(BaseModel):
    pdf_path: str
    provider: str = Field(default="doubao", pattern="^(doubao|kimi|aliyun)$")


class LabResultInput(BaseModel):
    item: str
    value: str
    unit: Optional[str] = ""
    range: Optional[str] = ""
    status: Optional[str] = ""


class MatchRequest(BaseModel):
    diagnosis: str
    age: Optional[int] = None
    gender: Optional[str] = None
    ecog: Optional[int] = None
    treatment_lines: Optional[int] = None
    location: Optional[str] = None
    cancer_stage: Optional[str] = None
    biomarkers: List[str] = Field(default_factory=list)
    lab_results: List[LabResultInput] = Field(default_factory=list)
    match_mode: str = Field(default="strict", pattern="^(strict|balanced)$")
    top_n: int = 20


class FeedbackRequest(BaseModel):
    patient_id: str
    trial_id: str
    accepted: bool
    reason: Optional[str] = None
    doctor_id: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health():
    return {"ok": True}


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    request_id = str(uuid.uuid4())
    METRICS["requests_total"] += 1
    try:
        response = await call_next(request)
    except Exception:
        METRICS["requests_failed"] += 1
        raise
    finally:
        METRICS["latency_ms_sum"] += (time.time() - start) * 1000
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/metrics/summary")
def metrics_summary():
    total = METRICS["requests_total"] or 1
    return {
        **METRICS,
        "avg_latency_ms": round(METRICS["latency_ms_sum"] / total, 2),
    }


@app.post("/v1/ocr/process")
def ocr_process(payload: OCRRequest):
    result = process_pdf_with_cloud_ocr(
        pdf_path=payload.pdf_path,
        provider=payload.provider,
        output_dir=str(PROJECT_ROOT / "output_patients"),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


@app.post("/v1/match")
def match_trials(payload: MatchRequest):
    if not TRIAL_JSON_PATH.exists():
        raise HTTPException(status_code=500, detail=f"试验库不存在: {TRIAL_JSON_PATH}")
    patient = build_patient_input(
        diagnosis=payload.diagnosis,
        age=payload.age,
        gender=payload.gender,
        ecog=payload.ecog,
        treatment_lines=payload.treatment_lines,
        location=payload.location,
        cancer_stage=payload.cancer_stage,
        biomarkers=payload.biomarkers,
    )
    patient["lab_results"] = [item.model_dump() for item in payload.lab_results]
    attach_lab_observations(patient)

    trials = load_trials(str(TRIAL_JSON_PATH))
    matches = rank_trials(
        patient, trials, top_n=payload.top_n, match_mode=payload.match_mode
    )
    return {
        "patient": patient,
        "match_mode": payload.match_mode,
        "data_quality": summarize_patient_data_quality(patient),
        "matches": matches,
    }


@app.post("/v1/feedback")
def save_feedback(payload: FeedbackRequest):
    feedback_dir = PROJECT_ROOT / "structured_data" / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    target = feedback_dir / f"{payload.patient_id}.jsonl"
    line = payload.model_dump_json(ensure_ascii=False)
    with target.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return {"saved": True, "path": str(target)}
