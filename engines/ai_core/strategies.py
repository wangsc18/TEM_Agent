#!/usr/bin/env python3
"""
策略层 - Slow Engine (System 2)

深度推理引擎，生成策略建议（思考+评估+建议）
"""
import asyncio
from typing import Dict
from .models import Observation, Strategy
from .utils import random_delay, parse_json_response


class StrategyGenerator:
    """策略生成器 - Slow Engine的核心逻辑"""

    def __init__(self, slow_engine, role: str, config: Dict):
        """
        初始化策略生成器

        Args:
            slow_engine: Slow LLM引擎
            role: AI角色 (PF or PM)
            config: 配置参数
        """
        self.slow_engine = slow_engine
        self.role = role
        self.slow_thinking_time = config.get('slow_thinking_time', (3, 6))
        self.strategic_context = {}  # 策略上下文

    async def strategize_pm_verify(self, observation: Observation, pf_decision_data: Dict) -> Strategy:
        """
        PM验证PF决策的策略思考

        Args:
            observation: 当前观察结果
            pf_decision_data: PF的决策数据

        Returns:
            Strategy: 策略建议
        """
        print(f"[SlowEngine] PM验证策略思考...")

        sop_text = "\n".join(pf_decision_data['sop_data']['content'])

        # 提取聊天历史
        chat_history = observation.context.get('chat_history', [])
        chat_context = ""
        if chat_history:
            chat_lines = []
            for msg in chat_history[-5:]:  # 只用最近5条消息
                chat_lines.append(f"{msg['sender']}: {msg['message']}")
            chat_context = "\n".join(chat_lines)

        prompt = f"""你是严谨的PM，需要深入分析PF的决策。

【当前情况】
PF识别的威胁: {pf_decision_data['keyword']}
PF提出的方案: {pf_decision_data['pf_decision']}

【SOP标准】
{pf_decision_data['sop_data']['title']}
{sop_text}

【机组通信记录】
{chat_context if chat_context else "(暂无通信记录)"}

【你的任务】
评估"PF选择的应对方案是否合理"。注意：不是评估"是否应该继续飞行"，而是评估"PF的应对方案本身"。

【分析框架】
1. PF是否识别出了威胁？
2. PF选择的方案是"积极应对"还是"忽视威胁"？
3. 该方案是否符合SOP？
4. 综合机组通信内容进行判断

【判断逻辑】
✅ 应该同意：PF选择"使用XX标准程序"、"执行XX检查单"、"咨询XX" → 说明在积极应对
❌ 应该驳回：PF选择"忽略威胁"、"不采取行动"、违反SOP的操作

返回JSON格式（必须严格遵守格式）：
{{
    "thinking": "你的详细思考过程",
    "assessment": {{
        "threat_recognized": true/false,
        "pf_approach": "积极应对/忽视威胁/不确定",
        "sop_compliance": "符合/不符合/部分符合"
    }},
    "recommendation": {{
        "action": "approve/reject",
        "confidence": "high/medium/low",
        "reasoning": "推荐理由"
    }},
    "next_focus": "下一步关注点",
    "explanation": "向机组成员解释你决策的简短消息（20-50字，口语化，像真正的PM说话）"
}}
"""

        await asyncio.sleep(random_delay(*self.slow_thinking_time))

        try:
            response = await self.slow_engine.chat(prompt, stream=False)
            analysis = parse_json_response(response)

            # 构建 Strategy 对象
            strategy = Strategy(
                thinking=analysis.get('thinking', ''),
                assessment=analysis.get('assessment', {}),
                recommendation=analysis.get('recommendation', {}),
                next_focus=analysis.get('next_focus', ''),
                explanation=analysis.get('explanation', '')
            )

            print(f"[SlowEngine] 策略建议: {strategy.recommendation.get('action', 'N/A')}")
            print(f"[SlowEngine] 思考: {strategy.thinking[:50]}...")
            print(f"[SlowEngine] 解释: {strategy.explanation}")

            # 保存到上下文
            self.strategic_context['pm_verify_strategy'] = strategy.to_dict()

            return strategy

        except Exception as e:
            print(f"[SlowEngine] 错误: {e}")
            # 返回默认策略（同意）
            return Strategy(
                thinking="分析出错，采用默认策略",
                assessment={"error": True},
                recommendation={"action": "approve", "confidence": "low", "reasoning": "默认同意"},
                next_focus="",
                explanation="方案分析完成，同意执行"
            )

    # TODO: 添加更多策略方法
    # - strategize_pf_decision: PF决策策略
    # - strategize_qrh_selection: QRH选择策略
    # - strategize_gauge_monitoring: 仪表监控策略
