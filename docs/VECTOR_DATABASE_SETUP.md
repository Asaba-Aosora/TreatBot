"""
🚀 Faiss 向量数据库快速开始指南

本文件说明如何配置和使用 Faiss + SentenceTransformer 实现高效向量检索。
"""

# ============================================================================
# 第一步：依赖安装（一次性）
# ============================================================================

print("""
❶ 在终端运行以下命令安装依赖：

    pip install sentence-transformers faiss-cpu

如果你有 NVIDIA GPU，推荐用 faiss-gpu（更快）：

    pip install faiss-gpu  # 需要 CUDA 环境

如果你是 macOS Apple Silicon，改为：

    pip install faiss-bin  # 或从源码编译
""")

# ============================================================================
# 第二步：预训练模型下载（自动，首次运行）
# ============================================================================

print("""
❷ 模型会自动下载到 ~/.cache/huggingface/hub/ 目录

第一次运行时：
- 会自动下载 GanymedeNil/text2vec-large-chinese（约 440MB）
- 耗时 5-10 分钟（取决于网络速度）
- 之后使用会自动从本地缓存读取（很快）

如果网络不稳定，可以手动下载：

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('GanymedeNil/text2vec-large-chinese')
    # 该命令会下载模型到本地缓存

""")

# ============================================================================
# 第三步：执行向量库构建（一次性，耗时 3-5 分钟）
# ============================================================================

print("""
❸ 构建向量库（仅需一次）：

    cd D:/Work/有救AI
    python scripts/build_vector_db.py

预期输出：
    加载试验库: original_data/clinical_trials/trials_structured.json
    ✅ 加载了 10000 个试验
    🤖 加载模型: GanymedeNil/text2vec-large-chinese
    🔄 向量化 10000 个试验文本...
    ✅ 向量化完成，生成向量形状: (10000, 384)
    ⚙️  构建 Faiss 索引...
    ✅ Faiss 索引构建完成，包含 10000 向量
    💾 保存向量库...
    ✅ 索引已保存: structured_data/vector_index/trials.faiss
    ✅ 元数据已保存: structured_data/vector_index/metadata.json

    ✨ 向量库构建完成！
       - 试验总数: 10000
       - 向量维度: 384
       - 预期查询时间: 5-10ms (top_20)
       - 索引大小: ~15.0 MB

""")

# ============================================================================
# 第四步：使用向量库进行匹配（运行时）
# ============================================================================

print("""
❹ 使用向量库：

    # 方式 1: 直接用 Web 表单
    python scripts/demo_server.py

    # 方式 2: 用脚本
    python scripts/run_match.py

    # 方式 3: 用 API
    python scripts/run_api.py

系统会自动：
- 加载 Faiss 索引和元数据
- 为患者信息向量化
- 检索相似试验（毫秒级）
- 融合规则分数进行排序
""")

# ============================================================================
# 文件列表
# ============================================================================

print("""
✅ 核心文件清单：

构建向量库：
  scripts/build_vector_db.py          # 一键构建脚本
  
改进的核心模块：
  codes/rag_index.py                  # 改进：用 SentenceTransformer + Faiss
  codes/trial_matcher.py              # 改进：添加融合函数（待添加）
  
配置和脚本：
  requirements.txt                    # 更新：添加 sentence-transformers + faiss
  scripts/demo_server.py              # 改进：集成向量搜索（待改进）
  
生成的文件（自动生成，勿手动修改）：
  structured_data/vector_index/trials.faiss      # Faiss 二进制索引
  structured_data/vector_index/metadata.json     # 元数据
""")

# ============================================================================
# 故障排除
# ============================================================================

print("""
⚠️  常见问题：

Q1: 安装 faiss-cpu 失败？
A: 可能需要 C++ 编译器。
   - Windows: 安装 Visual Studio Build Tools
   - macOS: 安装 Xcode Command Line Tools
   - Linux: apt-get install build-essential

Q2: 首次运行非常慢？
A: 正在下载模型（440MB）。耐心等待 5-10 分钟。
   可以查看 ~/.cache/huggingface/hub/ 目录确认下载进度。

Q3: build_vector_db.py 运行出错？
A: 检查：
   - original_data/clinical_trials/trials_structured.json 是否存在
   - 磁盘空间是否充足（建议 > 1GB）
   - 网络是否可连接（下载模型）

Q4: 查询速度还是很慢？
A: 可能原因：
   - 第一次查询：会加载模型到内存（一次性，后续很快）
   - Faiss 索引太大：建议用 GPU 版本或更大内存的机器
   - 可调参：batch_size（构建时）、top_k（查询时）

Q5: 想用其他语言模型？
A: 改 build_vector_db.py 的 --model 参数：

    python scripts/build_vector_db.py --model BAAI/bge-large-zh

   推荐模型列表：
   - GanymedeNil/text2vec-large-chinese (推荐，平衡)
   - BAAI/bge-large-zh (更好的语义，需要微调)
   - sentence-transformers/paraphrase-MiniLM-L6-v2 (快速，英文)
""")

# ============================================================================
# 性能数据
# ============================================================================

print("""
📊 性能预期：

离线（一次性）：
  - 向量化 1 万条数据：3-5 分钟 (CPU) / 30-60 秒 (GPU)
  - Faiss 索引构建：< 1 秒
  - 总存储：~20 MB (索引 + 元数据)

在线（每个患者）：
  - 患者向量化：10-20 ms
  - Faiss 检索 (top_20)：5-10 ms
  - 规则匹配：50-100 ms
  - 融合排序：< 5 ms
  - 总耗时：~100-150 ms ✅ 满足实时需求

内存占用：
  - Faiss 索引：~60 MB (10k 向量 × 384 维 × 4字节 float32)
  - 模型缓存：~440 MB (SentenceTransformer)
  - 总计：~500-600 MB
""")
