#!/usr/bin/env python3
"""
AI核心数据结构

定义观察→策略→动作架构中的标准化数据模型
"""
from typing import Dict, Any


class Observation:
    """
    观察结果 - 提取当前状态（不用LLM）

    Attributes:
        phase: 当前阶段 (phase1, phase2, phase3)
        role: AI角色 (PF or PM)
        context: 上下文信息（根据阶段不同而不同）
    """
    def __init__(self, phase: str, role: str, context: Dict[str, Any]):
        self.phase = phase
        self.role = role
        self.context = context

    def to_dict(self) -> Dict:
        return {
            "phase": self.phase,
            "role": self.role,
            "context": self.context
        }


class Strategy:
    """
    策略输出 - Slow Engine的思考结果

    Attributes:
        thinking: 思考过程
        assessment: 情况评估
        recommendation: 策略建议
        next_focus: 下一步关注点
        explanation: 向用户解释决策的简短消息（可选，用于聊天显示）
    """
    def __init__(self, thinking: str, assessment: Dict, recommendation: Dict, next_focus: str = "", explanation: str = ""):
        self.thinking = thinking
        self.assessment = assessment
        self.recommendation = recommendation
        self.next_focus = next_focus
        self.explanation = explanation

    def to_dict(self) -> Dict:
        return {
            "thinking": self.thinking,
            "assessment": self.assessment,
            "recommendation": self.recommendation,
            "next_focus": self.next_focus,
            "explanation": self.explanation
        }


class Action:
    """
    动作输出 - Fast Engine的执行指令

    Attributes:
        action_type: 动作类型
        params: 动作参数
        execute_immediately: 是否立即执行
    """
    def __init__(self, action_type: str, params: Dict[str, Any], execute_immediately: bool = True):
        self.action_type = action_type
        self.params = params
        self.execute_immediately = execute_immediately

    def to_dict(self) -> Dict:
        return {
            "action": self.action_type,
            "params": self.params,
            "execute_immediately": self.execute_immediately
        }
