# 项目上下文交接文档

> 供新 Cursor 会话快速恢复上下文。最后更新：2026-06-01（本会话：地理/筛查匹配/文件名推断/HAQI）

---

## 1. 项目是什么

**有救AI**：临床试验患者-试验匹配系统。

- **试验库**：496 条招募中项目（来自 Excel sheet1）
- **匹配引擎**：规则硬匹配（年龄/性别/ECOG/线数/化验）+ 弱语义排序（Jaccard）；Faiss 向量库有建库脚本，**未接入** demo_server / run_match 默认入口
- **患者输入**：Web 表单 / OCR JSON（豆包 hybrid）/ normalize 流水线
- **产品定位**：给医生**筛选建议**，缺失字段标「待核对」，医生补全后再收紧；**不是**缺 ECOG 就零候选

---

## 2. 数据流（当前共识）

```
临床试验数据20250908-原始数据.xlsx
  └─ sheet「1.招募中项目」496 条  ──sync──►  trials_structured.json
  └─ sheet「2.研究中心明细」9327 行（=496试验×多中心，不是试验数）

PDF（文件名含癌种/线数/地点等业务元数据）
  └─ OCR（scripts/ocr_demo.py / codes/ocr_cloud.py）
       └─ *_患者信息.json
            └─ （可选）scripts/fix_lab_result.py → *_fixed.json
                 └─ scripts/normalize_patient_for_matching.py → *_matching.json
                      └─ rank_trials / demo_server / benchmark
```

**不要用**：`structured_data/临床试验_入组条件_结构化结果.xlsx`（离线分析用，匹配引擎不读）

**金标准工作文件**：`*_matching.json`（不是 `fixed.json`）

---

## 3. 历史 + 本会话已完成事项

### 3.1 试验库与清单（此前已完成）

- 试验库 496 条：`scripts/sync_xlsx_to_trials_json.py` → `trials_structured.json`
- 化验频率：`scripts/summarize_trial_lab_metrics.py` → `structured_data/trial_parsed/lab_metric_frequency.*`
- 匹配清单：`docs/MATCHING_CHECKLIST.md` + `structured_data/matching_checklist.json`
- 患者整理：`codes/patient_matching_normalize.py` + `scripts/normalize_patient_for_matching.py`

### 3.2 地理距离（本会话）✅

- **新模块** `codes/geo_admin.py`：`cpca` + 民政部 adcode 坐标，替代手工 `LOCATION_COORDS`
- 患者 `location` / `location_adcode` / `location_source`；试验多中心按 index 配对算最短距离
- **依赖**：`cpca>=0.5.5`（已写入 `requirements.txt`）
- **测试**：`tests/test_geo_admin.py`（8 passed）
- **CHQI 样例**：`location=辽宁省沈阳市`, `adcode=210100`；同城距离 ≈ 0 km（不再是 ~66 km）

### 3.3 筛查式匹配语义（本会话）✅ — `MATCHER_VERSION = matcher_layers_v2`

**产品原则**：缺 ECOG/线数等 → 报「ECOG缺失」等，**仍给候选**，等医生补数据。

| 字段 | 含义 |
|------|------|
| `hard_excluded` | 已知违反入排（年龄/ECOG 超标、化验 fail、排除触发）→ **不进候选列表** |
| `needs_review` | 核心字段缺失或化验 unknown → **进列表，标待核对** |
| `eligible` | **可确认入选**（规则全过 + 无缺失 core） |

`rank_trials` 过滤条件：`disease_match ∧ ¬hard_excluded`（**不再**因缺 ECOG 把试验踢出列表）

- HTML：`scripts/run_match.py` 显示「⚠ 建议候选（待医生核对）」
- 文档：`docs/MATCHING_CHECKLIST.md` 2.3 节已更新

### 3.4 疾病匹配修复（本会话）✅

**问题（HAQI）**：诊断 `胃恶性肿瘤 TXNXM1…` 误匹配 **T/NK细胞淋巴瘤**（`TXNXM1` 里的字母 `T` 命中标签 `T/NK`）；且「胃恶性肿瘤」对不上试验标签「胃癌」。

**修复**（`codes/trial_matcher.py` + `codes/patient_filename_infer.py`）：

- 去掉 TNM/KPS/NRS 噪声；同义词 `胃恶性肿瘤` → `胃癌`
- 英文 token **至少 2 字符**（单字母 `T` 不参与匹配）
- `build_patient_disease_text(patient)`：合并 `cancer_type` + `diagnosis` 再匹配

### 3.5 文件名元数据推断（本会话）✅

- **新模块** `codes/patient_filename_infer.py`
- 命名约定：`{内部码}{癌种}{可选:省/市}{可选:一线/二线…}.pdf`
  - `CHQI胰腺癌辽宁沈阳.pdf` → 癌种 + 地点
  - `HAQI胃癌一线进展.pdf` → 癌种 + `treatment_lines=1`
- normalize 时 **只补缺失字段**，写入 `*_source: "filename"` 和 `_matching_normalize_report.filename_inferred`
- **测试**：`tests/test_filename_and_disease_match.py`

### 3.6 金标准样例

| 文件 | 说明 |
|------|------|
| `output_patients/CHQI胰腺癌辽宁沈阳_患者信息_matching.json` | 胰腺癌；11/12 P0（缺 plt）；strict ~7 条；location 已规范 |
| `output_patients/HAQI胃癌一线进展_患者信息_fixed_matching.json` | 第二份样例；OCR 脏数据多；文件名补 `cancer_type=胃癌`, `treatment_lines=1`；修复后 Top 为**胃癌试验**（非淋巴瘤） |

---

## 4. 匹配逻辑速查（第 1 层，v2）

| 类型 | 内容 |
|------|------|
| **进候选列表** | `disease_match` 且 **非** `hard_excluded` |
| **硬规则（已知值）** | 年龄/性别/ECOG/线数/化验 fail、排除触发 → 硬拒 |
| **缺失 core** | 不硬拒；`needs_review` + `missing_core_messages`（如「ECOG缺失」） |
| **strict** | 化验须全过；balanced 允许入组化验 fail ≤ 1 |
| **可确认入选 `eligible`** | 硬规则全过 + 无缺失 core + 化验门槛过 |
| **软排序** | 地理距离、Jaccard；缺 core 每条扣 3 分 |

**12 项化验 metric_id**：wbc, anc, plt, hb, tbil, alt, ast, cr, alb, inr, aptt, pt  
**P0（9 项）**：plt, alt, hb, ast, anc, cr, tbil, inr, aptt

---

## 5. 关键路径

| 用途 | 路径 |
|------|------|
| 试验库 | `original_data/clinical_trials/trials_structured.json` |
| 匹配清单 | `docs/MATCHING_CHECKLIST.md` |
| 核心匹配 | `codes/trial_matcher.py` |
| 地理 | `codes/geo_admin.py` |
| 文件名推断 | `codes/patient_filename_infer.py` |
| 患者 normalize | `codes/patient_matching_normalize.py` |
| 患者整理 CLI | `scripts/normalize_patient_for_matching.py` |
| OCR 清洗 | `scripts/fix_lab_result.py` |
| OCR 入口 | `scripts/ocr_demo.py` |
| Web 演示 | `scripts/demo_server.py` |
| 离线 HTML 报告 | `scripts/run_match.py` |
| 化验规则 | `codes/lab_rules.py`, `codes/lab_lexicon.py` |

---

## 6. 常用命令

```powershell
pip install cpca pandas   # 地理 + 文件名地点解析

# OCR → 整理 → 匹配
python scripts/ocr_demo.py
python scripts/fix_lab_result.py input.json output_fixed.json   # 可选
python scripts/normalize_patient_for_matching.py --file "output_patients/xxx_fixed.json" --run-match

# 测试
python -m pytest tests/test_geo_admin.py tests/test_filename_and_disease_match.py tests/test_matcher_v2.py -q

# 离线匹配 HTML
python scripts/run_match.py

# Web
python scripts/demo_server.py
```

---

## 7. 建议的下一步（优先级）

1. **HAQI 人工补全**：ECOG（KPS 80≈1 需医生确认）、OCR 缺的 P0 化验（alt/ast/cr/tbil/aptt）；第 14 页 OCR 超时可能缺肝功
2. **批量 OCR + normalize**：其余 PDF 走同一流水线；文件名尽量含 `{癌种}{线数}{地点}`
3. **CHQI 医生复核**：7 条 strict 候选；plt 缺失是否接受
4. **诊断规范化**：OCR `diagnosis` 仍带 TNM 长串时可考虑写入 `diagnosis_raw`，匹配用 `cancer_type`
5. **（可选）** 接 Faiss：`rank_trials_with_vector`
6. **（后期）** 治疗史/排除语义、×ULN、疾病匹配进一步收紧（实体瘤 vs 血液瘤）

---

## 8. 已知问题 / 注意点

- **demo_server** 仍用 `rank_trials`，未融合 Faiss
- **OCR 质量**：大量脏行 → `fix_lab_result.py` + normalize；非化验进 `_ocr_meta_unsorted`
- **「一线进展」歧义**：文件名「一线」→ `treatment_lines=1` 是提示，可能与 OCR 病史（如已 3 周期化疗）冲突，看 `filename_conflicts`
- **HAQI strict 候选少（~2 条）**：疾病匹配已有 ~20 条胃癌，其余因化验/排除等 `hard_excluded`，非零候选问题
- **git**：用户规则勿主动 commit；本会话新增/修改多文件未提交

---

## 9. 对话中澄清过的误解

| 误解 | 事实 |
|------|------|
| 试验上万条 | 9327 是研究中心明细行数；试验 **496** 条 |
| 缺 ECOG → 候选为 0 | **旧 strict 行为**；v2 已改为缺失只 `needs_review`，除非已知违反 |
| 胃恶性肿瘤应匹配胃癌 | 需 `cancer_type=胃癌` 或同义词规范化；否则旧逻辑会对不上 |
| TXNXM1 导致淋巴瘤 | 单字母 `T` 误匹配 `T/NK`；已修 |
| 文件名只是备注 | 可推断 **癌种/线数/地点**，已接入 normalize |
| 地理位置改好了吗 | 是；跑 `pytest tests/test_geo_admin.py` 验证 |

---

## 10. 给新会话的一句话

> 试验库 496 条；匹配引擎 **v2 筛查模式**（缺 ECOG 仍给候选）；地理用 **cpca/adcode**；文件名推断 **癌种/线数/地点**（`patient_filename_infer.py`）；疾病匹配已修 TNM/同义词误报。CHQI=胰腺癌金标准，HAQI=胃癌第二样例（`output_patients/HAQI胃癌一线进展_患者信息_fixed_matching.json`）。下一步：批量 OCR+normalize，人工补 HAQI 的 ECOG 与 P0 化验。
