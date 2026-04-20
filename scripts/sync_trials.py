import argparse
import json
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="临床试验数据版本化同步")
    parser.add_argument("--input", required=True, help="输入JSON路径")
    parser.add_argument("--output-dir", default="structured_data/trial_versions", help="版本存储目录")
    args = parser.parse_args()

    source = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    trials = json.loads(source.read_text(encoding="utf-8"))
    version = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = output_dir / f"trials_{version}.json"
    target.write_text(json.dumps(trials, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = output_dir / "manifest.jsonl"
    with manifest.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "version": version,
                    "source": str(source),
                    "target": str(target),
                    "count": len(trials),
                    "created_at": datetime.now().isoformat(),
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    print(f"已写入版本: {target}")
    print(f"试验条数: {len(trials)}")


if __name__ == "__main__":
    main()
