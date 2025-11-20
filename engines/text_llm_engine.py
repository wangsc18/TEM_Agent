#!/usr/bin/env python3
"""
传统文本 LLM 引擎 - 大模型专用
使用自定义 API 端点（如 yunwu 平台），返回文本响应
"""
import os
from typing import Optional, List, Dict
from openai import AsyncOpenAI


class TextLLMEngine:
    """传统文本 LLM 引擎（大模型）"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "gpt-4o",
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        callback_on_response_start=None,
        callback_on_text_delta=None,
        callback_on_response_done=None,
        callback_on_error=None
    ):
        """
        初始化文本 LLM 引擎

        Args:
            api_key: OpenAI API 密钥
            base_url: 自定义 API Base URL（如 yunwu 平台）
            model: 模型名称
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大 token 数
            callback_on_response_start: 响应开始回调
            callback_on_text_delta: 文本增量回调 (delta_text)
            callback_on_response_done: 响应完成回调 (full_text)
            callback_on_error: 错误回调 (error_message)
        """
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.max_tokens = max_tokens

        # 处理 base_url
        if not base_url.startswith("http"):
            base_url = f"https://{base_url}"
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"

        self.base_url = base_url

        # 回调函数
        self.callback_on_response_start = callback_on_response_start
        self.callback_on_text_delta = callback_on_text_delta
        self.callback_on_response_done = callback_on_response_done
        self.callback_on_error = callback_on_error

        # 创建 OpenAI 客户端
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )

        print(f"[TextLLM] 初始化成功")
        print(f"[TextLLM] Base URL: {base_url}")
        print(f"[TextLLM] 模型: {model}")
        print(f"[TextLLM] Temperature: {temperature}")
        print(f"[TextLLM] Max Tokens: {max_tokens}")

    def update_system_prompt(self, new_prompt: str):
        """更新系统提示词"""
        self.system_prompt = new_prompt
        print(f"[TextLLM] System Prompt 已更新: {new_prompt[:100]}...")

    async def chat(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        stream: bool = True
    ) -> str:
        """
        发送消息并接收文本响应

        Args:
            user_message: 用户消息
            conversation_history: 对话历史 [{"role": "user/assistant", "content": "..."}]
            stream: 是否流式输出

        Returns:
            完整的 AI 回复文本
        """
        try:
            # 构建消息列表
            messages = []

            # 添加 system prompt
            if self.system_prompt:
                messages.append({
                    "role": "system",
                    "content": self.system_prompt
                })

            # 添加历史对话
            if conversation_history:
                messages.extend(conversation_history)

            # 添加当前用户消息
            messages.append({
                "role": "user",
                "content": user_message
            })

            print(f"[TextLLM] 发送消息: {user_message[:50]}...")
            print(f"[TextLLM] 消息总数: {len(messages)} 条")

            # 调用 API
            if stream:
                return await self._chat_streaming(messages)
            else:
                return await self._chat_non_streaming(messages)

        except Exception as e:
            error_msg = f"TextLLM 错误: {str(e)}"
            print(f"[TextLLM] {error_msg}")

            # 回调：错误
            if self.callback_on_error:
                self.callback_on_error(error_msg)

            import traceback
            traceback.print_exc()
            return ""

    async def _chat_streaming(self, messages: List[Dict[str, str]]) -> str:
        """流式对话"""
        full_response = ""
        first_chunk = True

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                full_response += delta

                if first_chunk:
                    first_chunk = False
                    # 回调：响应开始
                    if self.callback_on_response_start:
                        self.callback_on_response_start()

                # 回调：文本增量
                if self.callback_on_text_delta:
                    self.callback_on_text_delta(delta)

        print(f"[TextLLM] 响应完成: {len(full_response)} 字符")

        # 回调：响应完成
        if self.callback_on_response_done:
            self.callback_on_response_done(full_response)

        return full_response

    async def _chat_non_streaming(self, messages: List[Dict[str, str]]) -> str:
        """非流式对话"""
        # 回调：响应开始
        if self.callback_on_response_start:
            self.callback_on_response_start()

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=False,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )

        full_response = response.choices[0].message.content

        print(f"[TextLLM] 响应完成: {len(full_response)} 字符")

        # 回调：响应完成
        if self.callback_on_response_done:
            self.callback_on_response_done(full_response)

        return full_response

    async def analyze_with_context(
        self,
        user_question: str,
        conversation_history: List[Dict[str, str]],
        background_data: Dict,
        personal_memo: str
    ) -> Dict:
        """
        使用背景数据和个人备忘录进行深度分析（大模型专用）

        Args:
            user_question: 用户问题
            conversation_history: 对话历史
            background_data: 背景数据字典
            personal_memo: 个人备忘录

        Returns:
            分析结果字典 {"answer": str, "analysis": str}
        """
        try:
            # 构建增强的 system prompt
            enhanced_prompt = f"""{self.system_prompt}

【背景数据】
{self._format_background_data(background_data)}

【用户个人备忘录】
{personal_memo}

【任务】
基于以上背景数据和用户备忘录，深入分析用户的问题，提供专业、详细的回答。
"""

            # 临时保存原 prompt
            original_prompt = self.system_prompt
            self.system_prompt = enhanced_prompt

            # 调用对话
            answer = await self.chat(
                user_message=user_question,
                conversation_history=conversation_history,
                stream=True
            )

            # 恢复原 prompt
            self.system_prompt = original_prompt

            return {
                "answer": answer,
                "analysis": "深度分析完成"
            }

        except Exception as e:
            print(f"[TextLLM] 深度分析错误: {e}")
            import traceback
            traceback.print_exc()
            return {
                "answer": "",
                "analysis": f"分析失败: {str(e)}"
            }

    def _format_background_data(self, data: Dict) -> str:
        """格式化背景数据"""
        formatted = []
        for key, value in data.items():
            if isinstance(value, dict):
                formatted.append(f"\n## {key}")
                for sub_key, sub_value in value.items():
                    formatted.append(f"- {sub_key}: {sub_value}")
            else:
                formatted.append(f"\n## {key}")
                formatted.append(str(value))

        return "\n".join(formatted)


# 测试代码
async def test_text_llm_engine():
    """测试 Text LLM Engine"""

    # 从环境变量获取配置
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = "https://yunwu.zeabur.app"

    if not api_key:
        print("请设置 OPENAI_API_KEY 环境变量")
        return

    # 定义回调函数
    def on_response_start():
        print("🤖 AI 开始回复...")

    def on_text_delta(delta):
        print(delta, end="", flush=True)

    def on_response_done(full_text):
        print(f"\n✓ 回复完成: {len(full_text)} 字符")

    # 创建引擎
    engine = TextLLMEngine(
        api_key=api_key,
        base_url=base_url,
        model="gpt-4o",
        system_prompt="你是一个专业的技术顾问。",
        temperature=0.7,
        max_tokens=2000,
        callback_on_response_start=on_response_start,
        callback_on_text_delta=on_text_delta,
        callback_on_response_done=on_response_done
    )

    # 对话测试
    print("\n=== 测试 1: 简单对话 ===")
    response1 = await engine.chat("什么是 TEM（威胁与差错管理）？")

    print("\n\n=== 测试 2: 带历史的对话 ===")
    history = [
        {"role": "user", "content": "什么是 TEM（威胁与差错管理）？"},
        {"role": "assistant", "content": response1}
    ]
    await engine.chat("在航空领域如何应用？", conversation_history=history)

    print("\n\n=== 测试 3: 深度分析 ===")
    background_data = {
        "航班信息": {
            "航班号": "CA1234",
            "机型": "A320",
            "目的地": "北京"
        },
        "天气": "目的地有雾"
    }
    personal_memo = "我关注的是跑道视程问题"

    result = await engine.analyze_with_context(
        user_question="这次航班有什么风险？",
        conversation_history=history,
        background_data=background_data,
        personal_memo=personal_memo
    )

    print(f"\n分析结果: {result['answer']}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_text_llm_engine())
