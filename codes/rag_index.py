import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List

from codes.trial_matcher import normalize_text


def _hash_embed(text: str, dim: int = 256) -> List[float]:
    vec = [0.0] * dim
    norm = normalize_text(text)
    if not norm:
        return vec
    for i in range(max(1, len(norm) - 1)):
        token = norm[i : i + 2]
        idx = hash(token) % dim
        vec[idx] += 1.0
    scale = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / scale for v in vec]


def _cosine(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass
class CriterionChunk:
    chunk_id: str
    trial_id: str
    chunk_type: str
    text: str
    vector: List[float]
    metadata: Dict


class TrialVectorIndex:
    def __init__(self, dim: int = 256):
        self.dim = dim
        self.chunks: List[CriterionChunk] = []

    def add_chunk(self, chunk_id: str, trial_id: str, chunk_type: str, text: str, metadata: Dict):
        self.chunks.append(
            CriterionChunk(
                chunk_id=chunk_id,
                trial_id=trial_id,
                chunk_type=chunk_type,
                text=text,
                vector=_hash_embed(text, self.dim),
                metadata=metadata,
            )
        )

    def search(self, query: str, top_k: int = 8) -> List[Dict]:
        query_vec = _hash_embed(query, self.dim)
        ranked = []
        for chunk in self.chunks:
            ranked.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "trial_id": chunk.trial_id,
                    "chunk_type": chunk.chunk_type,
                    "text": chunk.text,
                    "metadata": chunk.metadata,
                    "score": _cosine(query_vec, chunk.vector),
                }
            )
        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked[:top_k]

    def save(self, path: str):
        payload = {"dim": self.dim, "chunks": [asdict(c) for c in self.chunks]}
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str) -> "TrialVectorIndex":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        index = cls(dim=payload.get("dim", 256))
        for item in payload.get("chunks", []):
            index.chunks.append(CriterionChunk(**item))
        return index
