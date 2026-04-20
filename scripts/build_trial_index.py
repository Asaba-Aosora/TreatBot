import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from codes.rag_index import TrialVectorIndex


def split_criteria(text: str):
    if not text:
        return []
    chunks = []
    for idx, part in enumerate([p.strip() for p in text.replace("；", "。").split("。") if p.strip()]):
        chunks.append({"idx": idx, "text": part})
    return chunks


def main():
    source = PROJECT_ROOT / "original_data" / "clinical_trials" / "trials_structured.json"
    target = PROJECT_ROOT / "structured_data" / "vector_index" / "trial_criteria_index.json"
    trials = json.loads(source.read_text(encoding="utf-8"))
    index = TrialVectorIndex(dim=256)

    for trial in trials:
        trial_id = str(trial.get("项目编码", "unknown"))
        for chunk in split_criteria(trial.get("入组条件", "")):
            index.add_chunk(
                chunk_id=f"{trial_id}-inc-{chunk['idx']}",
                trial_id=trial_id,
                chunk_type="inclusion",
                text=chunk["text"],
                metadata={"trial_name": trial.get("项目名称", ""), "field": "入组条件"},
            )
        for chunk in split_criteria(trial.get("排除条件", "")):
            index.add_chunk(
                chunk_id=f"{trial_id}-exc-{chunk['idx']}",
                trial_id=trial_id,
                chunk_type="exclusion",
                text=chunk["text"],
                metadata={"trial_name": trial.get("项目名称", ""), "field": "排除条件"},
            )

    index.save(str(target))
    print(f"索引已生成: {target}")
    print(f"Chunk数量: {len(index.chunks)}")


if __name__ == "__main__":
    main()
