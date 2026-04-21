# 有救AI — 患者临床试验智能匹配

从病历（PDF）或手填信息提取患者画像，与临床试验库做规则匹配，并按地理距离等维度排序输出候选试验。

---

## 快速开始

```bash
pip install -r requirements.txt
```

### 推荐路径

| 用途 | 命令 | 说明 |
|------|------|------|
| Web 表单录入并匹配 | `python scripts/demo_server.py` | 浏览器打开 http://127.0.0.1:8000/ |
| 后端 API（FastAPI） | `python scripts/run_api.py` | Swagger：http://127.0.0.1:8010/docs |
| 云端 OCR 病历 → JSON | `python scripts/ocr_demo.py` | 需配置豆包/Kimi 等 API，见下文 |
| 脚本直接匹配（不调 OCR） | `python scripts/run_match.py` | 在脚本内编辑患者字典后运行 |
| 构建试验向量索引（RAG） | `python scripts/build_trial_index.py` | 依赖 `codes/rag_index.py` |
| OCR 金标准评测（raw vs fixed） | `python scripts/eval_ocr_gold.py --raw ... --gold ...` | 评估结构化质量 |
| OCR JSON 匹配压测 | `python scripts/benchmark_match_from_ocr_json.py --dir output_patients` | 评估匹配耗时/候选数 |

### 可选：本地 Ollama OCR

无云端密钥时可用本地视觉模型（速度/精度因机器与模型而异）：

```bash
ollama serve
python scripts/run_ocr.py
```

实现见 `codes/ocr_ollama.py`。详细步骤见 [docs/QUICK_START.md](docs/QUICK_START.md)、[docs/OLLAMA_GUIDE.md](docs/OLLAMA_GUIDE.md)。

---

## 环境变量（`.env`）

在项目根目录创建 `.env`（勿提交仓库）。常见项：

| 变量 | 说明 |
|------|------|
| `DOUBAO_API_KEY` 或 `ARK_API_KEY` | 豆包多模态 OCR（推荐） |
| `DOUBAO_MODEL` | 可选，覆盖默认视觉模型名 |
| `KIMI_API_KEY` / `ALIYUN_API_KEY` | 其他 OCR 提供商 |
| `OCR_MAX_PAGES` | 限制 PDF 最多 OCR 页数，控制耗时与费用 |
| `HYBRID_HQ_TOP_K` | 混合模式下高质量复扫页数上限 |

豆包开通与密钥说明可参考仓库内 [豆包API配置指南.md](豆包API配置指南.md)。

---

## 项目结构（与仓库一致）

```
有救AI/
├── README.md
├── requirements.txt
├── 豆包API配置指南.md
├── api/
│   └── server.py                 # FastAPI 服务实现（由 run_api 加载）
├── codes/
│   ├── ocr_cloud.py              # 云端多模态 OCR + 文本结构化提取
│   ├── ocr_ollama.py             # 本地 Ollama OCR（可选）
│   ├── trial_matcher.py          # 匹配引擎（含化验规则等）
│   ├── lab_normalize.py          # 检验结果归一化
│   ├── lab_lexicon.py / lab_rules.py
│   ├── trial_parse.py            # 试验条款解析辅助
│   ├── rag_index.py              # 试验向量索引
│   └── schemas.py                # 数据结构定义
├── scripts/
│   ├── demo_server.py            # Flask 演示站
│   ├── run_api.py                # 启动 API
│   ├── ocr_demo.py               # 云端 OCR 演示入口
│   ├── run_match.py              # 离线匹配示例
│   ├── run_ocr.py                # 本地 Ollama 入口
│   ├── build_trial_index.py
│   ├── sync_trials.py
│   ├── parse_trials_to_rules.py
│   ├── eval_regression.py
│   ├── eval_ocr_gold.py          # OCR 原始输出 vs 医生修订评测
│   └── benchmark_match_from_ocr_json.py
├── data_preparation/
│   ├── inclusion_list.py         # 入排条件文本 → 结构化字段
│   └── lines.py                  # 治疗线数等文本解析
├── tests/                        # pytest
├── docs/
│   ├── QUICK_START.md
│   ├── OLLAMA_GUIDE.md
│   ├── GEO_DISTANCE_EXPLANATION.md
│   ├── IMPLEMENTATION_SPEC.md    # 实现约定与 schema
│   └── STORAGE_MIGRATION.md
├── web/
│   └── demo_input.html
├── original_data/                # 原始试验/病历数据（默认不纳入版本控制）
├── output_patients/              # 运行输出（默认 gitignore）
└── structured_data/              # 中间/导出数据（默认 gitignore）
```

---

## 试验与患者数据

- 试验库示例路径：`original_data/clinical_trials/trials_structured.json`（若本地未放置数据，请先按团队数据流程同步）。
- 患者 PDF 样本：`original_data/dataset_patient/`（同上，由 `.gitignore` 忽略时可自建目录）。

---

## 测试

```bash
pytest tests/
```

---

## 医生标注驱动迭代（推荐流程）

当你有医生修订后的 `*_fixed.json` 时，建议按下面闭环迭代：

1) 先跑基线评测，量化 OCR 结构化误差

```bash
python scripts/eval_ocr_gold.py \
  --raw "output_patients/CHQI胰腺癌辽宁沈阳_患者信息.json" \
  --gold "output_patients/CHQI胰腺癌辽宁沈阳_患者信息_fixed.json" \
  --save "structured_data/eval/chqi_gold_baseline.json"
```

2) 用修订样本验证匹配稳定性（严格/平衡模式都建议跑）

```bash
python scripts/benchmark_match_from_ocr_json.py --file "output_patients/CHQI胰腺癌辽宁沈阳_患者信息_fixed.json" --match-mode strict
python scripts/benchmark_match_from_ocr_json.py --file "output_patients/CHQI胰腺癌辽宁沈阳_患者信息_fixed.json" --match-mode balanced
```

3) 每次修改 OCR/匹配后，至少回归：
- `pytest tests/`
- `scripts/eval_ocr_gold.py` 指标是否退化
- `balanced` 模式候选是否异常减少

当前系统会在 OCR 后处理时自动把 `lab_results` 分流为：
- `lab_results`：可计算化验项（含 `range_low/range_high/reference_range_raw/source_abnormal_flag`）
- `genomics_raw`：基因/突变条目
- `_ocr_meta_unsorted`：元信息与叙事噪声

---

## 文档索引

- [docs/QUICK_START.md](docs/QUICK_START.md) — 环境与常见问题  
- [docs/OLLAMA_GUIDE.md](docs/OLLAMA_GUIDE.md) — Ollama 与模型选择  
- [docs/GEO_DISTANCE_EXPLANATION.md](docs/GEO_DISTANCE_EXPLANATION.md) — 地理匹配说明  
- [docs/IMPLEMENTATION_SPEC.md](docs/IMPLEMENTATION_SPEC.md) — 接口与数据结构约定  
- [docs/STORAGE_MIGRATION.md](docs/STORAGE_MIGRATION.md) — 存储迁移说明  

---

## 许可证

MIT

**最后更新**：2026-04-20
