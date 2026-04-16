"""
快速开始脚本 - 本地Ollama医疗病历处理
直接运行这个文件即可处理PDF
"""
import os
from pathlib import Path
import sys

from codes.ocr_ollama import process_pdf_with_ollama

def main():
    """主程序"""
    
    print("""
╔═══════════════════════════════════════════════════════════════╗
║       医疗病历OCR处理 - 本地Ollama免费方案                      ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # 配置
    PDF_PATH = r"original_data/dataset_patient/姓名：CHRO胆管癌 四川.pdf"
    
    # Windows用户指定poppler路径
    POPPLER_PATH = r"D:\Asaba\Softwares\poppler-25.12.0\Library\bin"
    
    # Ollama模型选择（根据你安装的修改）
    # 推荐: "llava:7b" (平衡) 
    # 可选: "llava:13b" (更强但慢) 
    #      "minicpm-v:latest" (很快但精度一般)
    MODEL = "llava:7b"
    
    # 检查PDF文件
    if not Path(PDF_PATH).exists():
        print(f"❌ PDF文件不存在: {PDF_PATH}")
        print("   请修改PDF_PATH指向正确的医疗病历文件")
        sys.exit(1)
    
    # 检查Ollama是否运行
    try:
        import requests
        requests.get("http://localhost:11434/api/tags", timeout=2)
    except Exception as e:
        print(f"❌ Ollama服务未运行")
        print(f"   请先运行: ollama serve")
        print(f"   (在另一个终端窗口)")
        sys.exit(1)
    
    # 开始处理
    result = process_pdf_with_ollama(
        pdf_path=PDF_PATH,
        model=MODEL,
        output_dir="./output_patients",
        poppler_path=POPPLER_PATH if os.path.exists(POPPLER_PATH) else None
    )
    
    if not result.get('success'):
        print(f"\n⚠️  处理未完全成功")
        if result.get('errors'):
            print("错误信息:")
            for error in result['errors']:
                print(f"  - {error}")
    
    return result


if __name__ == "__main__":
    result = main()
    
    # 可选：进一步处理result
    if result.get('success'):
        patient = result.get('patient', {})
        print(f"\n✅ 患者信息提取完成:")
        print(f"   年龄: {patient.get('age')}")
        print(f"   诊断: {patient.get('diagnosis')}")
        print(f"   ECOG: {patient.get('ecog')}")
