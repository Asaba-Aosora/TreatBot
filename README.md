# 有救AI — 患者临床试验智能匹配系统

**核心功能**：从病历（PDF）或手填信息提取患者画像，与 **496 条**招募中临床试验做**规则匹配 + 软语义排序**（地理距离、Jaccard），输出候选试验列表。

**产品定位**：给医生**筛选建议**——缺 ECOG、化验等核心字段时标「待核对」，**不因信息不全而零候选**（`matcher_layers_v2` 筛查模式）。**不是**自动入组决策。

**默认匹配入口**：`rank_trials`（规则引擎）。Faiss / 向量库有建库脚本，**尚未接入** `demo_server` 与默认 OCR 流水线。

---

## 现有成果

### ✅ 已完成模块

| 功能 | 核心文件 | 说明 |
|------|--------|------|
| **规则匹配引擎 v2** | `codes/trial_matcher.py` | 筛查语义：`eligible` / `needs_review` / `hard_excluded`；12 项化验按试验条款 pass/fail/unknown |
| **化验结果归一化** | `codes/lab_normalize.py` | `lab_results` → `lab_observations`（12 项 metric_id） |
| **患者整理（normalize）** | `codes/patient_matching_normalize.py` | 化验 curated、biomarker、分期推断、`_matching_normalize_report` |
| **文件名推断** | `codes/patient_filename_infer.py` | 从 PDF 名补癌种 / 线数 / 地点（仅补缺失） |
| **地理距离** | `codes/geo_admin.py` | cpca + adcode，多中心最短距离排序 |
| **OCR（云端）** | `codes/ocr_cloud.py` | 豆包 hybrid / Kimi / 阿里云；PDF → 结构化 JSON |
| **批量 OCR** | `scripts/batch_ocr.py` | 递归扫描 `dataset_patient`，跳过已成功 JSON |
| **化验清洗** | `scripts/fix_lab_result.py` | ↑↓ 状态、非化验行分离 |
| **匹配整理 CLI** | `scripts/normalize_patient_for_matching.py` | 产出 `*_fixed_matching.json`（**匹配金标准输入**） |
| **OCR（本地）** | `codes/ocr_ollama.py` | 基于 Ollama 视觉模型，离线运行 |
| **Web 匹配界面** | `web/demo_input.html` + `scripts/demo_server.py` | 手动录入 / 上传 OCR JSON |
| **FastAPI 后端** | `api/server.py` | REST API 集成 |
| **医学领域词汇库** | `codes/lab_lexicon.py`, `lab_rules.py` | 化验别名、×ULN 部分支持 |
| **向量索引（实验）** | `codes/rag_index.py`, `scripts/build_trial_index.py` | 哈希向量方案；**默认匹配未使用** |

---

## 下一步计划（Road Map）

| 优先级 | 任务 | 预期效果 |
|-------|------|--------|
| **🔴 高** | OCR 稳定性：超时页重试、漏检病例重跑 | 化验进系统率提升（当前主要瓶颈） |
| **🔴 高** | 10+ 病例医生标注 Top 候选是否合理 | 评测驱动规则迭代 |
| **🟡 中** | 化验 ×ULN、biomarker 硬规则扩展 | 更贴近试验入排原文 |
| **🟡 中** | 诊断规范化（`diagnosis_raw` / `cancer_type`） | 减少零候选（标签未对齐） |
| **🟢 低** | 接入 Faiss / 真实 embedding | 规则满足后语义召回与排序 |
| **🟢 低** | 匹配解释 UI | 得分分解、待核对项展示 |

> 阶段性评测与 OCR 漏检分析见 [docs/STAGE_REPORT.md](docs/STAGE_REPORT.md)。

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

### 方式 4️⃣ : 病历 PDF 全流程（推荐，需要 API 密钥）

**推荐流水线**（金标准工作文件为 `*_fixed_matching.json`）：

```powershell
# 1. 批量 OCR（默认跳过已有 success JSON）
python scripts/batch_ocr.py

# 2. 化验清洗（可选，OCR 脏数据多时建议）
python scripts/fix_lab_result.py input.json output_fixed.json

# 3. 整理为匹配输入 + 可选预览 Top 候选
python scripts/normalize_patient_for_matching.py --file output_patients/xxx_fixed.json --run-match
```

单份交互式 OCR：

```bash
python scripts/ocr_demo.py
```

PDF 样本目录：`original_data/dataset_patient/`（文件名建议含 `{癌种}{线数}{地点}`，如 `CHQI胰腺癌辽宁沈阳.pdf`）。

#### OCR 本地化（Ollama）

```bash
ollama serve
python scripts/run_ocr.py
```

详细步骤见 [docs/OLLAMA_GUIDE.md](docs/OLLAMA_GUIDE.md)。

---

### 方式 5️⃣ : 向量索引构建（实验，默认匹配未使用）

```bash
python scripts/build_trial_index.py
```

- 读取 `trials_structured.json`，生成 `structured_data/vector_index/trial_criteria_index.json`
- 当前 **demo / rank_trials 默认不走此索引**；见 [QUICKSTART_VECTOR_DB.md](docs/QUICKSTART_VECTOR_DB.md)

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
│  ├─ trial_matcher.py                # ⭐ 匹配引擎 v2（rank_trials / match_trial）
│  ├─ patient_matching_normalize.py   # OCR 患者 JSON → 匹配输入
│  ├─ patient_filename_infer.py       # 文件名 → 癌种/线数/地点
│  ├─ geo_admin.py                    # 省市区 → adcode / 距离
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
│  ├─ batch_ocr.py                    # ⭐ 批量 PDF OCR（跳过已成功）
│  ├─ normalize_patient_for_matching.py  # ⭐ 整理 → *_matching.json
│  ├─ ocr_demo.py                     # 单份 OCR 交互入口
│  ├─ run_ocr.py                      # 本地 Ollama OCR
│  │
│  ├─ build_trial_index.py            # 向量索引构建（实验，默认未接入匹配）
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
│  ├─ test_geo_admin.py               # 地理 / adcode 测试
│  ├─ test_filename_and_disease_match.py  # 文件名推断、分期、疾病匹配
│  └─ test_real_data.py               # 真实数据集成测试
│
├─ docs/                              # 文档与说明
│  ├─ STAGE_REPORT.md                 # ⭐ 阶段性汇报（10 例评测）
│  ├─ SESSION_HANDOFF.md              # 开发交接与命令速查
│  ├─ MATCHING_CHECKLIST.md           # 匹配规则与 12 项化验清单
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
   ├─ *_患者信息.json                  # OCR 原始输出
   ├─ *_fixed.json                    # 化验清洗后
   ├─ *_fixed_matching.json          # ⭐ 匹配金标准输入
   ├─ patient_trial_matches.html      # 离线匹配 HTML 报告
   ├─ batch_ocr.log                   # 批量 OCR 日志
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

### 完整闭环：OCR → fix → normalize → 匹配 → 评测

1. **OCR** — `batch_ocr.py` 或 `ocr_demo.py` → `*_患者信息.json`
2. **化验清洗** — `fix_lab_result.py` → `*_fixed.json`（OCR 脏数据多时建议）
3. **匹配整理** — `normalize_patient_for_matching.py` → `*_fixed_matching.json`
4. **医生补全** — ECOG、P0 化验等（见 normalize 报告 `missing_p0_metrics`）
5. **匹配评测**
   ```bash
   python scripts/benchmark_match_from_ocr_json.py --dir output_patients --match-mode strict
   python scripts/run_match.py   # 生成 HTML 报告
   ```
6. **OCR 金标准评测**（有 `*_fixed.json` 时）
   ```bash
   python scripts/eval_ocr_gold.py --raw <raw.json> --gold <fixed.json>
   ```
7. **回归测试** — `pytest tests/test_matcher_v2.py tests/test_geo_admin.py -q`

### 关键指标

- OCR：页级 timeout 率、P0 化验进系统率（见 [STAGE_REPORT.md](docs/STAGE_REPORT.md)）
- 匹配：候选数、`needs_review` / `eligible` 比例、疾病 Top1 标签是否正确
- 性能：单患者 × 496 试验约数秒级（取决于硬件）

---

## 试验与患者数据

- **试验库**：`original_data/clinical_trials/trials_structured.json`（**496** 条招募中项目）  
  同步脚本：`scripts/sync_xlsx_to_trials_json.py`

- **病历样本**：`original_data/dataset_patient/`（PDF；可含子目录）  
  当前阶段已 OCR + normalize **10** 例，详见 [STAGE_REPORT.md](docs/STAGE_REPORT.md)。

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
- **疾病匹配**、年龄/性别/ECOG/线数/化验 hard 规则
- **地理距离**、入排全文 Jaccard 软语义
- 缺 core 字段每条扣 3 分

查看结果中的 `reasons`、`review_items`、`checks` 了解逐项判定。

### Q4: 如何切换匹配模式？
**A：** 两种模式：
- **strict**（默认）：入组化验 fail → 不进候选列表
- **balanced**：入组化验 fail ≤ 1 仍可进列表

缺 ECOG/化验 unknown **不会**因此 hard_excluded，仅标 `needs_review`。

Web 表单和 API 都支持选择。

### Q5: 如何部署到生产环境？
**A：** 
1. 使用 `run_api.py` 启动 FastAPI 后端
2. 通过 Docker 或 systemd 进行服务管理
3. 推荐配置 Nginx 反向代理
4. 详见 [docs/IMPLEMENTATION_SPEC.md](docs/IMPLEMENTATION_SPEC.md) 部署章节

### Q6: 向量索引有什么用？
**A：** `rag_index.py` / `build_trial_index.py` 为**实验模块**：
- 当前默认匹配走 `rank_trials` 规则引擎，**未接入** Faiss
- 哈希向量方案；后续可选升级 embedding + 向量库
- 详见 [QUICKSTART_VECTOR_DB.md](docs/QUICKSTART_VECTOR_DB.md)

---

## 故障排除

| 问题 | 解决方案 |
|------|--------|
| `ModuleNotFoundError: codes` | 确保在项目根目录运行脚本；检查 `sys.path.insert(0, ...)` |
| API 返回 400 Bad Request | 检查 JSON 格式；必须包含 `patient.diagnosis` 或 `cancer_type` |
| OCR 结果为空 / timeout | 检查 API 密钥与余额；见 `errors` 字段；可单份重跑 `batch_ocr.py` |
| 化验全缺但 PDF 里有 | 多为 OCR 漏检（页 timeout），非匹配 bug；重跑 OCR 或人工补录 |
| 匹配耗时过长 | 检查试验库大小；可用 `--max-trials` 参数限制（见脚本 --help） |
| 化验项无法识别 | 检查 `lab_lexicon.py` 是否包含该项代码；提交反馈以扩展词汇库 |

---

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/NLP_FINAL_REPORT.md](docs/NLP_FINAL_REPORT.md) | **NLP 课程期末项目报告**（IE + 文本匹配） |
| [docs/STAGE_REPORT.md](docs/STAGE_REPORT.md) | **阶段性汇报**：10 例评测、OCR 漏检分析 |
| [docs/SESSION_HANDOFF.md](docs/SESSION_HANDOFF.md) | 开发交接、常用命令 |
| [docs/MATCHING_CHECKLIST.md](docs/MATCHING_CHECKLIST.md) | 匹配规则、12 项化验、v2 筛查语义 |
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

**最后更新**：2026-06-03  
**匹配引擎**：`matcher_layers_v2`（筛查模式）  
**核心功能**：✅ PDF→matching 流水线 | ✅ 496 试验规则匹配 | ⏳ OCR 稳定性 / Faiss 待迭代
