#!/usr/bin/env python3
"""
测试云端OCR功能
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

def test_ocr_imports():
    """测试OCR模块导入"""
    try:
        from codes.ocr_cloud import CloudOCR, process_pdf_with_cloud_ocr
        print("✅ OCR模块导入成功")
        return True
    except ImportError as e:
        print(f"❌ OCR模块导入失败: {e}")
        return False

def test_env_config():
    """测试环境配置"""
    from dotenv import load_dotenv
    import os

    load_dotenv()

    providers = ['DOUBAO_API_KEY', 'KIMI_API_KEY', 'ALIYUN_API_KEY']
    configured = []

    for provider in providers:
        if os.getenv(provider):
            configured.append(provider.replace('_API_KEY', ''))

    if configured:
        print(f"✅ 已配置API密钥: {', '.join(configured)}")
        return True
    else:
        print("⚠️ 未配置任何API密钥，请复制 .env.example 为 .env 并填入密钥")
        return False

def main():
    """主测试函数"""
    print("🧪 测试云端OCR功能")
    print("=" * 40)

    # 测试导入
    import_ok = test_ocr_imports()
    if not import_ok:
        return

    # 测试配置
    config_ok = test_env_config()

    print("\n📋 使用说明:")
    print("1. 复制 .env.example 为 .env 文件")
    print("2. 在 .env 中填入你的API密钥")
    print("3. 运行: python scripts/ocr_demo.py")
    print("4. 输入PDF路径并选择OCR提供商")

    print("\n🔧 支持的OCR服务:")
    print("• 豆包 (Doubao) - 推荐，数值识别最准")
    print("• Kimi - 通用医疗文本")
    print("• 阿里云OCR - 成本最低")

    if config_ok:
        print("\n✅ 准备就绪，可以开始使用OCR功能！")
    else:
        print("\n⚠️ 请先配置API密钥")

if __name__ == "__main__":
    main()