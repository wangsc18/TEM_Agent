#!/usr/bin/env python3
"""
Azure Realtime API 语音引擎 - 小模型专用
流式音频输入输出，超低延迟
"""
import os
import base64
import asyncio
from typing import Optional

import numpy as np
import sounddevice as sd
from openai import AsyncOpenAI


class RealtimeVoiceEngine:
    """Azure Realtime API 语音引擎（小模型）"""

    def __init__(
        self,
        azure_endpoint: str,
        azure_api_key: str,
        deployment_name: str = "gpt-realtime-mini",
        voice: str = "alloy",
        system_prompt: str = "",
        callback_on_response_start=None,
        callback_on_audio_chunk=None,
        callback_on_transcript_delta=None,
        callback_on_response_done=None,
        callback_on_error=None
    ):
        """
        初始化 Realtime 语音引擎

        Args:
            azure_endpoint: Azure OpenAI 端点
            azure_api_key: Azure API 密钥
            deployment_name: 部署名称
            voice: 语音类型 (alloy, echo, shimmer)
            system_prompt: 系统提示词
            callback_on_response_start: 响应开始回调
            callback_on_audio_chunk: 音频块接收回调 (audio_data)
            callback_on_transcript_delta: 转录文本增量回调 (delta_text)
            callback_on_response_done: 响应完成回调 (full_transcript)
            callback_on_error: 错误回调 (error_message)
        """
        self.azure_endpoint = azure_endpoint
        self.azure_api_key = azure_api_key
        self.deployment_name = deployment_name
        self.voice = voice
        self.system_prompt = system_prompt

        # 回调函数
        self.callback_on_response_start = callback_on_response_start
        self.callback_on_audio_chunk = callback_on_audio_chunk
        self.callback_on_transcript_delta = callback_on_transcript_delta
        self.callback_on_response_done = callback_on_response_done
        self.callback_on_error = callback_on_error

        # 音频配置
        self.audio_sample_rate = 24000
        self.audio_channels = 1
        self.audio_dtype = np.int16

        # 初始化音频流
        self._init_audio_stream()

        print(f"[RealtimeVoice] 初始化成功")
        print(f"[RealtimeVoice] 端点: {azure_endpoint}")
        print(f"[RealtimeVoice] 部署: {deployment_name}")
        print(f"[RealtimeVoice] 语音: {voice}")

    def _init_audio_stream(self):
        """初始化 sounddevice 音频流"""
        try:
            self.audio_stream = sd.OutputStream(
                samplerate=self.audio_sample_rate,
                channels=self.audio_channels,
                dtype=self.audio_dtype,
                blocksize=4096
            )
            self.audio_stream.start()
            print(f"[RealtimeVoice] 音频流初始化: {self.audio_sample_rate}Hz, 16-bit PCM")
        except Exception as e:
            print(f"[RealtimeVoice] 音频流初始化失败: {e}")
            self.audio_stream = None

    def update_system_prompt(self, new_prompt: str):
        """更新系统提示词"""
        self.system_prompt = new_prompt
        print(f"[RealtimeVoice] System Prompt 已更新: {new_prompt[:100]}...")

    async def chat(self, user_message: str, conversation_history: list = None):
        """
        发送消息并接收流式音频响应

        Args:
            user_message: 用户消息
            conversation_history: 对话历史 [{"role": "user/assistant", "content": "..."}]

        Returns:
            完整的 AI 回复文本（转录）
        """
        try:
            # 创建 WebSocket 客户端
            base_url = self.azure_endpoint.replace("https://", "wss://").rstrip("/") + "/openai/v1"

            realtime_client = AsyncOpenAI(
                websocket_base_url=base_url,
                api_key=self.azure_api_key
            )

            print(f"[RealtimeVoice] 连接到: {base_url}")

            # 创建异步音频队列
            audio_queue = asyncio.Queue()

            # 启动音频播放协程
            async def audio_player():
                """后台播放音频"""
                try:
                    while True:
                        audio_data = await audio_queue.get()
                        if audio_data is None:
                            break

                        # 播放音频
                        if self.audio_stream:
                            try:
                                audio_array = np.frombuffer(audio_data, dtype=self.audio_dtype)
                                audio_array = audio_array.reshape(-1, 1)

                                loop = asyncio.get_event_loop()
                                await loop.run_in_executor(
                                    None,
                                    self.audio_stream.write,
                                    audio_array
                                )

                                # 回调：音频块播放
                                if self.callback_on_audio_chunk:
                                    self.callback_on_audio_chunk(audio_data)

                            except Exception as e:
                                print(f"[RealtimeVoice] 音频播放错误: {e}")

                        audio_queue.task_done()
                except Exception as e:
                    print(f"[RealtimeVoice] 音频播放器错误: {e}")

            play_task = asyncio.create_task(audio_player())

            # 连接并配置 session
            async with realtime_client.realtime.connect(
                model=self.deployment_name,
            ) as connection:
                # 配置 session
                await connection.session.update(session={
                    "output_modalities": ["audio"],
                    "audio": {
                        "output": {
                            "voice": self.voice,
                            "format": {
                                "type": "audio/pcm",
                                "rate": 24000,
                            }
                        }
                    }
                })

                print(f"[RealtimeVoice] Session 配置完成")

                # 添加 system prompt
                if self.system_prompt:
                    print(f"[RealtimeVoice] 添加 system prompt")
                    await connection.conversation.item.create(
                        item={
                            "type": "message",
                            "role": "system",
                            "content": [{"type": "input_text", "text": self.system_prompt}],
                        }
                    )

                # 添加历史对话
                if conversation_history:
                    print(f"[RealtimeVoice] 添加 {len(conversation_history)} 条历史消息")
                    for msg in conversation_history:
                        await connection.conversation.item.create(
                            item={
                                "type": "message",
                                "role": msg["role"],
                                "content": [{"type": "input_text", "text": msg["content"]}],
                            }
                        )

                # 发送当前用户消息
                print(f"[RealtimeVoice] 发送用户消息: {user_message[:30]}...")
                await connection.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_message}],
                    }
                )
                await connection.response.create()

                # 实时接收事件
                full_response = ""
                audio_chunk_count = 0
                first_chunk = True

                async for event in connection:
                    if event.type == "response.output_audio.delta":
                        # 音频数据块
                        audio_data = base64.b64decode(event.delta)
                        await audio_queue.put(audio_data)

                        audio_chunk_count += 1
                        if first_chunk:
                            first_chunk = False
                            # 回调：响应开始
                            if self.callback_on_response_start:
                                self.callback_on_response_start()

                    elif event.type == "response.output_audio_transcript.delta":
                        # 转录文本增量
                        delta_text = event.delta
                        full_response += delta_text

                        # 回调：转录增量
                        if self.callback_on_transcript_delta:
                            self.callback_on_transcript_delta(delta_text)

                    elif event.type == "response.output_audio_transcript.done":
                        print(f"[RealtimeVoice] 转录完成: {full_response[:50]}...")

                    elif event.type == "response.done":
                        print(f"[RealtimeVoice] 响应完成，共接收 {audio_chunk_count} 个音频块")
                        break

            # 等待音频播放完成
            await audio_queue.put(None)
            await play_task
            print(f"[RealtimeVoice] 音频播放完成")

            # 回调：响应完成
            if self.callback_on_response_done:
                self.callback_on_response_done(full_response)

            return full_response

        except Exception as e:
            error_msg = f"RealtimeVoice 错误: {str(e)}"
            print(f"[RealtimeVoice] {error_msg}")

            # 回调：错误
            if self.callback_on_error:
                self.callback_on_error(error_msg)

            import traceback
            traceback.print_exc()
            return ""

    def cleanup(self):
        """清理资源"""
        if self.audio_stream:
            self.audio_stream.stop()
            self.audio_stream.close()
            print(f"[RealtimeVoice] 音频流已关闭")


# 测试代码
async def test_realtime_voice_engine():
    """测试 Realtime Voice Engine"""

    # 从环境变量获取配置
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_api_key = os.getenv("AZURE_OPENAI_API_KEY")

    if not azure_endpoint or not azure_api_key:
        print("请设置 AZURE_OPENAI_ENDPOINT 和 AZURE_OPENAI_API_KEY 环境变量")
        return

    # 定义回调函数
    def on_response_start():
        print("🔊 AI 开始回复...")

    def on_transcript_delta(delta):
        print(delta, end="", flush=True)

    def on_response_done(full_text):
        print(f"\n✓ 回复完成: {len(full_text)} 字")

    # 创建引擎
    engine = RealtimeVoiceEngine(
        azure_endpoint=azure_endpoint,
        azure_api_key=azure_api_key,
        deployment_name="gpt-realtime-mini",
        voice="alloy",
        system_prompt="你是一个友好的AI助手。",
        callback_on_response_start=on_response_start,
        callback_on_transcript_delta=on_transcript_delta,
        callback_on_response_done=on_response_done
    )

    # 对话测试
    print("\n=== 测试 1: 简单对话 ===")
    response1 = await engine.chat("你好，介绍一下你自己")

    print("\n\n=== 测试 2: 带历史的对话 ===")
    history = [
        {"role": "user", "content": "你好，介绍一下你自己"},
        {"role": "assistant", "content": response1}
    ]
    await engine.chat("你能做什么？", conversation_history=history)

    # 清理
    engine.cleanup()


if __name__ == "__main__":
    asyncio.run(test_realtime_voice_engine())
