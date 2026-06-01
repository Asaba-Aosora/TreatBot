# 有救AI — 患者临床试验智能匹配系统

**核心功能**：从病历（PDF）或手填信息提取患者画像，与临床试验库做**规则匹配 + 向量语义匹配**，按匹配度、地理距离等维度排序输出候选试验。

---

## 现有成果

### ✅ 已完成模块

| 功能 | 核心文件 | 说明 |
|------|--------|------|
| **规则匹配引擎** | `codes/trial_matcher.py` | 支持入排条件、化验指标、生物标志物等多维度规则匹配 |
| **化验结果归一化** | `codes/lab_normalize.py` | 自动将非结构化化验结果转换为标准化指标与观测值 |
| **OCR（云端）** | `codes/ocr_cloud.py` | 支持豆包、Kimi、阿里云等多家云厂商API |
| **OCR（本地）** | `codes/ocr_ollama.py` | 基于本地 Ollama 视觉模型，离线运行 |
| **向量索引框架** | `codes/rag_index.py` | 基于哈希的试验条款向量化与向量搜索 (256维) |
| **向量索引构建** | `scripts/build_trial_index.py` | 将试验入排条件拆分为 chunks 并向量化 |
| **语义相似度** | `codes/trial_matcher.py::semantic_similarity()` | 基于 token 集合的语义相似度计算，已融入排序 |
| **Web 匹配界面** | `web/demo_input.html` + `scripts/demo_server.py` | 手动录入模式 / OCR JSON 上传模式 |
| **FastAPI 后端** | `api/server.py` | 可供外部系统集成的 REST API |
| **医学领域词汇库** | `codes/lab_lexicon.py`, `lab_rules.py` | 化验指标、操作符、单位的标准化映射 |

---

## 下一步计划（Road Map）

| 优先级 | 任务 | 预期效果 |
|-------|------|--------|
| **🔴 高** | 集成真实 embedding 模型（CLIP / 医学 BERT） | 替换当前哈希方案，显著提升语义匹配准确度 |
| **🔴 高** | 集成向量数据库（Faiss / Milvus） | 支持百万级试验库的高效向量检索 |
| **🟡 中** | 医学 LLM 结构化提取优化 | 针对医学文本的更精准 OCR 后处理 |
| **🟡 中** | 患者/试验元数据补全（知识图谱）| 地理位置、医疗机构、医生信息丰富化 |
| **🟢 低** | 可视化匹配解释（Explainability） | 用户界面展示每个匹配的得分分解 |

---

## 快速开始

### 1. 环境配置

```bash
# 克隆项目
git clone <repo-url>
cd 有救AI

# 安装依赖
pip install -r requirements.txt

# 创建 .env 文件（见下文环境变量配置）
cp .env.example .env  # 如有示例文件
```

### 2. 环境变量（`.env`）

在项目根目录创建 `.env`（勿提交仓库）。常见项：

| 变量 | 说明 | 必需 |
|------|------|------|
| `DOUBAO_API_KEY` 或 `ARK_API_KEY` | 豆包多模态 OCR（推荐） | 仅 OCR 时需要 |
| `DOUBAO_MODEL` | 覆盖默认视觉模型名 | 可选 |
| `KIMI_API_KEY` | Kimi OCR API Key | 可选替代方案 |
| `ALIYUN_API_KEY` / `ALIYUN_APP_CODE` | 阿里云 OCR | 可选替代方案 |
| `OCR_MAX_PAGES` | 限制 PDF 最多 OCR 页数 | 可选，默认全部 |
| `HYBRID_HQ_TOP_K` | 混合模式下高质量复扫页数上限 | 可选 |

**获取 API 密钥**：参考 [豆包API配置指南.md](豆包API配置指南.md)（仓库内）。

---

## 使用指南

### 方式 1️⃣ : Web 表单录入（**最简单，推荐初始使用**）

#### 启动服务
```bash
python scripts/demo_server.py
```
**输出**：
```
Demo server running at http://127.0.0.1:8000/
打开浏览器访问输入页面，填写后提交即可查看匹配结果。
```

#### 操作步骤
1. 浏览器打开 http://127.0.0.1:8000/
2. 进入 **手动录入模式**（默认）或 **上传 OCR JSON 模式**
3. **手动录入**：填写患者诊断、分期、年龄、性别、化验值等
4. **上传 JSON**：直接上传 OCR 输出的 JSON 文件（含 `patient` 字段）
5. 点击 **提交** → 系统自动生成匹配结果
6. 查看输出：`output_patients/patient_trial_matches.html`

**界面功能**：
- ✓ 表单实时校验（诊断、分期、ECOG 值范围检查）
- ✓ 两种输入模式切换
- ✓ 生物标志物多值逗号分隔支持
- ✓ 匹配模式选择（严格 / 平衡）

---

### 方式 2️⃣ : FastAPI 后端（**适合系统集成**）

#### 启动 API 服务
```bash
python scripts/run_api.py
```
**输出**：
```
INFO:     Uvicorn running on http://127.0.0.1:8010
INFO:     Application startup complete
```

#### 调用 API 示例

**获取 Swagger 文档**：浏览器打开 http://127.0.0.1:8010/docs

**Python 客户端**：
```python
import requests
import json

payload = {
    "patient": {
        "diagnosis": "胰腺癌",
        "cancer_stage": "III期",
        "age": 65,
        "gender": "男",
        "ecog": 1,
        "treatment_lines": 1,
        "location": "辽宁 沈阳",
        "biomarkers": ["KRAS突变"],
        "lab_results": []
    },
    "match_mode": "balanced"
}

resp = requests.post("http://127.0.0.1:8010/match", json=payload)
result = resp.json()
print(json.dumps(result, ensure_ascii=False, indent=2))
```

**返回值**：包含 `patient`、`match_mode`、`data_quality`、`matches` 字段。

---

### 方式 3️⃣ : 脚本直接匹配（**快速测试，不调 OCR**）

```bash
python scripts/run_match.py
```

**操作**：
- 编辑脚本内的 `patient` 字典（约 50-60 行）
- 填写诊断、分期、年龄等患者信息
- 运行脚本 → 自动生成 `output_patients/patient_trial_matches.html`

---

### 方式 4️⃣ : OCR 病历提取（需要 API 密钥）

#### OCR Demo（云端）
```bash
python scripts/ocr_demo.py
```
- 选择 PDF 病历文件
- 系统调用配置的云端 OCR API（豆包/Kimi 等）
- 输出结构化 JSON 到 `output_patients/`

#### OCR 本地化（Ollama）
```bash
# 先启动 Ollama 服务
ollama serve

# 另开终端，运行 OCR 脚本
python scripts/run_ocr.py
```
详细步骤见 [docs/OLLAMA_GUIDE.md](docs/OLLAMA_GUIDE.md)。

---

### 方式 5️⃣ : 向量索引构建（RAG 基础）

```bash
python scripts/build_trial_index.py
```
- 读取 `original_data/clinical_trials/trials_structured.json`
- 将试验入排条件向量化并存储为 `structured_data/vector_index/trial_criteria_index.json`
- 输出：`Chunk数量: <N>`

---

## 项目结构详解

```
有救AI/
│
├─ README.md                          # 本文件
├─ requirements.txt                   # 依赖清单
├─ .env                               # 环境变量（本地配置，勿提交）
├─ .gitignore                         # Git 忽略规则
│
├─ api/
│  └─ server.py                       # FastAPI 应用主文件
│                                     # ├─ POST /match: 患者-试验匹配
│                                     # ├─ GET  /health: 健康检查
│                                     # └─ Swagger 自动生成文档
│
├─ codes/                             # 核心业务逻辑
│  ├─ trial_matcher.py                # ⭐ 匹配引擎（规则、语义、排序）
│  │                                  #    ├─ build_patient_input()
│  │                                  #    ├─ load_trials()
│  │                                  #    ├─ rank_trials()
│  │                                  #    ├─ semantic_similarity()
│  │                                  #    └─ summarize_patient_data_quality()
│  │
│  ├─ lab_normalize.py                # 化验结果标准化
│  │                                  #    ├─ normalize_ocr_lab_payload()
│  │                                  #    └─ attach_lab_observations()
│  │
│  ├─ lab_lexicon.py                  # 化验指标词汇库（别名映射）
│  │                                  #    └─ METRIC_ALIASES 字典
│  │
│  ├─ lab_rules.py                    # 化验规则定义
│  │                                  #    ├─ build_clause()
│  │                                  #    └─ normalize_metric_key()
│  │
│  ├─ ocr_cloud.py                    # 云端 OCR 集成
│  │                                  #    ├─ ocr_with_doubao()
│  │                                  #    ├─ ocr_with_kimi()
│  │                                  #    └─ ocr_with_aliyun()
│  │
│  ├─ ocr_ollama.py                   # 本地 Ollama OCR
│  │                                  #    └─ ocr_with_ollama()
│  │
│  ├─ rag_index.py                    # 向量索引框架
│  │                                  #    ├─ _hash_embed()
│  │                                  #    ├─ _cosine()
│  │                                  #    └─ TrialVectorIndex 类
│  │
│  ├─ rag_clause_assist.py            # RAG 模板库与候选抽取
│  │                                  #    └─ extract_rag_lab_clause_candidates()
│  │
│  ├─ trial_parse.py                  # 试验条款解析辅助工具
│  │
│  └─ schemas.py                      # 数据结构定义（Pydantic models）
│
├─ scripts/                           # 可执行脚本
│  ├─ demo_server.py                  # ⭐ Web 表单服务器（推荐入口）
│  ├─ run_api.py                      # ⭐ FastAPI 后端启动
│  ├─ run_match.py                    # 离线匹配脚本（手写患者数据）
│  │
│  ├─ ocr_demo.py                     # OCR 演示入口
│  ├─ run_ocr.py                      # 本地 Ollama OCR 运行脚本
│  │
│  ├─ build_trial_index.py            # 向量索引构建脚本
│  ├─ build_learning_artifacts.py     # 学习工件构建
│  ├─ parse_trials_to_rules.py        # 试验规则解析
│  ├─ sync_trials.py                  # 试验库同步
│  │
│  ├─ eval_ocr_gold.py                # OCR 评测（raw vs gold standard）
│  ├─ eval_regression.py              # 回归测试
│  ├─ benchmark_match_from_ocr_json.py│ 匹配性能基准测试
│  └─ fix_lab_result.py               # 化验结果修复工具
│
├─ web/
│  └─ demo_input.html                 # 📱 Web 匹配界面（HTML）
│
├─ data_preparation/                  # 数据预处理工具
│  ├─ inclusion_list.py               # 入排条件文本解析
│  └─ lines.py                        # 治疗线数等解析
│
├─ tests/                             # 测试套件 (pytest)
│  ├─ test_matcher_v2.py              # 匹配引擎测试
│  ├─ test_lab_normalize.py           # 化验归一化测试
│  ├─ test_ocr_cloud.py               # OCR 测试
│  ├─ test_geo.py                     # 地理距离测试
│  └─ test_real_data.py               # 真实数据集成测试
│
├─ docs/                              # 文档与说明
│  ├─ QUICK_START.md                  # 快速开始指南
│  ├─ OLLAMA_GUIDE.md                 # 本地 Ollama 详细步骤
│  ├─ IMPLEMENTATION_SPEC.md          # 实现细节与 schema 约定
│  ├─ GEO_DISTANCE_EXPLANATION.md     # 地理距离计算说明
│  └─ STORAGE_MIGRATION.md            # 存储迁移指南
│
├─ original_data/                     # 原始数据（.gitignore）
│  ├─ clinical_trials/
│  │  └─ trials_structured.json       # 试验库（JSON 格式）
│  └─ dataset_patient/                # 病历样本 PDF
│
├─ structured_data/                   # 中间与输出数据（.gitignore）
│  ├─ eval/
│  │  ├─ chqi_gold_baseline.json      # OCR 评测基线
│  │  └─ fixture_patient.json         # 测试患者 fixture
│  ├─ trial_parsed/
│  │  ├─ rules_bundle.json            # 试验规则 bundle
│  │  └─ needs_review.jsonl           # 需人工审核的条款
│  └─ vector_index/
│     └─ trial_criteria_index.json    # 向量索引（build_trial_index.py 生成）
│
└─ output_patients/                   # 运行输出（.gitignore）
   ├─ patient_trial_matches.html      # 📄 最终匹配结果（Web 界面）
   ├─ patient_trial_matches.json      # 匹配结果 JSON
   └─ temp_images/                    # 临时 OCR 图片缓存
```

---

## 测试与评测

### 单元与集成测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_matcher_v2.py -v
pytest tests/test_lab_normalize.py -v
```

### OCR 结构化质量评测

当有医生修订后的 `*_fixed.json` 金标准时，评测 OCR 输出质量：

```bash
python scripts/eval_ocr_gold.py \
  --raw "output_patients/CHQI胰腺癌辽宁沈阳_患者信息.json" \
  --gold "output_patients/CHQI胰腺癌辽宁沈阳_患者信息_fixed.json" \
  --save "structured_data/eval/chqi_gold_baseline.json"
```

### 匹配性能基准测试

评测匹配耗时和候选试验数量：

```bash
# 测试单个患者 JSON
python scripts/benchmark_match_from_ocr_json.py \
  --file "output_patients/patient_info.json" \
  --match-mode strict

# 批量评测整个目录
python scripts/benchmark_match_from_ocr_json.py \
  --dir output_patients \
  --match-mode balanced
```

---

## 迭代工作流（推荐）

### 完整闭环：OCR → 标注 → 评测 → 优化

1. **OCR 病历**
   ```bash
   python scripts/ocr_demo.py
   # 生成 output_patients/patient_info.json
   ```

2. **医生标注修订**（人工审核，生成 `*_fixed.json`）

3. **评测 OCR 质量**
   ```bash
   python scripts/eval_ocr_gold.py --raw <raw.json> --gold <fixed.json>
   ```

4. **验证匹配稳定性**（用修订后的患者数据）
   ```bash
   # 严格模式
   python scripts/benchmark_match_from_ocr_json.py --file <fixed.json> --match-mode strict
   
   # 平衡模式
   python scripts/benchmark_match_from_ocr_json.py --file <fixed.json> --match-mode balanced
   ```

5. **回归测试**（确保无功能退化）
   ```bash
   pytest tests/ -v
   ```

### 关键指标

- OCR 结构化准确度（精准率/召回率）
- 匹配耗时 < 100ms per patient
- 平衡模式候选试验数稳定（通常 5-20 个）
- 高分候选与临床实际相符度

---

## 试验与患者数据

- **试验库**：`original_data/clinical_trials/trials_structured.json`  
  若本地未放置数据，请先按团队数据流程同步。

- **病历样本**：`original_data/dataset_patient/`  
  由 `.gitignore` 忽略，请自建目录放置 PDF 样本。

---

## 常见问题

### Q1: 我没有 API 密钥，可以使用系统吗？
**A：** 可以。用以下方式：
- **Web 表单手动录入模式**（`demo_server.py`）：完全无需 API
- **本地 Ollama OCR**（`ocr_ollama.py`）：离线运行，无需云端密钥
- **脚本直接匹配**（`run_match.py`）：手写患者信息，无需 OCR

### Q2: 化验结果如何输入？
**A：** 支持两种方式：
1. **Web 表单**：直接在界面填写化验项代码 + 数值 + 单位
2. **JSON**：`patient.lab_results` 数组，格式见 [docs/IMPLEMENTATION_SPEC.md](docs/IMPLEMENTATION_SPEC.md)

系统会自动归一化为标准指标。

### Q3: 为什么某个试验排名很靠后？
**A：** 匹配分数由多个维度组成：
- **规则匹配**（入排条件）：权重最高
- **化验指标**：权重次高
- **地理距离**：权重较低
- **语义相似度**：补充维度

查看 HTML 结果页面中的"检查详情"表格，可看到每个试验的逐项评分。

### Q4: 如何切换匹配模式？
**A：** 系统提供两种模式：
- **严格模式**（`strict`）：要求所有入排条件严格符合
- **平衡模式**（`balanced`）：允许部分条件模糊匹配，候选更多

Web 表单和 API 都支持选择。

### Q5: 如何部署到生产环境？
**A：** 
1. 使用 `run_api.py` 启动 FastAPI 后端
2. 通过 Docker 或 systemd 进行服务管理
3. 推荐配置 Nginx 反向代理
4. 详见 [docs/IMPLEMENTATION_SPEC.md](docs/IMPLEMENTATION_SPEC.md) 部署章节

### Q6: 向量索引有什么用？
**A：** 当前向量索引（`rag_index.py`）：
- 用于在试验入排条件中做语义检索（补充规则匹配）
- 目前采用简化的哈希方案
- 计划升级为真实 embedding 模型（CLIP / 医学 BERT）

---

## 故障排除

| 问题 | 解决方案 |
|------|--------|
| `ModuleNotFoundError: codes` | 确保在项目根目录运行脚本；检查 `sys.path.insert(0, ...)` |
| API 返回 400 Bad Request | 检查 JSON 格式；必须包含 `patient.diagnosis` 或 `cancer_type` |
| OCR 结果为空 | 检查 API 密钥有效性；检查 PDF 质量（清晰度、页数） |
| 匹配耗时过长 | 检查试验库大小；可用 `--max-trials` 参数限制（见脚本 --help） |
| 化验项无法识别 | 检查 `lab_lexicon.py` 是否包含该项代码；提交反馈以扩展词汇库 |

---

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/QUICK_START.md](docs/QUICK_START.md) | 环境配置、常见问题、初始化步骤 |
| [docs/OLLAMA_GUIDE.md](docs/OLLAMA_GUIDE.md) | Ollama 本地部署、模型下载、性能优化 |
| [docs/IMPLEMENTATION_SPEC.md](docs/IMPLEMENTATION_SPEC.md) | 接口约定、数据结构、匹配算法详解 |
| [docs/GEO_DISTANCE_EXPLANATION.md](docs/GEO_DISTANCE_EXPLANATION.md) | 地理距离计算方法、位置匹配逻辑 |
| [docs/STORAGE_MIGRATION.md](docs/STORAGE_MIGRATION.md) | 数据库迁移、备份恢复、版本升级 |
| [豆包API配置指南.md](豆包API配置指南.md) | 豆包 OCR 注册、密钥配置、额度管理 |

---

## 联系与反馈

- **问题报告**：提交 Issue 至仓库
- **功能建议**：讨论区或 Pull Request
- **性能问题**：附带 `benchmark_match_from_ocr_json.py` 的输出日志

---

## 许可证

MIT License — 详见 `LICENSE` 文件

---

**最后更新**：2026-05-14  
**当前版本**：v1.0 (Beta)  
**核心功能**：✅ 规则匹配 | ✅ 向量索引框架 | 🚀 实际 embedding 集成中
