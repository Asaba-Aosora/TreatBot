# 有救AI 实施文档（按计划落地）

## 1. 任务清单（按周）

### Week 1：基线固化 + OCR入口稳定
- 修复并替换 `scripts/ocr_demo.py` 为可运行版本。
- 增加统一结构化Schema：`codes/schemas.py`。
- 统一 OCR 输出中的 `issues` 字段，支持错误分级。
- 打通 API 化基础入口：`api/server.py`。

### Week 2-3：OCR生产化
- 默认主通道豆包，Kimi/阿里云降级通道保留。
- 增加页面级重试与退避重试。
- 增加关键字段缺失/异常校验（年龄、ECOG、诊断、化验项）。
- 输出错误分类用于后续观测与人工回补。

### Week 4-5：匹配引擎V2（规则+RAG风格）
- 新增化验阈值解析与硬约束匹配。
- 增加轻量语义相似分，作为软排序特征。
- 新增试验条款切片和向量索引构建脚本：`scripts/build_trial_index.py`。

### Week 6：产品与数据闭环
- 增加医生反馈接口 `POST /v1/feedback`。
- 增加数据版本化同步脚本 `scripts/sync_trials.py`。
- 输出安全、可观测、灰度、评估指标方案。

## 2. 数据库表结构草案

建议主库使用 PostgreSQL（后续可加 pgvector）：

```sql
CREATE TABLE patients (
  id UUID PRIMARY KEY,
  name TEXT,
  age INT,
  gender TEXT,
  diagnosis TEXT NOT NULL,
  cancer_stage TEXT,
  ecog INT,
  treatment_lines INT,
  location TEXT,
  biomarkers JSONB DEFAULT '[]'::jsonb,
  lab_results JSONB DEFAULT '[]'::jsonb,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE trials (
  trial_id TEXT PRIMARY KEY,
  trial_name TEXT,
  labels JSONB,
  inclusion_text TEXT,
  exclusion_text TEXT,
  parsed_conditions JSONB,
  source_version TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE match_results (
  id UUID PRIMARY KEY,
  patient_id UUID NOT NULL,
  trial_id TEXT NOT NULL,
  score NUMERIC NOT NULL,
  semantic_score NUMERIC,
  hard_pass BOOLEAN NOT NULL,
  reasons JSONB DEFAULT '[]'::jsonb,
  snapshot JSONB NOT NULL,
  algorithm_version TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE doctor_feedback (
  id UUID PRIMARY KEY,
  patient_id UUID NOT NULL,
  trial_id TEXT NOT NULL,
  doctor_id TEXT,
  accepted BOOLEAN NOT NULL,
  reason TEXT,
  context JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE trial_sync_versions (
  id UUID PRIMARY KEY,
  version TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  trial_count INT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

## 3. API清单草案

当前已落地（FastAPI骨架）：
- `GET /health`：健康检查。
- `POST /v1/ocr/process`：PDF OCR结构化处理。
- `POST /v1/match`：患者信息匹配试验（支持化验指标输入）。
- `POST /v1/feedback`：医生反馈回流。

后续扩展建议：
- `POST /v1/trials/sync`：触发试验数据同步。
- `GET /v1/trials/versions`：版本列表。
- `POST /v1/trials/publish/{version}`：草稿发布。
- `GET /v1/matches/{patient_id}`：历史匹配查询。

## 4. 安全与合规最小基线

- 传输：全部HTTPS。
- 存储：敏感字段加密（手机号、证件号等，如后续引入）。
- 权限：医生/患者/运营三角色RBAC。
- 审计：所有匹配查询与反馈写审计日志。
- 脱敏：日志默认不落全量病历原文。

## 5. 可观测性指标

- OCR：成功率、超时率、字段缺失率、平均处理时延。
- 匹配：Top-N覆盖率、硬约束拒绝率、医生采纳率。
- 数据：同步成功率、脏数据回滚次数、版本发布频率。
- 服务：接口成功率、P95/P99延迟、错误分布。

## 6. 化验驱动数据契约（JSON 摘要）

### 6.1 患者：`lab_observations[]`

由 `lab_results` 清洗得到，字段与 [`codes/schemas.py`](d:/Work/有救AI/codes/schemas.py) 中 `LabObservation` 对齐：

```json
{
  "metric_id": "wbc",
  "value_num": 4.5,
  "unit_norm": "10^9/L",
  "comparator": null,
  "confidence": 0.85,
  "raw": {"item": "白细胞", "value": "4.5", "unit": "10^9/L", "range": "4.0-10.0"}
}
```

- `metric_id`：稳定 slug，词典见 [`codes/lab_lexicon.py`](d:/Work/有救AI/codes/lab_lexicon.py)。
- `confidence`：清洗置信度，便于后续阈值与人工兜底。

### 6.2 试验：`parsed_conditions` 扩展字段

`load_trials` 后为每条试验写入（由 [`codes/trial_parse.py`](d:/Work/有救AI/codes/trial_parse.py) 补充）：

| 字段 | 含义 |
|------|------|
| `inclusion_lab_clauses` | 入组文本解析出的数值比较条款列表 |
| `exclusion_lab_clauses` | 排除文本解析出的数值比较条款列表 |
| `inclusion_chunks` / `exclusion_chunks` | 条款切片，供 RAG / 人工抽检 |
| `parser_version` | 解析器版本，便于追溯 |

单条 clause 示例：

```json
{
  "metric_id": "plt",
  "operator": ">=",
  "threshold": 100.0,
  "relative_to_uln": false,
  "field": "inclusion",
  "severity": "must",
  "evidence": "血小板计数≥100×10^9/L"
}
```

### 6.3 匹配输出：`checks[]` 与 `next_steps[]`

[`codes/trial_matcher.py`](d:/Work/有救AI/codes/trial_matcher.py) 中每条匹配结果包含：

- `checks`：`{metric_id, field, status: pass|fail|unknown, message, evidence, ...}`
- `next_steps`：缺失或需 ULN 等指标时的补检建议（**缺项不硬拒绝**，仅降权）。
- `eligible`：`disease_match` 且未触发排除且化验入组未明确违反时为 `true`。
- `matcher_version`：匹配引擎版本号。

### 6.4 版本与追溯

- 试验原始 JSON：继续用 [`scripts/sync_trials.py`](d:/Work/有救AI/scripts/sync_trials.py) 做时间版本。
- 解析产物：由 [`scripts/parse_trials_to_rules.py`](d:/Work/有救AI/scripts/parse_trials_to_rules.py) 导出 `structured_data/trial_parsed/`，与 `parser_version` 对齐。
