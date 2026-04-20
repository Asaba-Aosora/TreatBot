#!/usr/bin/env python3
"""
医疗病历 OCR 演示脚本。
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from codes.ocr_cloud import process_pdf_with_cloud_ocr


def _select_provider() -> str:
    print("\n选择OCR服务提供商:")
    print("1. 豆包 (Doubao) - 推荐，医学检验报告最准")
    print("2. Kimi")
    print("3. 阿里云OCR")
    provider_map = {"1": "doubao", "2": "kimi", "3": "aliyun"}
    return provider_map.get(input("请选择 (1-3): ").strip(), "")


def _select_mode() -> tuple[str, int]:
    print("\n选择识别模式:")
    print("1. 混合模式（默认推荐）：先快扫全页，再精扫关键页")
    print("2. FAST模式：更快，仅识别前N页")
    print("3. 高精度模式：更慢，直接高精度识别全部页")
    choice = input("请选择 (1-3，默认1): ").strip() or "1"
    if choice == "2":
        return "fast", 5
    if choice == "3":
        return "quality", 0
    return "hybrid", 0


def main():
    pdf_path = input("请输入PDF病历文件路径: ").strip()
    if not pdf_path:
        print("❌ 未输入PDF路径")
        return
    if not Path(pdf_path).exists():
        print(f"❌ PDF文件不存在: {pdf_path}")
        return

    provider = _select_provider()
    if not provider:
        print("❌ 无效选择")
        return
    run_mode, default_pages = _select_mode()
    max_pages = default_pages
    if run_mode == "fast":
        custom_pages = input("FAST模式最大页数（默认5）: ").strip()
        if custom_pages.isdigit() and int(custom_pages) > 0:
            max_pages = int(custom_pages)

    print(f"\n🔍 使用 {provider.upper()} 处理: {Path(pdf_path).name}")
    result = process_pdf_with_cloud_ocr(
        pdf_path=pdf_path,
        provider=provider,
        output_dir=str(PROJECT_ROOT / "output_patients"),
        run_mode=run_mode,
        max_pages=max_pages if run_mode == "fast" else None,
    )

    if not result.get("success"):
        print(f"\n❌ 处理失败: {result.get('error', '未知错误')}")
        for err in result.get("errors", []):
            print(f"  - {err}")
        return

    patient = result.get("patient", {})
    print("\n✅ 识别成功!")
    print(f"📄 页面数: {result.get('pages', 0)}")
    print(f"⏱️ 总耗时: {result.get('processing_time', 0):.1f}s")
    print(f"🤖 模型: {provider.upper()}")
    mode_label = {"fast": "FAST", "quality": "高精度", "hybrid": "混合"}
    print(f"⚙️ 模式: {mode_label.get(result.get('mode', run_mode), run_mode)}")

    print("\n👤 患者信息:")
    print(f"  姓名: {patient.get('name') or '未识别'}")
    print(f"  年龄: {patient.get('age') or '未识别'}")
    print(f"  性别: {patient.get('gender') or '未识别'}")
    print(f"  诊断: {patient.get('diagnosis') or '未识别'}")
    print(f"  分期: {patient.get('cancer_stage') or '未识别'}")
    print(f"  ECOG: {patient.get('ecog') if patient.get('ecog') is not None else '未识别'}")
    print(f"  治疗线数: {patient.get('treatment_lines') if patient.get('treatment_lines') is not None else '未识别'}")

    lab_results = patient.get("lab_results") or []
    if lab_results:
        print("\n🔬 检验结果(前10项):")
        for item in lab_results[:10]:
            print(
                f"  - {item.get('item', '未知项目')}: "
                f"{item.get('value', '-')}{item.get('unit', '')} "
                f"(参考: {item.get('range', '-')}, 状态: {item.get('status', '-')})"
            )
        if len(lab_results) > 10:
            print(f"  ... 还有 {len(lab_results) - 10} 项")

    print("\n💾 结果已保存到 output_patients 目录")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户取消操作")