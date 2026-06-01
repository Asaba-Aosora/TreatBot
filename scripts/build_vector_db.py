"""
构建试验库向量数据库（一次性离线流程）
使用 SentenceTransformer + Faiss 实现高效向量检索

使用方法：
    python scripts/build_vector_db.py
    
输出：
    - structured_data/vector_index/trials.faiss          # Faiss 索引
    - structured_data/vector_index/metadata.json         # 元数据（试验 ID、名称等）
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np


def build_vector_db(
    trials_json_path: str = 'original_data/clinical_trials/trials_structured.json',
    model_name: str = 'GanymedeNil/text2vec-large-chinese',
    output_dir: str = 'structured_data/vector_index',
    batch_size: int = 32,
):
    """
    构建向量数据库
    
    Args:
        trials_json_path: 试验库 JSON 文件路径
        model_name: SentenceTransformer 模型名称
        output_dir: 输出目录
        batch_size: 向量化批次大小
    """
    try:
        from sentence_transformers import SentenceTransformer
        import faiss
    except ImportError:
        print("❌ 缺少依赖，请先运行:")
        print("   pip install sentence-transformers faiss-cpu")
        return False
    
    # 确保输出目录存在
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 1. 加载试验数据
    trials_path = PROJECT_ROOT / trials_json_path
    if not trials_path.exists():
        print(f"❌ 找不到试验库文件: {trials_path}")
        print(f"   请确保 {trials_json_path} 存在")
        return False
    
    print(f"📂 加载试验库: {trials_path}")
    with open(trials_path, 'r', encoding='utf-8') as f:
        trials = json.load(f)
    print(f"✅ 加载了 {len(trials)} 个试验")
    
    # 2. 准备向量化文本
    print(f"\n📝 准备向量化文本...")
    trial_texts = []
    trial_ids = []
    trial_names = []
    
    for trial in trials:
        # 拼接：试验名称 + 入组条件 + 排除条件
        # 这样既包含诊断信息，也包含详细的纳入排除标准
        text_parts = [
            trial.get('项目名称', ''),
            trial.get('入组条件', ''),
            trial.get('排除条件', ''),
        ]
        text = ' '.join([p for p in text_parts if p])
        
        if text.strip():  # 只要非空文本
            trial_texts.append(text)
            trial_ids.append(trial.get('项目编码', 'unknown'))
            trial_names.append(trial.get('项目名称', 'unknown'))
    
    print(f"   需向量化的文本数: {len(trial_texts)}")
    
    # 3. 加载模型（第一次会自动下载，约 440MB）
    print(f"\n🤖 加载模型: {model_name}")
    print(f"   首次使用会自动下载到 ~/.cache/huggingface/hub/")
    print(f"   这可能需要 5-10 分钟（取决于网络）...")
    
    try:
        model = SentenceTransformer(model_name)
        embedding_dim = model.get_sentence_embedding_dimension()
        print(f"✅ 模型加载成功，向量维度: {embedding_dim}")
    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        print(f"   可能原因：")
        print(f"   1. 网络连接问题，无法下载模型")
        print(f"   2. 磁盘空间不足")
        print(f"   解决方案：检查网络，或指定本地模型路径")
        return False
    
    # 4. 批量向量化
    print(f"\n🔄 向量化 {len(trial_texts)} 个试验文本...")
    print(f"   batch_size={batch_size}")
    
    try:
        embeddings = model.encode(
            trial_texts,
            batch_size=batch_size,
            show_progress_bar=True,
            convert_to_numpy=True
        )
        print(f"✅ 向量化完成，生成向量形状: {embeddings.shape}")
    except Exception as e:
        print(f"❌ 向量化失败: {e}")
        return False
    
    # 5. 构建 Faiss 索引
    print(f"\n⚙️  构建 Faiss 索引...")
    try:
        # 使用 L2 距离的平面索引（对 10k 数据足够快）
        index = faiss.IndexFlatL2(embedding_dim)
        index.add(embeddings.astype('float32'))
        print(f"✅ Faiss 索引构建完成，包含 {index.ntotal} 向量")
    except Exception as e:
        print(f"❌ 索引构建失败: {e}")
        return False
    
    # 6. 保存索引文件
    print(f"\n💾 保存向量库...")
    try:
        faiss_path = output_path / 'trials.faiss'
        faiss.write_index(index, str(faiss_path))
        print(f"✅ 索引已保存: {faiss_path}")
    except Exception as e:
        print(f"❌ 索引保存失败: {e}")
        return False
    
    # 7. 保存元数据（用于检索结果对应试验信息）
    print(f"   保存元数据...")
    metadata = {
        'embedding_model': model_name,
        'embedding_dim': int(embedding_dim),
        'total_trials': len(trial_texts),
        'trial_ids': trial_ids,
        'trial_names': trial_names,
        'index_type': 'IndexFlatL2',
        'distance_metric': 'L2 (欧几里得距离)',
    }
    
    try:
        metadata_path = output_path / 'metadata.json'
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"✅ 元数据已保存: {metadata_path}")
    except Exception as e:
        print(f"❌ 元数据保存失败: {e}")
        return False
    
    # 8. 验证
    print(f"\n✨ 向量库构建完成！")
    print(f"   📊 统计信息:")
    print(f"      - 试验总数: {len(trial_texts)}")
    print(f"      - 向量维度: {embedding_dim}")
    print(f"      - 索引类型: Faiss IndexFlatL2")
    print(f"      - 预期查询时间: 5-10ms (top_20)")
    print(f"      - 索引大小: ~{len(trial_texts) * embedding_dim * 4 / 1024 / 1024:.1f} MB")
    print(f"\n   📁 输出文件:")
    print(f"      - {faiss_path}")
    print(f"      - {metadata_path}")
    print(f"\n   🚀 下一步:")
    print(f"      运行 python scripts/run_match.py 或 python scripts/demo_server.py")
    print(f"      即可使用向量语义匹配！")
    
    return True


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='构建试验库向量数据库')
    parser.add_argument('--trials-json', default='original_data/clinical_trials/trials_structured.json',
                        help='试验库 JSON 文件路径')
    parser.add_argument('--model', default='GanymedeNil/text2vec-large-chinese',
                        help='SentenceTransformer 模型名称')
    parser.add_argument('--output-dir', default='structured_data/vector_index',
                        help='输出目录')
    parser.add_argument('--batch-size', type=int, default=32,
                        help='向量化批次大小')
    
    args = parser.parse_args()
    
    success = build_vector_db(
        trials_json_path=args.trials_json,
        model_name=args.model,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
    )
    
    sys.exit(0 if success else 1)
