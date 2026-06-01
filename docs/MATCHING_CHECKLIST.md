# 匹配规则与核心化验清单（第 1 层）

> 本文档汇总当前版本**已落地**的硬性匹配规则与 12 项结构化化验指标，供 OCR 抽取、患者 JSON 校对、匹配评测共用。  
> 代码实现：`codes/trial_matcher.py`（`MATCHER_VERSION = matcher_layers_v1`）、`codes/lab_rules.py`、`codes/lab_lexicon.py`  
> 试验库：`original_data/clinical_trials/trials_structured.json`（496 条）  
> 化验频率统计：`structured_data/trial_parsed/lab_metric_frequency.json`（2026-06-01）

---

## 一、患者侧必备字段（匹配输入）

| 字段 | 类型 | 硬性作用 | OCR/表单优先级 |
| --- | --- | --- | --- |
| `diagnosis` / `cancer_type` | 字符串 | **准入门槛**：须与试验 `疾病三级标签` 匹配，否则不进入候选 | P0 |
| `age` | 整数 | 与试验入组年龄比较；试验有要求但缺失时 strict 模式不可 eligible | P0 |
| `gender` | 字符串 | 与试验性别要求比较（「不限」则跳过） | P0 |
| `ecog` | 整数 | 与试验 ECOG 范围比较 | P0 |
| `treatment_lines` | 整数 | 与试验最低治疗线数比较 | P0 |
| `location` | 字符串 | 不挡候选；影响地理距离加分与排序 | P1 |
| `cancer_stage` | 字符串 | 不参与硬过滤；参与弱语义排序 | P1 |
| `biomarkers` | 字符串列表 | 不参与硬过滤；参与弱语义排序 | P1 |
| `lab_results` → `lab_observations` | 数组 | 见下文 12 项化验 | P0（按频率） |

---

## 二、硬性匹配规则（当前已实现）

### 2.1 候选准入（`rank_trials` 过滤）

试验进入候选列表须同时满足：

1. **疾病匹配** `disease_match = true`  
   - 患者 `diagnosis` 与试验 `疾病三级标签` 做子串/关键词交集（偏宽召回）。
2. **eligible = true**（见 2.2，随 `match_mode` 不同）。

### 2.2 单试验硬规则（`match_trial`）

从试验「入组条件」原文正则抽取（`parse_trial_condition`）：

| 规则 | 抽取来源 | 判定逻辑 | 患者缺失时 |
| --- | --- | --- | --- |
| 年龄 | 入组条件 | `age_min` ≤ age ≤ `age_max` | strict：试验有年龄要求且患者无 age → **不可 eligible** |
| 性别 | 入组条件 | 男/女/不限 | strict：试验限定性别且患者无 gender → **不可 eligible** |
| ECOG | 入组条件 | `ecog_min` ~ `ecog_max` | strict：试验有 ECOG 要求且患者无 ecog → **不可 eligible** |
| 治疗线数 | 入组条件 | treatment_lines ≥ `treatment_lines_min` | strict：试验有线数要求且患者无 treatment_lines → **不可 eligible** |
| 化验数值 | 入组/排除解析条款 | 见第三节 | 缺数据多为 **unknown**（不硬失败）；明确违反为 **fail** |

**hard_rule_pass** = 年龄 ∧ 性别 ∧ ECOG ∧ 线数 ∧ 化验 ∧ 未触发排除化验。

### 2.3 匹配模式

| 模式 | eligible 条件 |
| --- | --- |
| **strict**（默认） | 疾病匹配 ∧ hard_rule_pass ∧ 核心字段无缺失（年龄/性别/ECOG/线数，当试验有要求时） |
| **balanced** | 疾病匹配 ∧ 未触发排除 ∧（化验全过 **或** 入组化验 fail ≤ 1 条） |

### 2.4 化验判定细则（`lab_rules.evaluate_lab_rule_clauses`）

| 状态 | 含义 | 对 hard_rule_pass / eligible 的影响 |
| --- | --- | --- |
| **pass** | 患者数值满足试验阈值 | 通过 |
| **fail** | 患者数值明确违反 | 入组 fail → 化验不通过；排除 fail → exclusion_triggered |
| **unknown** | 患者缺该项或无法归一化 | **不视为硬失败**；扣排序分；写入 `next_steps` / `review_items` |

×ULN、肌酐清除率等复杂表述：部分进入 `structured_data/trial_parsed/needs_review.jsonl`，解析不全时按 unknown 处理。

### 2.5 软排序（不过滤候选）

| 因素 | 权重思路 |
| --- | --- |
| 疾病匹配 | +50 |
| 年龄/ECOG/线数/性别/化验通过 | 各 +5~10 |
| 地理距离 | +2~8 |
| 入排全文 Jaccard 语义 | ×15 |

向量/Faiss 语义匹配尚未接入默认入口（`rank_trials_with_vector` 待接）。

---

## 三、12 项结构化化验指标

规范 ID 与别名见 `codes/lab_lexicon.py`。患者 OCR 应优先归一化到 `lab_observations[].metric_id`。

### 3.1 优先级分层（按 496 试验提及频率）

**P0 — 患者 OCR 必抽（Top 9，提及率 ≥ 50%）**

| 排名 | metric_id | 中文名 | 试验合计提及 | 提及率 | 别名示例 |
| ---: | --- | --- | ---: | ---: | --- |
| 1 | `plt` | 血小板 | 375 | 75.6% | 血小板计数、血小板 |
| 2 | `alt` | 丙氨酸氨基转移酶 | 364 | 73.4% | ALT、谷丙转氨酶 |
| 3 | `hb` | 血红蛋白 | 359 | 72.4% | 血红蛋白、HGB |
| 4 | `ast` | 天门冬氨酸氨基转移酶 | 358 | 72.2% | AST、谷草转氨酶 |
| 5 | `anc` | 中性粒细胞 | 356 | 71.8% | ANC、中性粒细胞绝对值 |
| 6 | `cr` | 肌酐 | 351 | 70.8% | 肌酐、血肌酐 |
| 7 | `tbil` | 总胆红素 | 349 | 70.4% | 总胆红素、TBil |
| 8 | `inr` | INR | 278 | 56.0% | 国际标准化比值 |
| 9 | `aptt` | APTT | 251 | 50.6% | 活化部分凝血活酶时间 |

**P1 — 建议抽取**

| 排名 | metric_id | 中文名 | 试验合计提及 | 提及率 |
| ---: | --- | --- | ---: | ---: |
| 10 | `pt` | 凝血酶原时间 | 184 | 37.1% |
| 11 | `alb` | 白蛋白 | 111 | 22.4% |
| 12 | `wbc` | 白细胞 | 73 | 14.7% |

> 说明：许多试验写 ANC/PLT/Hb 而不单独写 WBC；有 ANC 时可不把 WBC 缺失当作最高优先级。

### 3.2 完整别名表

| metric_id | 别名（匹配/OCR 归一化用） |
| --- | --- |
| `wbc` | 白细胞、wbc、white blood cell、白血球 |
| `anc` | 中性粒细胞、anc、neutrophil、中性粒细胞绝对值 |
| `plt` | 血小板计数、血小板、plt、platelet |
| `hb` | 血红蛋白、hb、hemoglobin、hgb、血红蛋白浓度 |
| `tbil` | 总胆红素、tbil、bilirubin、血清总胆红素 |
| `alt` | alt、谷丙转氨酶、丙氨酸氨基转移酶 |
| `ast` | ast、谷草转氨酶、天门冬氨酸氨基转移酶 |
| `cr` | 肌酐、creatinine、cr、血肌酐、scr |
| `alb` | 白蛋白、alb、albumin |
| `inr` | inr、国际标准化比值、凝血酶原时间国际标准化比值 |
| `aptt` | aptt、活化部分凝血活酶时间 |
| `pt` | pt、凝血酶原时间 |

### 3.3 高风险指标（复核队列优先）

以下与 `codes/lab_policy.HIGH_RISK_METRICS` 一致：fail/unknown 时 `review_items` 优先级更高（p0/p1）。

`wbc`, `anc`, `plt`, `hb`, `alt`, `ast`, `tbil`, `cr`, `alb`, `inr`, `aptt`, `pt`（即全部 12 项）

---

## 四、第 1 层范围外（暂不自动硬判）

以下仍保留在试验入排**原文**中，供人工阅读与后续语义层使用，**当前不做可靠自动 pass/fail**：

- 具体既往治疗方案（铂类、PD-1、ADC 等是否失败）
- 转移部位细项（脑转移、腹水、门脉癌栓等）
- 基因/标志物复杂逻辑（除 `biomarkers` 弱语义外）
- 研究者判断、例外条款、「除…外」类叙述
- 肌酐清除率、×ULN 等未稳定解析的化验表述

---

## 五、相关脚本与文件

| 用途 | 路径 |
| --- | --- |
| 试验库 | `original_data/clinical_trials/trials_structured.json` |
| Excel → JSON 同步 | `scripts/sync_xlsx_to_trials_json.py` |
| 化验频率统计 | `scripts/summarize_trial_lab_metrics.py` |
| 离线匹配 | `scripts/run_match.py` |
| OCR 患者压测 | `scripts/benchmark_match_from_ocr_json.py` |
| 回归 fixture | `structured_data/eval/fixture_patient.json` |

---

## 六、患者 JSON 校对勾选项（可复制使用）

**核心字段**

- [ ] `diagnosis`
- [ ] `cancer_stage`（或已从 diagnosis 拆分）
- [ ] `age` / `gender` / `ecog` / `treatment_lines`
- [ ] `location`
- [ ] `biomarkers`（KRAS、MSI、PD-L1 等，与基因报告一致）

**化验 P0（9 项）**

- [ ] `plt` / `anc` / `hb`
- [ ] `alt` / `ast` / `tbil` / `cr`
- [ ] `inr` / `aptt`

**化验 P1（3 项，有则填）**

- [ ] `pt` / `alb` / `wbc`

**质量**

- [ ] 已运行 `attach_lab_observations`，`lab_observations` 含上述 metric_id
- [ ] 心电图、超声、 narrative 噪声未混入 `lab_results`
