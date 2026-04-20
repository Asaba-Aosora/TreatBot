from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LabResult:
    item: str
    value: str
    unit: str = ""
    range: str = ""
    status: str = ""


@dataclass
class LabObservation:
    """OCR 原始 lab_results 归一化后的可计算化验项（metric_id 见 lab_lexicon）。"""

    metric_id: str
    value_num: float
    unit_norm: str = ""
    comparator: Optional[str] = None
    confidence: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TrialRuleClause:
    """试验入排中解析出的一条化验数值规则（可序列化存库）。"""

    metric_id: str
    operator: str
    threshold: float
    field: str  # inclusion | exclusion
    severity: str = "must"  # must | should
    relative_to_uln: bool = False
    evidence: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PatientProfile:
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    diagnosis: Optional[str] = None
    cancer_stage: Optional[str] = None
    ecog: Optional[int] = None
    treatment_lines: Optional[int] = None
    treatments: List[str] = field(default_factory=list)
    allergies: List[str] = field(default_factory=list)
    location: Optional[str] = None
    biomarkers: List[str] = field(default_factory=list)
    lab_results: List[LabResult] = field(default_factory=list)
    lab_observations: List[LabObservation] = field(default_factory=list)

    def to_dict(self) -> Dict:
        payload = asdict(self)
        payload["lab_results"] = [asdict(item) for item in self.lab_results]
        payload["lab_observations"] = [o.to_dict() for o in self.lab_observations]
        return payload


@dataclass
class OCRIssue:
    severity: str
    code: str
    message: str
    page: Optional[int] = None


@dataclass
class OCRResultEnvelope:
    success: bool
    provider: str
    patient: PatientProfile
    pages: int
    processing_time: float
    issues: List[OCRIssue] = field(default_factory=list)
    raw_ocr_texts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "provider": self.provider,
            "patient": self.patient.to_dict(),
            "pages": self.pages,
            "processing_time": self.processing_time,
            "issues": [asdict(item) for item in self.issues],
            "raw_ocr_texts": self.raw_ocr_texts,
        }
