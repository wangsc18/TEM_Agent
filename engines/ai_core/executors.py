#!/usr/bin/env python3
"""
执行层 - Fast Engine (System 1)

快速响应引擎，将策略转化为具体动作
"""
from typing import Dict
from .models import Strategy, Action


class ActionExecutor:
    """动作执行器 - Fast Engine的核心逻辑"""

    def __init__(self, fast_engine, role: str, config: Dict):
        """
        初始化动作执行器

        Args:
            fast_engine: Fast LLM引擎
            role: AI角色 (PF or PM)
            config: 配置参数
        """
        self.fast_engine = fast_engine
        self.role = role
        self.fast_response_delay = config.get('fast_response_delay', (1, 3))

    def execute_pm_verify(self, strategy: Strategy) -> Action:
        """
        根据策略生成PM验证的具体动作

        Args:
            strategy: Slow Engine的策略建议

        Returns:
            Action: 具体执行动作
        """
        print(f"[FastEngine] 生成PM验证动作...")

        # 从策略中提取建议
        recommendation = strategy.recommendation
        action_type = recommendation.get('action', 'approve')

        # 转换为布尔值
        approve = (action_type == 'approve')

        # 生成动作
        action = Action(
            action_type='pm_verify_decision',
            params={'approve': approve},
            execute_immediately=True
        )

        print(f"[FastEngine] 动作: {'同意' if approve else '驳回'}")

        return action

    # TODO: 添加更多执行方法
    # - execute_pf_decision: PF决策动作
    # - execute_qrh_selection: QRH选择动作
    # - execute_gauge_monitoring: 仪表监控动作
