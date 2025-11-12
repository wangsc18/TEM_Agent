#!/usr/bin/env python3
"""
双模型管理器 - 前端小模型 + 后端大模型协同架构
"""
import json
import re
from openai import AsyncOpenAI


class StrategyOptimizer:
    """策略优化器 - 大模型分析对话历史并优化小模型策略"""

    def __init__(self, client: AsyncOpenAI, big_model: str = "gpt-4o"):
        self.client = client
        self.big_model = big_model

    async def analyze_and_optimize(
        self,
        user_question: str,
        conversation_history: list,
        background_data: dict,
        personal_memo: str = ""
    ) -> dict:
        """
        大模型深度分析并返回优化建议

        Returns:
            {
                "answer": "问题的答案",
                "strategy_update": "小模型策略调整建议",
                "user_style": "用户交互风格分析"
            }
        """
        try:
            print(f"[策略优化器] 开始分析问题: {user_question}")

            # 构建完整上下文
            context = self._build_context(conversation_history, background_data, personal_memo)
            print(f"[策略优化器] 上下文长度: {len(context)} 字符")

            # 大模型分析prompt
            analysis_prompt = f"""你是一位资深的TEM（威胁与差错管理）教官和对话策略分析专家。

【当前任务】
1. 回答用户的问题："{user_question}"
2. 分析用户的交互风格和偏好
3. 为前端AI伙伴（小模型）提供策略优化建议

【完整背景信息】
{context}

【输出格式】
请严格按照以下JSON格式输出（纯JSON，不要markdown代码块）：
{{
    "answer": "对用户问题的详细回答（口语化、简洁、分成多个短句）",
    "user_style": "用户交互风格分析（例如：偏好简洁/详细、技术导向/流程导向等）",
    "strategy_update": "建议小模型如何调整对话策略（例如：更多使用专业术语、增加确认步骤等）"
}}"""

            # 调用大模型
            print(f"[策略优化器] 正在调用大模型 {self.big_model}...")
            response = await self.client.chat.completions.create(
                model=self.big_model,
                messages=[{"role": "user", "content": analysis_prompt}],
                temperature=0.7,
                max_tokens=1000
            )
            print(f"[策略优化器] 大模型调用成功")

            result_text = response.choices[0].message.content.strip()
            print(f"[策略优化器] 大模型返回内容长度: {len(result_text)} 字符")

            # 尝试解析JSON
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                # 如果不是纯JSON，尝试提取
                json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    # 降级处理
                    result = {
                        "answer": result_text,
                        "user_style": "未能分析",
                        "strategy_update": "保持当前策略"
                    }

            return result

        except Exception as e:
            import traceback
            print(f"[策略优化器] 错误: {e}")
            print(f"[策略优化器] 详细错误:\n{traceback.format_exc()}")
            return {
                "answer": "抱歉，我在处理这个问题时遇到了困难。",
                "user_style": "未知",
                "strategy_update": "保持当前策略"
            }

    def _build_context(self, conversation_history: list, background_data: dict, personal_memo: str) -> str:
        """构建完整上下文"""
        context_parts = []

        # 1. 背景信息
        context_parts.append("=== 飞行背景信息 ===")
        for key, value in background_data.items():
            context_parts.append(f"\n【{key}】\n{value}")

        # 2. 用户个人威胁备忘录
        if personal_memo.strip():
            context_parts.append(f"\n=== 用户个人威胁总结 ===\n{personal_memo}")

        # 3. 对话历史（最近10轮）
        context_parts.append("\n=== 对话历史 ===")
        recent_history = conversation_history[-20:]  # 最近10轮（每轮2条消息）
        for msg in recent_history:
            if msg["role"] == "user":
                context_parts.append(f"用户: {msg['content']}")
            elif msg["role"] == "assistant":
                context_parts.append(f"AI伙伴: {msg['content']}")

        return "\n".join(context_parts)


class DualModelManager:
    """双模型管理器 - 协调小模型和大模型"""

    def __init__(
        self,
        client: AsyncOpenAI,
        small_model: str = "gpt-4o-mini",
        big_model: str = "gpt-4o",
        callback_on_big_model_triggered=None
    ):
        self.client = client
        self.small_model = small_model
        self.big_model = big_model
        self.strategy_optimizer = StrategyOptimizer(client, big_model)
        self.callback_on_big_model_triggered = callback_on_big_model_triggered

        # 动态策略（会被大模型更新）
        self.current_strategy = ""

        # 触发词：当小模型回复中包含这些词时，触发大模型
        self.trigger_phrases = [
            "让我查找一下",
            "我需要确认",
            "让我查查",
            "我查一下",
            "稍等",
            "我不太确定"
        ]

    def check_if_trigger_big_model(self, small_model_response: str) -> bool:
        """检测是否需要触发大模型"""
        for phrase in self.trigger_phrases:
            if phrase in small_model_response:
                return True
        return False

    async def process_with_big_model(
        self,
        user_question: str,
        conversation_history: list,
        background_data: dict,
        personal_memo: str = ""
    ) -> dict:
        """
        使用大模型处理复杂问题

        Returns:
            {
                "answer": str,
                "strategy_update": str,
                "user_style": str
            }
        """
        if self.callback_on_big_model_triggered:
            self.callback_on_big_model_triggered()

        result = await self.strategy_optimizer.analyze_and_optimize(
            user_question,
            conversation_history,
            background_data,
            personal_memo
        )

        # 更新策略
        if result["strategy_update"] != "保持当前策略":
            self.current_strategy = result["strategy_update"]
            print(f"[双模型管理器] 策略已更新: {self.current_strategy}")

        return result

    def get_enhanced_system_prompt(self, base_prompt: str) -> str:
        """
        获取增强的system prompt（融合大模型的策略建议）
        """
        if not self.current_strategy:
            return base_prompt

        enhanced = base_prompt + f"""

【策略调整】（基于对话分析）
{self.current_strategy}

【重要】
- 如果遇到你不确定的专业问题（如具体的航空法规、性能计算、复杂的威胁分析），先回复"让我查找一下相关信息"，系统会自动调用专家知识库。
- 不要编造不确定的专业知识。"""

        return enhanced
