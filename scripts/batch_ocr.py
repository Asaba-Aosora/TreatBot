#!/usr/bin/env python3
"""
批量 OCR：dataset_patient 下 PDF → output_patients/{stem}_患者信息.json

示例:
    python scripts/batch_ocr.py
    python scripts/batch_ocr.py --pdf-dir original_data/dataset_patient --skip-existing
    python scripts/batch_ocr.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from codes.ocr_cloud import process_pdf_with_cloud_ocr  # noqa: E402

DEFAULT_POPPLER = Path(r"D:\Asaba\Softwares\poppler-25.12.0\Library\bin")


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


class _Tee:
    """同时写入控制台与 UTF-8 日志文件。"""

    def __init__(self, stream, log_path: Path):
        self._stream = stream
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = log_path.open("w", encoding="utf-8")

    def write(self, data: str) -> int:
        self._stream.write(data)
        self._log.write(data)
        return len(data)

    def flush(self) -> None:
        self._stream.flush()
        self._log.flush()

    def close(self) -> None:
        self._log.close()


def _resolve_poppler(explicit: str) -> str | None:
    for candidate in (explicit.strip(), os.getenv("POPPLER_PATH", "").strip()):
        if candidate and Path(candidate).exists():
            return candidate
    if DEFAULT_POPPLER.exists():
        return str(DEFAULT_POPPLER)
    return None


def _ocr_output_path(output_dir: Path, pdf: Path) -> Path:
    return output_dir / f"{pdf.stem}_患者信息.json"


def _should_skip(out_path: Path, *, require_success: bool) -> Tuple[bool, str]:
    if not out_path.exists():
        return False, ""
    if not require_success:
        return True, "output exists"
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"invalid existing json ({exc})"
    if data.get("success"):
        return True, "success json exists"
    return False, "existing json not successful"


def _collect_pdfs(pdf_dir: Path) -> List[Path]:
    return sorted(pdf_dir.rglob("*.pdf"))


def _run_batch(args: argparse.Namespace, pdf_dir: Path, output_dir: Path) -> int:
    if not pdf_dir.exists():
        print(f"[ERROR] PDF 目录不存在: {pdf_dir}", file=sys.stderr)
        return 1

    poppler = _resolve_poppler(args.poppler_path)
    if not poppler:
        print("[WARN] 未找到 poppler，PDF 转图可能失败。可设置 POPPLER_PATH 或 --poppler-path")
    else:
        print(f"poppler: {poppler}")

    pdfs = _collect_pdfs(pdf_dir)
    if not pdfs:
        print(f"[WARN] 未找到 PDF: {pdf_dir}")
        return 0

    to_run: List[Path] = []
    skipped: List[Tuple[Path, str]] = []

    for pdf in pdfs:
        out_path = _ocr_output_path(output_dir, pdf)
        if args.skip_existing:
            skip, reason = _should_skip(out_path, require_success=args.require_success)
            if skip:
                skipped.append((pdf, reason))
                continue
        to_run.append(pdf)

    print(f"PDF 总数: {len(pdfs)} | 跳过: {len(skipped)} | 待 OCR: {len(to_run)}")
    for pdf, reason in skipped:
        print(f"  SKIP [{reason}] {pdf.relative_to(pdf_dir)}")

    if args.dry_run:
        for pdf in to_run:
            print(f"  RUN {pdf.relative_to(pdf_dir)} -> {_ocr_output_path(output_dir, pdf).name}")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    ok, fail = 0, 0
    batch_start = time.time()

    for idx, pdf in enumerate(to_run, 1):
        rel = pdf.relative_to(pdf_dir)
        print(f"\n{'=' * 60}")
        print(f"[{idx}/{len(to_run)}] {rel}")
        print(f"{'=' * 60}")
        try:
            result = process_pdf_with_cloud_ocr(
                pdf_path=str(pdf),
                provider=args.provider,
                output_dir=str(output_dir),
                poppler_path=poppler,
                run_mode=args.run_mode,
            )
            if result.get("success"):
                ok += 1
                print(f"OK: {_ocr_output_path(output_dir, pdf).name}")
            else:
                fail += 1
                print(f"FAIL: {result.get('error')}")
                for err in result.get("errors") or []:
                    print(f"  - {err}")
        except KeyboardInterrupt:
            print("\n用户中断")
            break
        except Exception as exc:
            fail += 1
            print(f"FAIL: {exc}")

    elapsed = time.time() - batch_start
    print(f"\n{'=' * 60}")
    print(f"批量 OCR 完成 | 成功: {ok} | 失败: {fail} | 跳过: {len(skipped)} | 耗时: {elapsed:.0f}s")
    return 0 if fail == 0 else 1


def main() -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="批量 PDF OCR（跳过已成功输出）")
    parser.add_argument(
        "--pdf-dir",
        default="original_data/dataset_patient",
        help="PDF 根目录（递归扫描）",
    )
    parser.add_argument(
        "--output-dir",
        default="output_patients",
        help="OCR JSON 输出目录",
    )
    parser.add_argument("--provider", default="doubao", choices=["doubao", "kimi", "aliyun"])
    parser.add_argument(
        "--run-mode",
        default="hybrid",
        choices=["hybrid", "fast", "quality"],
    )
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="跳过已有成功 OCR 结果（默认开启）",
    )
    parser.add_argument(
        "--require-success",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="仅当已有 JSON success=true 时跳过",
    )
    parser.add_argument("--poppler-path", default=os.getenv("POPPLER_PATH", ""))
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不执行 OCR")
    parser.add_argument(
        "--log-file",
        default="output_patients/batch_ocr.log",
        help="批量 OCR 日志（UTF-8）",
    )
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    if not pdf_dir.is_absolute():
        pdf_dir = PROJECT_ROOT / pdf_dir
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    log_path = Path(args.log_file)
    if not log_path.is_absolute():
        log_path = PROJECT_ROOT / log_path

    tee = _Tee(sys.stdout, log_path)
    sys.stdout = tee
    try:
        return _run_batch(args, pdf_dir, output_dir)
    finally:
        tee.close()


if __name__ == "__main__":
    raise SystemExit(main())
