#!/usr/bin/env python3
"""
Mini + TTS 引擎 - 保底语音交互方案
使用 gpt-4o-mini (文本生成) + edge-tts (流式TTS) + sounddevice (音频播放)
"""
import os
import asyncio
import re
import io
from typing import Optional, List, Dict

import numpy as np
import sounddevice as sd
import soundfile as sf
import edge_tts
from openai import AsyncOpenAI


class MiniTTSEngine:
    """gpt-4o-mini + edge-tts 流式引擎（保底方案）"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "gpt-4o-mini",
        voice: str = "zh-CN-XiaoxiaoNeural",
        system_prompt: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        callback_on_response_start=None,
        callback_on_text_delta=None,
        callback_on_tts_sentence=None,
        callback_on_response_done=None,
        callback_on_error=None
    ):
        """
        初始化 Mini+TTS 引擎

        Args:
            api_key: OpenAI API 密钥
            base_url: API Base URL
            model: 模型名称（默认 gpt-4o-mini）
            voice: edge-tts 语音（默认中文女声）
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大 token 数
            callback_on_response_start: 响应开始回调
            callback_on_text_delta: 文本增量回调 (delta_text)
            callback_on_tts_sentence: TTS 句子转换回调 (sentence, index, status)
            callback_on_response_done: 响应完成回调 (full_text)
            callback_on_error: 错误回调 (error_message)
        """
        self.api_key = api_key
        self.model = model
        self.voice = voice
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
        self.callback_on_tts_sentence = callback_on_tts_sentence
        self.callback_on_response_done = callback_on_response_done
        self.callback_on_error = callback_on_error

        # 创建 OpenAI 客户端
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )

        # 音频配置
        self.audio_sample_rate = 24000  # edge-tts 默认采样率
        self.audio_channels = 1
        self.audio_dtype = np.int16

        # 初始化音频流
        self._init_audio_stream()

        print(f"[MiniTTS] 初始化成功")
        print(f"[MiniTTS] Base URL: {base_url}")
        print(f"[MiniTTS] 模型: {model}")
        print(f"[MiniTTS] 语音: {voice}")
        print(f"[MiniTTS] Temperature: {temperature}")
        print(f"[MiniTTS] Max Tokens: {max_tokens}")

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
            print(f"[MiniTTS] 音频流初始化: {self.audio_sample_rate}Hz, 16-bit PCM")
        except Exception as e:
            print(f"[MiniTTS] 音频流初始化失败: {e}")
            self.audio_stream = None

    def update_system_prompt(self, new_prompt: str):
        """更新系统提示词"""
        self.system_prompt = new_prompt
        print(f"[MiniTTS] System Prompt 已更新: {new_prompt[:100]}...")

    async def chat(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        发送消息并接收流式响应（文本 + 语音）

        Args:
            user_message: 用户消息
            conversation_history: 对话历史 [{\"role\": \"user/assistant\", \"content\": \"...\"}]

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

            print(f"[MiniTTS] 发送消息: {user_message[:50]}...")
            print(f"[MiniTTS] 消息总数: {len(messages)} 条")

            # 调用流式 API
            return await self._chat_streaming_with_tts(messages)

        except Exception as e:
            error_msg = f"MiniTTS 错误: {str(e)}"
            print(f"[MiniTTS] {error_msg}")

            # 回调：错误
            if self.callback_on_error:
                self.callback_on_error(error_msg)

            import traceback
            traceback.print_exc()
            return ""

    async def _chat_streaming_with_tts(self, messages: List[Dict[str, str]]) -> str:
        """流式对话 + 实时 TTS"""
        full_response = ""
        first_chunk = True

        # 句子缓冲区
        sentence_buffer = ""
        sentence_index = 0

        # 音频存储字典 {sentence_index: [audio_chunks]}
        audio_storage = {}
        audio_storage_lock = asyncio.Lock()

        # 句子完成事件 {sentence_index: Event}
        sentence_ready_events = {}

        # 启动音频播放器（按顺序播放）
        async def audio_player(total_sentences):
            """后台播放音频 - 按句子索引顺序播放"""
            try:
                for expected_index in range(total_sentences):
                    # 等待当前句子准备好
                    if expected_index not in sentence_ready_events:
                        sentence_ready_events[expected_index] = asyncio.Event()

                    await sentence_ready_events[expected_index].wait()

                    # 从存储中取出音频数据
                    async with audio_storage_lock:
                        audio_chunks = audio_storage.get(expected_index, [])

                    # 播放所有音频块
                    if self.audio_stream and audio_chunks:
                        for audio_data in audio_chunks:
                            try:
                                # 将字节数据转换为 numpy 数组
                                audio_array = np.frombuffer(audio_data, dtype=self.audio_dtype)
                                if len(audio_array) > 0:
                                    audio_array = audio_array.reshape(-1, 1)

                                    loop = asyncio.get_event_loop()
                                    await loop.run_in_executor(
                                        None,
                                        self.audio_stream.write,
                                        audio_array
                                    )
                            except Exception as e:
                                print(f"[MiniTTS] 音频播放错误: {e}")

                    print(f"[MiniTTS] 句子 #{expected_index} 播放完成")

            except Exception as e:
                print(f"[MiniTTS] 音频播放器错误: {e}")

        # TTS 任务队列
        tts_tasks = []

        async def process_sentence(sentence: str, index: int):
            """处理单个句子的 TTS"""
            if not sentence.strip():
                return

            # 清理 Markdown 标记
            clean_sentence = self._clean_markdown(sentence)
            if not clean_sentence.strip():
                # 清理后为空，跳过
                if index not in sentence_ready_events:
                    sentence_ready_events[index] = asyncio.Event()
                sentence_ready_events[index].set()
                return

            print(f"[MiniTTS] TTS 句子 #{index}: {clean_sentence[:30]}...")

            # 回调：TTS 开始
            if self.callback_on_tts_sentence:
                self.callback_on_tts_sentence(clean_sentence, index, "converting")

            try:
                # edge-tts 转换 - 收集所有音频块
                communicate = edge_tts.Communicate(clean_sentence, self.voice)
                audio_bytes = b""

                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_bytes += chunk["data"]

                if not audio_bytes:
                    print(f"[MiniTTS] 警告：句子 #{index} 没有生成音频数据")
                    # 仍然设置事件，避免播放器卡住
                    if index not in sentence_ready_events:
                        sentence_ready_events[index] = asyncio.Event()
                    sentence_ready_events[index].set()
                    return

                # 使用 soundfile 解码音频数据（edge-tts 输出 MP3 格式）
                audio_buffer = io.BytesIO(audio_bytes)

                # 读取音频数据
                audio_data, sample_rate = sf.read(audio_buffer, dtype='float32')

                print(f"[MiniTTS] 音频解码: {len(audio_data)} 采样点, {sample_rate}Hz")

                # 回调：TTS 播放（注意：这里只是标记准备好，实际播放按顺序）
                if self.callback_on_tts_sentence:
                    self.callback_on_tts_sentence(clean_sentence, index, "queued")

                # 将音频数据处理并存储
                # 转换为 int16 格式（sounddevice 需要）
                if audio_data.ndim == 1:
                    # 单声道
                    audio_data = audio_data.reshape(-1, 1)
                elif audio_data.ndim == 2 and audio_data.shape[1] == 2:
                    # 立体声，转为单声道
                    audio_data = audio_data.mean(axis=1, keepdims=True)

                # 重采样到目标采样率（如果需要）
                if sample_rate != self.audio_sample_rate:
                    print(f"[MiniTTS] 重采样: {sample_rate}Hz -> {self.audio_sample_rate}Hz")
                    # 简单的线性插值重采样
                    ratio = self.audio_sample_rate / sample_rate
                    new_length = int(len(audio_data) * ratio)
                    audio_data = np.interp(
                        np.linspace(0, len(audio_data) - 1, new_length),
                        np.arange(len(audio_data)),
                        audio_data.flatten()
                    ).reshape(-1, 1)

                # 转换为 int16
                audio_int16 = (audio_data * 32767).astype(np.int16)

                # 分块存储到字典
                chunk_size = 4096
                audio_chunks = []
                for i in range(0, len(audio_int16), chunk_size):
                    chunk = audio_int16[i:i + chunk_size]
                    audio_chunks.append(chunk.tobytes())

                # 存储到字典并设置事件
                async with audio_storage_lock:
                    audio_storage[index] = audio_chunks

                # 确保事件存在并设置
                if index not in sentence_ready_events:
                    sentence_ready_events[index] = asyncio.Event()
                sentence_ready_events[index].set()

                print(f"[MiniTTS] TTS 句子 #{index} 转换完成")

            except Exception as e:
                print(f"[MiniTTS] TTS 错误 (句子 #{index}): {e}")
                import traceback
                traceback.print_exc()
                # 出错时也要设置事件，避免播放器卡住
                if index not in sentence_ready_events:
                    sentence_ready_events[index] = asyncio.Event()
                sentence_ready_events[index].set()

        # 开始流式生成
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
                sentence_buffer += delta

                if first_chunk:
                    first_chunk = False
                    # 回调：响应开始
                    if self.callback_on_response_start:
                        self.callback_on_response_start()

                # 回调：文本增量
                if self.callback_on_text_delta:
                    self.callback_on_text_delta(delta)

                # 检查是否有完整的句子
                sentences = self._split_sentences(sentence_buffer)
                if len(sentences) > 1:
                    # 处理除最后一个之外的所有句子（最后一个可能不完整）
                    for sentence in sentences[:-1]:
                        if sentence.strip():
                            # 创建 TTS 任务
                            task = asyncio.create_task(process_sentence(sentence, sentence_index))
                            tts_tasks.append(task)
                            sentence_index += 1

                    # 保留最后一个未完成的句子
                    sentence_buffer = sentences[-1]

        # 处理最后剩余的文本
        if sentence_buffer.strip():
            task = asyncio.create_task(process_sentence(sentence_buffer, sentence_index))
            tts_tasks.append(task)
            sentence_index += 1

        print(f"[MiniTTS] 文本生成完成: {len(full_response)} 字符")

        # 计算总句子数
        total_sentences = sentence_index

        if total_sentences > 0:
            # 启动播放器（需要知道总句子数）
            play_task = asyncio.create_task(audio_player(total_sentences))

            # 等待所有 TTS 任务完成
            if tts_tasks:
                await asyncio.gather(*tts_tasks)

            # 等待音频播放完成
            await play_task
        else:
            print(f"[MiniTTS] 没有生成任何句子")

        print(f"[MiniTTS] 音频播放完成")

        # 回调：响应完成
        if self.callback_on_response_done:
            self.callback_on_response_done(full_response)

        return full_response

    def _split_sentences(self, text: str) -> List[str]:
        """
        分割句子（中文和英文）

        Args:
            text: 输入文本

        Returns:
            句子列表
        """
        # 使用正则表达式分割句子（保留分隔符）
        # 中文：。！？\n
        # 英文：. ! ? \n
        pattern = r'([。！？.!?\n]+)'
        parts = re.split(pattern, text)

        # 重新组合句子（将分隔符附加到前一个句子）
        sentences = []
        for i in range(0, len(parts) - 1, 2):
            if i + 1 < len(parts):
                sentences.append(parts[i] + parts[i + 1])
            else:
                sentences.append(parts[i])

        # 添加最后一个部分（如果存在）
        if len(parts) % 2 == 1:
            sentences.append(parts[-1])

        return sentences

    def _clean_markdown(self, text: str) -> str:
        """
        清理 Markdown 格式标记，使文本适合 TTS

        Args:
            text: 包含 Markdown 标记的文本

        Returns:
            清理后的纯文本
        """
        # 1. 移除粗体和斜体标记
        # **粗体** 或 __粗体__
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        # *斜体* 或 _斜体_
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)

        # 2. 移除代码标记
        # `代码`
        text = re.sub(r'`(.+?)`', r'\1', text)
        # ```代码块```
        text = re.sub(r'```[\s\S]*?```', '', text)

        # 3. 移除删除线
        # ~~删除线~~
        text = re.sub(r'~~(.+?)~~', r'\1', text)

        # 4. 移除标题标记
        # # 标题
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)

        # 5. 移除列表标记
        # - 列表项 或 * 列表项 或 数字. 列表项
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

        # 6. 移除链接，保留文本
        # [文本](url)
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)

        # 7. 移除图片
        # ![alt](url)
        text = re.sub(r'!\[.*?\]\(.+?\)', '', text)

        # 8. 移除引用标记
        # > 引用
        text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)

        # 9. 移除水平线
        # --- 或 *** 或 ___
        text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)

        # 10. 移除多余的空行
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 11. 移除首尾空白
        text = text.strip()

        return text

    def cleanup(self):
        """清理资源"""
        if self.audio_stream:
            self.audio_stream.stop()
            self.audio_stream.close()
            print(f"[MiniTTS] 音频流已关闭")


# 测试代码
async def test_mini_tts_engine():
    """测试 Mini+TTS Engine"""

    # 从环境变量获取配置
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = "https://yunwu.zeabur.app"

    if not api_key:
        print("请设置 OPENAI_API_KEY 环境变量")
        return

    # 定义回调函数
    def on_response_start():
        print("\n🤖 AI 开始回复...")

    def on_text_delta(delta):
        print(delta, end="", flush=True)

    def on_tts_sentence(sentence, index, status):
        status_map = {
            "converting": "⏳ TTS转换",
            "playing": "🔊 播放中"
        }
        status_text = status_map.get(status, status)
        print(f"\n[{status_text}] 句子 #{index}: {sentence[:25]}...")

    def on_response_done(full_text):
        print(f"\n\n✓ 回复完成: {len(full_text)} 字符")

    # 创建引擎
    engine = MiniTTSEngine(
        api_key=api_key,
        base_url=base_url,
        model="gpt-4o-mini",
        voice="zh-CN-XiaoxiaoNeural",
        system_prompt="你是一名航空飞行员AI伙伴，正在与另一名飞行员进行TEM（威胁与差错管理）案例讨论。用简短、口语化的方式回答（10-20字）。",
        temperature=0.7,
        max_tokens=1000,
        callback_on_response_start=on_response_start,
        callback_on_text_delta=on_text_delta,
        callback_on_tts_sentence=on_tts_sentence,
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
    await engine.chat("APU故障会影响起飞吗？", conversation_history=history)

    # 清理
    engine.cleanup()
    print("\n✓ 测试完成")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_mini_tts_engine())
