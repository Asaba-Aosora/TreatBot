# 面向临床试验匹配的中文医疗病历信息抽取与文本约束排序

**NLP 课程期末项目报告**

| 项目 | 内容 |
|------|------|
| 课程 | 自然语言处理（期末项目） |
| 系统名称 | 有救AI — 临床试验患者-试验匹配 |
| 完成日期 | 2026-06-03 |
| 代码仓库 | 有救AI（本地项目） |
| 配套数据 | `structured_data/stage_report_summary.json`；10 例 `*_fixed_matching.json` |

---

## 摘要

临床试验患者筛选依赖大量非结构化中文病历（PDF、检验报告、病理报告等）。本项目将**临床试验匹配**形式化为：**医疗文档信息抽取（IE）** + **文本约束下的候选排序**两个连贯的 NLP 子任务。系统从 PDF 经多模态大模型 OCR 得到多页文本，抽取患者诊断、化验、生物标志物等槽位，经词典归一化与规则后处理后，与 496 条试验的入排条件进行 lexical 疾病匹配及约束满足检查，输出排序后的候选试验列表。

在 **10 例真实中文病历** 上的 case study 表明：（1）当 IE 较完整时（如 CHQI，11/12 项化验），strict 模式可将候选收窄至 7 条且 Top1 疾病标签正确；（2）OCR 页级超时是结构化 recall 的主要瓶颈，7/10 例化验稀少伴随 `Request timed out`，其中 CHRO 经人工核对源 PDF 含化验但系统未抽出；（3）针对 TNM 噪声导致的疾病误匹配（HAQI：`TXNXM1` 中单字母 `T` 误命中「T/NK 细胞淋巴瘤」），词典规范化与 token 过滤可有效修复。本工作展示了领域 IE 与可解释文本匹配的结合，并讨论了缺失信息处理（unknown vs fail）在真实临床文本场景下的必要性。

**关键词**：临床自然语言处理；信息抽取；中文医疗文本；OCR；文本匹配；缺失信息

---

## 1 引言

### 1.1 背景与动机

肿瘤患者参与临床试验前，需对照大量入组/排除条件（年龄、ECOG、化验阈值、疾病类型、生物标志物等）。这些信息分散在多页 PDF 病历中，格式不统一，含表格、缩写与同义词。人工筛选耗时且易漏；完全自动「判定入组」又不具备可审计性与安全性。

本项目的 NLP 视角是：将问题拆解为

1. **从自由文本中抽取结构化患者表示**（Information Extraction）；
2. **将患者表示与试验文本化入排条件对齐**（lexical / constraint-based matching）。

这与经典 NER、关系抽取课程中的「槽位填充」一致，但增加了**多页文档、化验表格、高缺失率**等现实约束。

### 1.2 任务概述

| NLP 子任务 | 输入 | 输出 |
|------------|------|------|
| **T1 文档级 IE** | OCR 多页中文医疗文本 | JSON 槽位：diagnosis、cancer_type、lab_observations、biomarkers 等 |
| **T2 文本规范化** | 原始 diagnosis / 化验 item 字符串 | 规范癌种、metric_id、分期 I–IV |
| **T3 疾病文本匹配** | 患者 disease text ↔ 试验「疾病三级标签」 | disease_match（bool）+ matching_labels |
| **T4 约束排序** | 结构化字段 + 试验入排原文 | 排序候选列表 + pass/fail/unknown 判定 |

下游的年龄/ECOG/化验数值比较以**结构化字段上的约束推理**实现，本文重点论述 T1–T4 中的文本处理部分。

### 1.3 贡献（课程项目层面）

1. 设计并实现一条可复现的 **中文医疗 PDF → 结构化患者画像 → 文本约束匹配** 流水线；
2. 针对中文肿瘤病历提出并验证 **TNM/分期噪声过滤、癌种同义词、文件名弱监督槽位** 等规范化策略；
3. 在 10 例真实数据上进行 **case study 与 OCR 失败分析**，区分「源文档缺失」与「抽取漏检」；
4. 讨论 **缺失槽位**（unknown）与 **明确违反**（fail）在筛查式匹配中的 NLP 语义设计。

---

## 2 相关工作

**临床信息抽取（Clinical IE）**  
i2b2/n2c2 等评测推动从 EHR 中抽取诊断、药物、化验；中文场景常见挑战包括无边界词、简称与嵌套诊断（如「胃恶性肿瘤 TXNXM1（Ⅳ）」）。本项目采用 **LLM 多模态 OCR + 规则后处理** 的 hybrid 路线，而非纯 CRF/BERT-NER，原因是输入为 PDF 图像且含复杂表格。

**生物医学术语规范化**  
SNOMED、ICD 等本体用于 entity linking；本项目采用**轻量级同义词表**（如 胃恶性肿瘤→胃癌）与 **12 项化验 metric_id 别名表**（`lab_lexicon.py`），对齐内部试验库标签而非国际编码，属于 domain-specific normalization。

**文本相似度与匹配**  
试验匹配可建模为 document ranking。本项目使用 **子串/词片段 Jaccard**（`semantic_similarity`）作为入排全文的 lexical 相似度，未使用预训练句向量；向量检索（Faiss）列为未来工作。

**缺失与不确定性 NLP**  
开放信息抽取与 partial annotation 中，missing 与 unknown 的处理影响下游决策。本项目在匹配层显式区分 **unknown（不硬拒）** 与 **fail（硬拒）**，对应筛查而非判定场景。

---

## 3 数据

### 3.1 试验库（文本侧）

- 来源：`original_data/clinical_trials/trials_structured.json`
- 规模：**496** 条招募中项目
- 每条含「入组条件」「排除条件」「疾病三级标签」等**非结构化中文文本**，由 `parse_trial_condition` 正则抽取年龄、ECOG、化验 clause 等。

### 3.2 患者病历（评测集）

- 来源：`original_data/dataset_patient/` 下 **10 份 PDF**（全库 18 份，其余 OCR 因 API 欠费未完成）
- 癌种覆盖：胰腺癌、胃癌、胆管癌、尿路上皮癌、胶质瘤等
- 经 OCR → fix → normalize 得到 `output_patients/*_fixed_matching.json`

### 3.3 标注与评测设定

**无大规模 gold 标注语料**；采用：

- **自动统计**：`lab_observations` 数量、P0 缺失、OCR `errors`、strict 候选数；
- **人工核对**：CHRO 源 PDF 是否含化验；HAQI 修复前后疾病 Top 标签；
- **Case study**：CHQI / HAQI / CHRO 三个代表性病例。

该设定符合课程项目在有限数据下的可行评测方式，并在讨论中说明局限。

---

## 4 方法

### 4.1 总体架构

```
PDF
 → 图像化 (pdf2image)
 → 多模态 LLM 逐页 OCR (hybrid: 全页快扫 + 关键页高精复扫)
 → PatientExtractor: 全文 → patient JSON
 → fix_lab_result: 化验行清洗
 → normalize_patient_for_matching: 槽位归一 + 报告
 → rank_trials: 疾病匹配 + 约束 + 排序
```

核心代码：`codes/ocr_cloud.py`、`codes/patient_matching_normalize.py`、`codes/trial_matcher.py`。

### 4.2 T1：文档级信息抽取

**OCR**  
使用豆包视觉 API，hybrid 模式：先 160 DPI 并发扫全页，再对关键页 300 DPI 复扫。输出 `raw_ocr_texts[]` 与合并全文。

**结构化抽取**  
`PatientExtractor.extract_from_text` 从全文抽取 patient 字典，包括 diagnosis、lab_results（item/value/unit/range）、genomics 等。抽取由 LLM 完成，属于 **generative IE**。

**失败模式**  
页级 `Request timed out` 导致 `raw_ocr_texts[i]` 为空；后续 IE 无法恢复该页信息（见 §6.2）。

### 4.3 T2：文本规范化与槽位补全

**化验归一化**  
- `lab_normalize.attach_lab_observations`：将 `lab_results[].item` 映射到 12 个 `metric_id`（wbc, anc, plt, hb, tbil, alt, ast, cr, alb, inr, aptt, pt）。
- 多行竞争同一 metric 时按 item 与别名匹配得分选最优行（`patient_matching_normalize._merge_metric_rows`）。

**诊断与癌种**  
- `normalize_diagnosis_for_matching`：去除 `TXNXM1`、KPS、NRS 等噪声；同义词表 `CANCER_SYNONYMS`（胃恶性肿瘤→胃癌）。
- `build_patient_disease_text`：合并 `cancer_type` + `diagnosis` 供匹配使用。

**分期抽取**  
- `infer_stage_from_text`：规则优先级 — 带「期」→ 括号罗马数字 `（Ⅳ）` → TNM M1；输出 I–IV。

**文件名弱监督**（`patient_filename_infer.py`）  
从 `{癌种}{地点}{线数}.pdf` 补缺失槽位，如 `HAQI胃癌一线进展.pdf` → cancer_type=胃癌, treatment_lines=1。仅填空，冲突写入 report。

**生物标志物**  
自 OCR 全文正则抽取 PD-L1、MSI、TMB、KRAS 等，写入 `biomarkers[]`，参与软排序。

### 4.4 T3：疾病文本匹配

`find_matching_labels(patient_diag, trial_labels)`：

1. 对 patient 与 label 做 `normalize_diagnosis_for_matching`；
2. 子串包含、同义词、按 `/()` 切分后的 token 匹配；
3. **英文 token 至少 2 字符**，避免单字母 `T` 误匹配「T/NK」。

**案例（HAQI）**  
- 诊断：`胃恶性肿瘤 TXNXM1（Ⅳ）（KPS 80分）NRS0`  
- 修复前：token `T` 可命中「T/NK细胞淋巴瘤」  
- 修复后：Top1 标签为「胃癌」

### 4.5 T4：约束满足与缺失处理

对每条试验：

1. **准入**：`disease_match ∧ ¬hard_excluded`（v2 筛查语义）；
2. **hard_excluded**：年龄/性别/ECOG/线数/化验 **已知且违反**，或排除 clause 命中；
3. **unknown**：患者缺该化验或无法解析 ×ULN → **不 hard_excluded**，记入 `needs_review`；
4. **软排序**：疾病 +50，各项 pass +5~10，地理 +2~8，Jaccard×15，缺 core 字段每条 −3。

该设计将 NLP 抽取不确定性传导为 **待核对** 而非 silent error。

---

## 5 实验

### 5.1 实验设置

- 匹配引擎：`MATCHER_VERSION = matcher_layers_v2`
- 模式：**strict**（化验 fail 则 hard_excluded）
- 候选上限：50（实际返回 disease_match 且未 hard_excluded 的前 50）
- 评测脚本：批量 `rank_trials` + `structured_data/stage_report_summary.json`

### 5.2 信息抽取层结果

| 病例 | 结构化化验数 | 缺 P0 | OCR errors | 主要 error 类型 |
|------|-------------|-------|------------|----------------|
| CHQI | 11 | 1 | 0 | — |
| HAQI | 5 | 5 | 1 | timeout |
| MSHU | 5 | 5 | 5 | timeout |
| HZZH | 1 | 8 | 5 | timeout |
| LHBI | 1 | 8 | 6 | timeout |
| LSLI | 0 | 9 | 1 | timeout |
| CHRO | 0 | 9 | 4 | **全部页 timeout** |
| LWPI | 0 | 9 | 6 | timeout / 400 |
| LUFE | 0 | 9 | 2 | timeout |
| TARU | 0 | 9 | 3 | timeout / 403 欠费 |

**观察**：10 例中 9 例存在 OCR errors；化验数 ≤1 的 7 例 **全部** 伴随页级失败。唯一无 error 的 CHQI 化验最完整（11 项）。

### 5.3 端到端匹配结果（strict）

| 病例 | 癌种 | lab | strict 候选 | eligible | needs_review | Top1 标签 |
|------|------|-----|------------|----------|--------------|-----------|
| CHQI | 胰腺癌 | 11 | 7 | 7 | 4 | 胰腺癌 |
| CHRO | 胆管癌 | 0 | 50 | 3 | 47 | 肝内胆管癌 |
| HAQI | 胃癌 | 5 | 2 | 0 | 2 | 胃癌 |
| HZZH | 胰腺癌 | 1 | 15 | 0 | 15 | 胰腺癌 |
| LHBI | 胰腺癌 | 1 | 50 | 4 | 46 | 胰腺癌（实体瘤） |
| LSLI | 胰腺癌 | 0 | 11 | 11 | 10 | 胰腺癌 |
| LWPI | 胃癌 | 0 | 13 | 13 | 12 | 胃癌 |
| LUFE | 脑恶性肿瘤 | 0 | 0 | 0 | 0 | — |
| MSHU | 尿路上皮相关 | 5 | 0 | 0 | 0 | — |
| TARU | 胶质母细胞瘤 | 0 | 0 | 0 | 0 | — |

**汇总**：7/10 有候选；3/10 零候选（LUFE/MSHU/TARU），主因 **疾病标签 lexical 未对齐**，非化验 hard_excluded。

### 5.4 代表性 Case Study

#### Case A — CHQI（IE 较完整）

- IE：11 项 lab_observations，ECOG=1，stage=IV，8 条 biomarkers，地点沈阳
- 匹配：strict 7 候选，Top1 score=103.3，eligible=true，标签「胰腺癌」
- **解读**：输入完整时，文本匹配 + 约束可**显著收窄**搜索空间

#### Case B — HAQI（复杂 diagnosis + IE 修复）

- IE：5 项化验；缺 ECOG；cancer_stage=IV（从 `（Ⅳ）` 规则抽出）；文件名补胃癌/一线
- 匹配：strict 2 候选，Top1「胃癌」，needs_review=true（缺 ECOG、P0 化验）
- **解读**：TNM 噪声规范化解决 **疾病误配**；缺失槽位正确标为待核对而非零候选

#### Case C — CHRO（OCR 漏检）

- **人工核对**：源 PDF 含血常规、肝肾功能等化验
- OCR：4 页均 timeout；仅第 2 页 pathology 文本入库；lab_observations=0
- 匹配：50 候选，47 needs_review
- **解读**：**抽取 recall 失败**导致下游大量 unknown；匹配层行为符合设计，但不能反映真实患者可匹配性

---

## 6 讨论

### 6.1 NLP 层面的主要发现

1. **瓶颈在 IE recall，而非匹配规则**：低结构化病例与 OCR timeout 高度相关。
2. **领域规范化必不可少**：通用 LLM OCR 不会自动处理 TNM 与同义词；轻量规则可修复 high-impact 错误。
3. **lexical 疾病匹配有天花板**：MSHU 长诊断、LUFE「脑恶性肿瘤」vs 试验「胶质瘤」等导致零候选，需 entity linking 或同义词扩展。
4. **缺失信息应显式建模**：unknown vs fail 的区分，等价于 NLP 中的 partial information inference。

### 6.2 错误类型分析

| 错误类型 | 示例 | 层级 |
|----------|------|------|
| OCR 超时 | CHRO 全页 timeout | 文档 IE |
| 化验 item 误映射 | Hb vs MCHC 混淆（已通过 EXCLUDE 规则缓解） | 归一化 |
| TNM 噪声误匹配 | HAQI → 淋巴瘤 | 疾病匹配 |
| 诊断未规范化 | MSHU 零候选 | 疾病匹配 |
| ×ULN 未解析 | 部分试验 clause → unknown | 约束解析 |

### 6.3 与纯神经网络方法的对比

| 维度 | 本项目 | 潜在 neural 方案 |
|------|--------|------------------|
| IE | LLM OCR + 规则 | LayoutLM、UniNER on 医疗表格 |
| 匹配 | 词典 + Jaccard + 规则 | Cross-encoder 排序 |
| 可解释性 | 高（checks、reasons） | 较低 |
| 数据需求 | 10 例即可 demo | 需标注对训练 ranker |

课程项目选择 **可解释、可审计** 的 hybrid 路线合理；neural ranking 留作 future work。

### 6.4 局限

1. 无 gold 标注，无法报告标准 NER/IE 的 P/R/F1；
2. 10 例样本小，癌种与 OCR 质量分布不均；
3. Top 排序未经临床专家系统评估；
4. 向量语义与 ×ULN 全解析未实现。

---

## 7 结论与未来工作

### 7.1 结论

本项目从 NLP 角度实现了中文肿瘤病历的 **文档级信息抽取 → 文本规范化 → lexical 疾病匹配 → 约束排序** 流水线，并在 10 例真实 PDF 上验证：（1）IE 质量决定下游匹配可信度；（2）领域文本规范化可修复关键误匹配；（3）缺失槽位的 unknown 处理适合筛查式应用。实验表明，**OCR 页级失败是当前最大的 NLP/IE 瓶颈**，需在方法章节与产品叙述中明确区分。

### 7.2 未来工作

1. **OCR 稳定性**：超时重试、单页重跑、提高 timeout；对 CHRO 等漏检病例重评测 recall；
2. **诊断规范化**：`diagnosis_raw` + 规范 `cancer_type`；扩展同义词与实体链接；
3. **评测集**：小规模人工标注 IE gold（P0 化验、癌种、ECOG）以计算 F1；
4. **语义匹配**：接入 embedding / Faiss 改善入排长文本排序；
5. **复杂表述解析**：×ULN、biomarker 硬约束从试验文本中稳定抽取。

---

## 参考文献（建议阅读与引用格式）

1. Uzuner Ö., et al. **2011 i2b2/VA challenge on concepts, assertions, and relations in clinical text.** JAMIA, 2011.  
2. Li J., et al. **BioCreative VI CP extraction.** 2017.（生物标志物/文本抽取背景）  
3. Devlin J., et al. **BERT: Pre-training of Deep Bidirectional Transformers.** NAACL, 2019.  
4. Huang K., et al. **ClinicalBERT.** 2019.（临床文本预训练）  
5. Xu Y., et al. **LayoutLM: Pre-training of Text and Layout.** KDD, 2020.（文档 IE）  
6. Savova G.K., et al. **Mayo clinical Text Analysis and Knowledge Extraction System (cTAKES).** JAMIA, 2010.  
7. 刘知远等. **知识图谱与实体链接综述.** 计算机研究与发展.（中文术语规范化背景）

*注：正式提交时请按课程要求统一为 GB/T 7714 或 APA 格式，并补充实际引用的页码。*

---

## 附录 A：患者槽位 Schema（节选）

| 字段 | 类型 | NLP/IE 角色 |
|------|------|-------------|
| diagnosis | string | 原始诊断文本 |
| cancer_type | string | 规范癌种 |
| cancer_stage | string | 规则从 diagnosis 推断 |
| lab_observations | array | 化验 IE + 归一化 |
| biomarkers | string[] | 正则/全文抽取 |
| ecog, treatment_lines | int | 结构化抽取 |

完整定义见 `docs/MATCHING_CHECKLIST.md`。

## 附录 B：12 项化验 metric_id

P0（9）：plt, alt, hb, ast, anc, cr, tbil, inr, aptt  
P1（3）：pt, alb, wbc  

别名表见 `codes/lab_lexicon.py`。

## 附录 C：HAQI 诊断规范化示例

| 阶段 | 文本 / 匹配结果 |
|------|----------------|
| OCR 原始 | `胃恶性肿瘤 TXNXM1（Ⅳ）（KPS 80分）NRS0` |
| 规范化后（概念） | 癌种倾向：胃癌；噪声：TXNXM1、KPS、NRS 已剥离 |
| 修复前误匹配 | 试验标签「T/NK细胞淋巴瘤」 |
| 修复后 Top1 | 「胃癌」；cancer_stage=IV |

## 附录 D：复现实验

```powershell
cd 有救AI
python scripts/normalize_patient_for_matching.py --file "output_patients/CHQI胰腺癌辽宁沈阳_患者信息_fixed.json" --run-match
python -m pytest tests/test_filename_and_disease_match.py tests/test_matcher_v2.py -q
```

工程细节见 `README.md`；产品向阶段数据见 `docs/STAGE_REPORT.md`。

---

**作者声明**：本报告为 NLP 课程期末项目；系统不用于临床决策，所有匹配结果需专业人员核对。
