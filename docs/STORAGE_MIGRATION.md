# 从 JSON 文件管线迁移到 PostgreSQL（规划）

## 1. 动机

- 版本化试验与解析规则、并发读写、索引与审计。
- 匹配结果与医生反馈需要按患者/时间查询。
- 后续 pgvector 与试验条款向量共库，降低同步复杂度。

## 2. 迁移阶段

### 阶段 A：双写只读验证

- 应用仍从 `trials_structured.json` 读取；每次 `sync_trials` 后异步写入 DB `trials_raw` 表。
- 对比脚本：JSON 解析的 `parsed_conditions` 与 DB 存的一致哈希。

### 阶段 B：读切换

- `load_trials` 改为从 `trials_published` 视图读取；失败时回退 JSON。
- 向量索引构建脚本改为从 DB 导出 chunk。

### 阶段 C：写切换

- 管理端仅通过 API 更新试验；JSON 导出为备份归档。

## 3. 核心表（与 IMPLEMENTATION_SPEC 对齐扩展）

- `trials`：trial_id、名称、labels、入排原文、source_version、published_at。
- `trial_rule_clauses`：trial_id、field(inclusion|exclusion)、metric_id、operator、threshold、relative_to_uln、evidence、parser_version。
- `patients` / `patient_observations`：患者主表 + 化验窄表（lab_observations）。
- `match_runs`：patient_ref、trial_id、score、checks JSONB、matcher_version、created_at。
- `doctor_feedback`：已有设计，增加 match_run_id 外键。

## 4. 索引与性能

- `(trial_id, field)` 上 B-tree；`metric_id` 可选 GIN（若大量 JSON 查询）。
- 全文检索：入排原文 `tsvector`；或继续外向量库。

## 5. 灰度与回滚

- 特性开关 `READ_TRIALS_FROM_DB`。
- 发布前快照：pg_dump schema + trials 子集。
- 回滚：关开关 + 恢复上一快照。

## 6. 与当前仓库脚本的衔接

- 版本快照：[`scripts/sync_trials.py`](d:/Work/有救AI/scripts/sync_trials.py)。
- 解析导出：[`scripts/parse_trials_to_rules.py`](d:/Work/有救AI/scripts/parse_trials_to_rules.py) 的输出可作为 `trial_rule_clauses` 的导入源。
