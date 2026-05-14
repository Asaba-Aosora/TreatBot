"""
化验判定策略配置。
"""

from __future__ import annotations

HIGH_RISK_METRICS: set[str] = {
    # 血象
    "wbc",
    "anc",
    "plt",
    "hb",
    # 肝肾
    "alt",
    "ast",
    "tbil",
    "cr",
    "alb",
    # 凝血
    "inr",
    "aptt",
    "pt",
}

# 对这些指标启用更保守的单位冲突保护。
UNIT_GUARD_METRICS: set[str] = set(HIGH_RISK_METRICS)

# 低于该置信度的候选规则，不进入硬失败，降级为 unknown。
CLAUSE_CONFIDENCE_GATE = 0.75
