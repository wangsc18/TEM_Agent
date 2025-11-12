#!/usr/bin/env python3
"""
语音交互引擎 - 整合STT、LLM、TTS和双模型管理
"""
import os
import time
import asyncio
import tempfile
import threading
from typing import Optional, Literal
import re
import wave

import numpy as np
import sounddevice as sd
from openai import AsyncOpenAI

from engines.dual_model_manager import DualModelManager


class VoiceInteractionEngine:
    """语音交互引擎 - 用于TEM模拟器"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        small_model: str = "gpt-4o-mini",
        big_model: str = "gpt-4o",
        tts_engine: Literal["local", "edge", "openai"] = "local",
        callback_on_user_text=None,
        callback_on_ai_text=None,
        callback_on_ai_text_streaming=None,
        callback_on_status=None,
        callback_on_big_model_triggered=None,
        enable_dual_model: bool = True
    ):
        """
        初始化语音交互引擎

        Args:
            small_model: 小模型（快速响应）
            big_model: 大模型（深度分析）
            enable_dual_model: 是否启用双模型架构
            callback_on_user_text: 当识别到用户语音时的回调 (user_text)
            callback_on_ai_text: 当AI生成完整回复时的回调 (ai_text)
            callback_on_ai_text_streaming: 当AI流式生成时的回调 (partial_text)
            callback_on_status: 状态更新回调 (status_text, status_type)
            callback_on_big_model_triggered: 当大模型被触发时的回调
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 OPENAI_API_KEY")

        self.client = AsyncOpenAI(api_key=self.api_key)
        self.small_model = small_model
        self.big_model = big_model
        self.tts_engine = tts_engine

        self.callback_on_user_text = callback_on_user_text
        self.callback_on_ai_text = callback_on_ai_text
        self.callback_on_ai_text_streaming = callback_on_ai_text_streaming
        self.callback_on_status = callback_on_status

        # 双模型管理器
        self.enable_dual_model = enable_dual_model
        if enable_dual_model:
            self.dual_model_manager = DualModelManager(
                self.client,
                small_model,
                big_model,
                callback_on_big_model_triggered=callback_on_big_model_triggered
            )
        else:
            self.dual_model_manager = None

        # 录音参数
        self.sample_rate = 16000
        self.max_recording_duration = 10
        self.silence_threshold = 1.5
        self.silence_duration_to_stop = 0.02

        # 对话历史 - TEM场景专用prompt（严格限制幻觉）
        self.base_system_prompt = """你是一名航空飞行员AI伙伴，正在与另一名飞行员进行TEM（威胁与差错管理）案例讨论。

【核心原则 - 安全第一】
在航空领域，准确性和安全性高于一切。你必须严格遵守以下规则：

❌ 绝对禁止的行为：
1. 编造或猜测专业数据（如MEL条款、性能数据、法规条款）
2. 对不确定的专业问题给出模糊或猜测性的回答
3. 回答超出你当前信息范围的专业问题

✅ 必须遵守的行为：
1. 如果问题涉及具体的专业知识（MEL、运行手册、法规、性能计算等），你必须立即回复"让我查找一下相关信息"
2. 只讨论你已知的、确定的信息
3. 用口语化、简短的方式交流（10-20字）
4. 适当使用"嗯"、"好的"等口语化表达

【何时必须说"让我查找一下相关信息"】
- 用户问到具体的MEL条款、限制、手册条款
- 涉及性能计算、重量限制等具体数值
- 需要引用法规、运行标准
- 任何你不100%确定的专业问题

【你可以直接回答的】
- 一般性的威胁识别和讨论
- 基于已知信息的观察和总结
- 对话引导和确认性问题

示例对话：
用户: "APU故障会影响起飞吗？"
❌ 错误: "会的，需要延长起飞滑跑距离，大约增加10%。"（编造数据）
✅ 正确: "嗯，让我查找一下相关信息。"（触发专家分析）

用户: "你觉得这次飞行有哪些潜在威胁？"
✅ 正确: "我看到几个威胁，目的地有雾，跑道缩短，还有APU故障。"（基于已知信息）

记住：宁可谨慎地说"让我查找一下"，也不要给出不确定的专业建议！"""

        self.conversation_history = [
            {
                "role": "system",
                "content": self.base_system_prompt
            }
        ]

        # 用于在后台线程运行异步任务
        self.loop = None
        self.recording = False
        self.current_audio_data = []

        # 背景数据和用户备忘录（用于大模型分析）
        self.background_data = {}
        self.personal_memo = ""

    def set_background_data(self, data: dict):
        """设置背景数据（用于大模型）"""
        self.background_data = data

    def set_personal_memo(self, memo: str):
        """设置用户个人备忘录（用于大模型）"""
        self.personal_memo = memo

    def _update_status(self, text: str, status_type: str = "info"):
        """更新状态（在主线程调用回调）"""
        if self.callback_on_status:
            self.callback_on_status(text, status_type)

    def _on_user_text_recognized(self, text: str):
        """用户语音识别完成"""
        if self.callback_on_user_text:
            self.callback_on_user_text(text)

    def _on_ai_response(self, text: str):
        """AI回复生成完成"""
        if self.callback_on_ai_text:
            self.callback_on_ai_text(text)

    def _on_ai_response_streaming(self, text: str):
        """AI流式生成中（每生成一个句子调用）"""
        if self.callback_on_ai_text_streaming:
            self.callback_on_ai_text_streaming(text)

    def start_recording(self):
        """开始录音（仅录音+STT，不触发LLM）"""
        def run_async_recording():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.loop = loop
            loop.run_until_complete(self._async_record_and_transcribe())

        thread = threading.Thread(target=run_async_recording, daemon=True)
        thread.start()

    async def _async_record_and_transcribe(self):
        """异步录音并转文字（仅STT，不调用LLM）"""
        try:
            # 1. 录音
            self._update_status("🎤 正在录音...", "recording")
            audio_data = await self._record_audio()

            if audio_data is None:
                self._update_status("❌ 录音失败", "error")
                return

            # 2. 语音识别
            self._update_status("🔄 语音识别中...", "processing")
            user_text = await self._speech_to_text(audio_data)

            if not user_text:
                self._update_status("❌ 未识别到语音", "error")
                return

            # 3. 将识别结果填充到输入框（不自动发送）
            self._on_user_text_recognized(user_text)
            self._update_status("✓ 识别完成，请确认后发送", "success")

        except Exception as e:
            self._update_status(f"❌ 错误: {str(e)}", "error")

    def process_user_message(self, user_message: str):
        """处理用户消息（LLM对话+TTS）- 支持双模型"""
        def run_async_processing():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.loop = loop
            loop.run_until_complete(self._async_llm_and_tts(user_message))

        thread = threading.Thread(target=run_async_processing, daemon=True)
        thread.start()

    async def _async_llm_and_tts(self, user_message: str):
        """异步LLM生成和TTS播放 - 整合双模型逻辑"""
        try:
            # 添加用户消息到历史
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })

            # 1. 更新系统提示（如果有策略更新）
            if self.enable_dual_model and self.dual_model_manager:
                enhanced_prompt = self.dual_model_manager.get_enhanced_system_prompt(
                    self.base_system_prompt
                )
                self.conversation_history[0]["content"] = enhanced_prompt

            # 2. 开始流式LLM生成（小模型）
            self._update_status("🤖 AI思考中...", "processing")

            stream = await self.client.chat.completions.create(
                model=self.small_model,
                messages=self.conversation_history,
                stream=True,
                temperature=0.7,
                max_tokens=300
            )

            # 3. 流式处理：边生成边TTS
            full_response = ""
            current_chunk = ""
            audio_queue = []  # 存储待播放的音频文件
            should_trigger_big_model = False

            # 启动音频播放协程
            play_task = asyncio.create_task(self._audio_player(audio_queue))

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    current_chunk += token
                    full_response += token

                    # 检测是否有完整的句子/短语
                    sentences = self._extract_complete_sentences(current_chunk)

                    if sentences:
                        for sentence in sentences:
                            # 流式更新显示（每生成一个句子就显示）
                            self._on_ai_response_streaming(sentence)

                            # 检测是否触发大模型
                            if (self.enable_dual_model and
                                self.dual_model_manager and
                                self.dual_model_manager.check_if_trigger_big_model(sentence)):
                                should_trigger_big_model = True

                            # 立即进行TTS
                            audio_file = await self._quick_tts(sentence)
                            if audio_file:
                                audio_queue.append(audio_file)

                                # 首次播放时更新状态
                                if len(audio_queue) == 1:
                                    self._update_status("🔊 播放AI语音...", "speaking")

                        # 重置缓冲区（保留未完成的部分）
                        current_chunk = self._get_remaining_text(current_chunk, sentences)

            # 处理最后剩余的文本
            if current_chunk.strip():
                self._on_ai_response_streaming(current_chunk.strip())
                audio_file = await self._quick_tts(current_chunk.strip())
                if audio_file:
                    audio_queue.append(audio_file)

            # 标记音频队列结束
            audio_queue.append(None)  # 结束信号

            # 等待所有音频播放完成
            await play_task

            # 添加AI回复到历史
            self.conversation_history.append({
                "role": "assistant",
                "content": full_response
            })

            # 4. 如果触发了大模型，后台异步处理
            if should_trigger_big_model:
                print("[语音引擎] 检测到触发词，启动大模型分析...")
                self._update_status("🧠 正在深度分析...", "processing")

                # 在独立线程中运行大模型（避免event loop过早结束）
                def run_big_model():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(self._process_with_big_model(user_message))
                    except Exception as e:
                        print(f"[大模型线程] 错误: {e}")
                    finally:
                        loop.close()

                thread = threading.Thread(target=run_big_model, daemon=True)
                thread.start()
                print("[语音引擎] 大模型线程已启动")

            # 回调显示完整回复
            self._on_ai_response(full_response.strip())

            self._update_status("✓ 完成", "success")

        except Exception as e:
            self._update_status(f"❌ 错误: {str(e)}", "error")
            print(f"流式LLM+TTS错误: {e}")

    async def _process_with_big_model(self, user_question: str):
        """后台使用大模型处理复杂问题"""
        try:
            result = await self.dual_model_manager.process_with_big_model(
                user_question,
                self.conversation_history,
                self.background_data,
                self.personal_memo
            )

            # 大模型的答案
            big_model_answer = result["answer"]

            # 流式播放大模型的回复
            self._update_status("🎓 专家回复中...", "speaking")

            # 添加一个标识前缀
            prefix = "根据详细分析，"
            self._on_ai_response_streaming(prefix)
            audio_file = await self._quick_tts(prefix)
            if audio_file:
                await self._play_single_audio(audio_file)

            # 分句播放大模型回复
            sentences = self._extract_complete_sentences(big_model_answer)
            for sentence in sentences:
                self._on_ai_response_streaming(sentence)
                audio_file = await self._quick_tts(sentence)
                if audio_file:
                    await self._play_single_audio(audio_file)

            # 添加大模型回复到历史
            self.conversation_history.append({
                "role": "assistant",
                "content": prefix + big_model_answer
            })

            self._update_status("✓ 专家分析完成", "success")

        except Exception as e:
            import traceback
            print(f"[大模型处理] 错误: {e}")
            print(f"[大模型处理] 详细错误:\n{traceback.format_exc()}")
            self._update_status(f"❌ 大模型处理失败: {str(e)}", "error")

    async def _play_single_audio(self, audio_file: str):
        """播放单个音频文件"""
        if os.path.exists(audio_file):
            play_process = await asyncio.create_subprocess_exec(
                "afplay", audio_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await play_process.communicate()
            try:
                os.unlink(audio_file)
            except:
                pass

    def _extract_complete_sentences(self, text: str) -> list:
        """提取完整的句子（按标点符号分割）"""
        # 匹配中英文标点
        pattern = r'([^，。！？,\.!?]+[，。！？,\.!?]+)'
        matches = re.findall(pattern, text)
        return [m.strip() for m in matches if m.strip()]

    def _get_remaining_text(self, text: str, extracted_sentences: list) -> str:
        """获取提取句子后剩余的文本"""
        for sentence in extracted_sentences:
            text = text.replace(sentence, '', 1)
        return text

    async def _quick_tts(self, text: str) -> Optional[str]:
        """快速TTS（单个句子/短语）"""
        try:
            if self.tts_engine == "local":
                # macOS say命令（最快）
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".m4a")
                temp_file.close()

                process = await asyncio.create_subprocess_exec(
                    "say",
                    "-v", "Tingting",
                    "-o", temp_file.name,
                    "--data-format=LEF32@22050",
                    text,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()

                if process.returncode == 0 and os.path.exists(temp_file.name):
                    return temp_file.name
                else:
                    if os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)
                    return None

            elif self.tts_engine == "edge":
                # Edge TTS
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                temp_file.close()

                process = await asyncio.create_subprocess_exec(
                    "edge-tts",
                    "--voice", "zh-CN-XiaoxiaoNeural",
                    "--rate", "+10%",
                    "--pitch", "+5Hz",
                    "--text", text,
                    "--write-media", temp_file.name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()

                if process.returncode == 0 and os.path.exists(temp_file.name):
                    return temp_file.name
                else:
                    if os.path.exists(temp_file.name):
                        os.unlink(temp_file.name)
                    return None

            else:  # openai
                # OpenAI TTS（较慢，不推荐流式使用）
                response = await self.client.audio.speech.create(
                    model="tts-1",
                    voice="nova",
                    input=text
                )

                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                temp_file.write(response.content)
                temp_file.close()
                return temp_file.name

        except Exception as e:
            print(f"快速TTS错误: {e}")
            return None

    async def _audio_player(self, audio_queue: list):
        """音频播放器（并发播放队列中的音频）"""
        try:
            while True:
                # 等待队列中有音频
                while len(audio_queue) == 0:
                    await asyncio.sleep(0.1)

                # 取出音频文件
                audio_file = audio_queue.pop(0)

                # None表示队列结束
                if audio_file is None:
                    break

                # 播放音频
                await self._play_single_audio(audio_file)

        except Exception as e:
            print(f"音频播放器错误: {e}")

    async def _record_audio(self) -> Optional[np.ndarray]:
        """录音（简化版，自动静音检测）"""
        try:
            audio_chunks = []
            silence_start_time = None

            def audio_callback(indata, _frames, _time_info, status):
                if status:
                    print(f"录音状态: {status}")
                audio_chunks.append(indata.copy())

            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype=np.float32,
                callback=audio_callback
            ):
                start_time = time.time()
                while time.time() - start_time < self.max_recording_duration:
                    await asyncio.sleep(0.1)

                    if len(audio_chunks) > 0:
                        recent_audio = np.concatenate(audio_chunks[-5:])
                        rms = np.sqrt(np.mean(recent_audio ** 2))

                        if rms < self.silence_duration_to_stop:
                            if silence_start_time is None:
                                silence_start_time = time.time()
                            elif time.time() - silence_start_time > self.silence_threshold:
                                break
                        else:
                            silence_start_time = None

            if len(audio_chunks) == 0:
                return None

            audio_data = np.concatenate(audio_chunks)
            return audio_data

        except Exception as e:
            print(f"录音错误: {e}")
            return None

    async def _speech_to_text(self, audio_data: np.ndarray) -> str:
        """语音转文字"""
        try:
            # 保存为临时WAV文件
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")

            with wave.open(temp_file.name, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                audio_int16 = (audio_data * 32767).astype(np.int16)
                wf.writeframes(audio_int16.tobytes())

            # 调用Whisper API
            with open(temp_file.name, 'rb') as audio_file:
                transcription = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="zh"
                )

            os.unlink(temp_file.name)
            return transcription.text.strip()

        except Exception as e:
            print(f"STT错误: {e}")
            return ""
