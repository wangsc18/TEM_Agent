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
from datetime import datetime
import re
import wave
import subprocess
import base64

import numpy as np
import sounddevice as sd
from openai import AsyncOpenAI

from engines.dual_model_manager import DualModelManager


class VoiceInteractionEngine:
    """语音交互引擎 - 用于TEM模拟器"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        azure_endpoint: Optional[str] = None,
        azure_api_key: Optional[str] = None,
        azure_realtime_deployment: Optional[str] = None,
        small_model: str = "gpt-4o-mini",
        big_model: str = "gpt-4o",
        tts_engine: Literal["local", "edge", "openai"] = "local",
        voice_mode: Literal["audio", "text", "realtime"] = "text",
        audio_voice: str = "alloy",
        audio_format: str = "wav",
        callback_on_user_text=None,
        callback_on_ai_text=None,
        callback_on_ai_text_streaming=None,
        callback_on_status=None,
        callback_on_big_model_triggered=None,
        callback_on_tts_progress=None,
        enable_dual_model: bool = True
    ):
        """
        初始化语音交互引擎

        Args:
            api_key: OpenAI API密钥
            base_url: 自定义API Base URL（用于第三方平台）
            azure_endpoint: Azure OpenAI端点（用于Realtime API）
            azure_api_key: Azure OpenAI API密钥
            azure_realtime_deployment: Azure Realtime部署名称
            small_model: 小模型（快速响应）
            big_model: 大模型（深度分析）
            tts_engine: TTS引擎（text模式时使用）
            voice_mode: 语音模式 ("audio"=直接音频输出, "text"=文本→TTS, "realtime"=流式音频)
            audio_voice: 音频语音（audio/realtime模式时使用）
            audio_format: 音频格式（audio模式时使用）
            enable_dual_model: 是否启用双模型架构
            callback_on_user_text: 当识别到用户语音时的回调 (user_text)
            callback_on_ai_text: 当AI生成完整回复时的回调 (ai_text)
            callback_on_ai_text_streaming: 当AI流式生成时的回调 (partial_text)
            callback_on_status: 状态更新回调 (status_text, status_type)
            callback_on_big_model_triggered: 当大模型被触发时的回调
            callback_on_tts_progress: TTS进度回调 (sentence, current_index, total_count, status)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 OPENAI_API_KEY")

        # Azure Realtime API 配置
        self.azure_endpoint = azure_endpoint
        self.azure_api_key = azure_api_key
        self.azure_realtime_deployment = azure_realtime_deployment or "gpt-realtime-mini"
        self.use_realtime_api = False  # 标志位，稍后根据配置设置

        # 处理自定义 Base URL（参考 test_audio_model_simple.py）
        if base_url:
            # 确保有协议前缀
            if not base_url.startswith("http"):
                base_url = f"https://{base_url}"
            # 确保有 /v1 路径
            if not base_url.endswith("/v1"):
                base_url = f"{base_url}/v1"
            print(f"[API配置] 使用自定义Base URL: {base_url}")

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=base_url  # 传入 base_url
        )
        self.small_model = small_model
        self.big_model = big_model
        self.tts_engine = tts_engine
        self.voice_mode = voice_mode
        self.audio_voice = audio_voice
        self.audio_format = audio_format

        self.callback_on_user_text = callback_on_user_text
        self.callback_on_ai_text = callback_on_ai_text
        self.callback_on_ai_text_streaming = callback_on_ai_text_streaming
        self.callback_on_status = callback_on_status
        self.callback_on_tts_progress = callback_on_tts_progress

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

        # TTS音频保存目录
        self.tts_audio_dir = os.path.join(os.getcwd(), "tts_audio_debug")
        os.makedirs(self.tts_audio_dir, exist_ok=True)

        # 根据语音模式初始化
        if self.voice_mode == "realtime":
            # 检查 Azure Realtime API 配置
            if self.azure_endpoint and self.azure_api_key:
                self.use_realtime_api = True
                print(f"[语音引擎] 模式: Realtime流式音频 (Azure OpenAI)")
                print(f"[Realtime配置] 端点: {self.azure_endpoint}")
                print(f"[Realtime配置] 部署: {self.azure_realtime_deployment}")
                print(f"[Realtime配置] 语音: {self.audio_voice}")

                # 初始化 sounddevice 音频流
                self.audio_sample_rate = 24000
                self.audio_channels = 1
                self.audio_dtype = np.int16

                try:
                    # 创建持久的音频输出流
                    self.audio_stream = sd.OutputStream(
                        samplerate=self.audio_sample_rate,
                        channels=self.audio_channels,
                        dtype=self.audio_dtype,
                        blocksize=4096
                    )
                    self.audio_stream.start()
                    print(f"[音频流] 初始化成功: {self.audio_sample_rate}Hz, {self.audio_channels}通道, 16-bit PCM")
                except Exception as e:
                    print(f"[音频流] 初始化失败: {e}")
                    self.audio_stream = None
            else:
                print(f"[语音引擎] ⚠️ realtime 模式需要 Azure 配置，回退到 audio 模式")
                self.voice_mode = "audio"
                self.use_realtime_api = False

        if self.voice_mode == "audio":
            print(f"[语音引擎] 模式: Audio直出 (跳过TTS)")
            print(f"[语音引擎] 音频语音: {self.audio_voice}")
            print(f"[语音引擎] 音频文件保存路径: {self.tts_audio_dir}")
        elif self.voice_mode == "text":
            print(f"[语音引擎] 模式: 文本→TTS")
            print(f"[TTS调试] 音频文件保存路径: {self.tts_audio_dir}")
            # TTS音频裁剪设置（去除结尾静音）
            self.trim_end_silence_ms = 200  # 裁剪结尾200ms
            print(f"[TTS优化] 自动裁剪结尾静音: {self.trim_end_silence_ms}ms")

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

    def _on_tts_progress(self, sentence: str, index: int, status: str):
        """TTS进度更新（sentence: 句子内容, index: 序号, status: 状态）"""
        if self.callback_on_tts_progress:
            self.callback_on_tts_progress(sentence, index, status)

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
            # 根据语音模式选择不同的处理路径
            if self.voice_mode == "realtime" and self.use_realtime_api:
                await self._async_llm_with_realtime_audio(user_message)
            elif self.voice_mode == "audio":
                await self._async_llm_with_audio(user_message)
            else:
                await self._async_llm_with_text_tts(user_message)

        except Exception as e:
            self._update_status(f"❌ 错误: {str(e)}", "error")
            print(f"LLM处理错误: {e}")

    async def _async_llm_with_audio(self, user_message: str):
        """Audio模式：使用 gpt-4o-audio-preview 直接输出音频（跳过TTS）"""
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

            # 2. 调用Audio API（非流式）
            self._update_status("🤖 AI思考中...", "processing")

            # 打印请求参数（调试用）
            print(f"[Audio请求] 模型: {self.small_model}")
            print(f"[Audio请求] 模态: ['text', 'audio']")
            print(f"[Audio请求] 语音: {self.audio_voice}")
            print(f"[Audio请求] 格式: {self.audio_format}")

            response = await self.client.chat.completions.create(
                model=self.small_model,  # gpt-4o-audio-preview
                modalities=["text", "audio"],
                audio={
                    "voice": self.audio_voice,
                    "format": self.audio_format
                },
                messages=self.conversation_history
            )

            # 调试：查看响应结构
            print(f"[Audio调试] 响应类型: {type(response)}")
            print(f"[Audio调试] 是否有choices: {hasattr(response, 'choices')}")
            if hasattr(response, 'choices') and len(response.choices) > 0:
                choice = response.choices[0]
                print(f"[Audio调试] 是否有message: {hasattr(choice, 'message')}")
                if hasattr(choice, 'message'):
                    print(f"[Audio调试] 是否有content: {hasattr(choice.message, 'content')}")
                    print(f"[Audio调试] content值: {choice.message.content}")
                    print(f"[Audio调试] 是否有audio: {hasattr(choice.message, 'audio')}")
                    if hasattr(choice.message, 'audio'):
                        print(f"[Audio调试] audio值: {choice.message.audio}")
                        # 更详细的audio调试
                        if choice.message.audio is not None:
                            print(f"[Audio调试] audio类型: {type(choice.message.audio)}")
                            print(f"[Audio调试] audio属性: {dir(choice.message.audio)}")
                        else:
                            print(f"[Audio调试] ⚠️ audio为None! 可能原因:")
                            print(f"            1. 平台不完全支持audio模态")
                            print(f"            2. 请求参数不正确")
                            print(f"            3. API内容策略限制")

                    # 打印完整响应（用于调试）
                    print(f"[Audio调试] 完整choice.message对象: {choice.message}")
                    print(f"[Audio调试] finish_reason: {choice.finish_reason}")

            # 3. 提取响应
            if isinstance(response, str):
                # 如果返回的是字符串（某些平台可能不支持audio模式）
                print(f"[Audio模式] ⚠️ 平台返回字符串而非音频对象，可能不支持audio模式")
                full_response = response
                self._on_ai_response(full_response)

                # 添加到历史
                self.conversation_history.append({
                    "role": "assistant",
                    "content": full_response
                })

                self._update_status("⚠️ 平台可能不支持audio模式，已切换为文本", "error")
                return

            choice = response.choices[0]
            full_response = ""

            # 音频响应
            if hasattr(choice.message, 'audio') and choice.message.audio:
                audio_data_base64 = choice.message.audio.data
                audio_transcript = choice.message.audio.transcript

                if audio_transcript:
                    # 使用转录文本作为回复内容
                    full_response = audio_transcript
                    # 流式显示转录文本到界面
                    self._on_ai_response_streaming(audio_transcript)
                    print(f"[Audio模式] 音频转录: {audio_transcript}")

                # 解码音频
                audio_bytes = base64.b64decode(audio_data_base64)
                audio_array = np.frombuffer(audio_bytes, dtype=np.int16)

                # 保存音频文件（用于调试）
                timestamp = datetime.now().strftime("%H%M%S")
                filename = f"ai_response_{timestamp}.{self.audio_format}"
                audio_path = os.path.join(self.tts_audio_dir, filename)

                with wave.open(audio_path, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(24000)  # Audio API使用24kHz
                    wf.writeframes(audio_array.tobytes())

                print(f"[Audio模式] 已保存音频: {filename}")

                # 播放音频
                self._update_status("🔊 播放AI语音...", "speaking")
                await self._play_single_audio(audio_path)

            # 文本响应（如果有的话，作为备用或audio为None时使用）
            elif choice.message.content:
                full_response = choice.message.content
                self._on_ai_response_streaming(full_response)
                print(f"[Audio模式] ⚠️ API未返回音频，回退到文本模式")
                print(f"[Audio模式] AI文本回复: {full_response}")

                # 【新增】如果audio为None，自动使用TTS转换文本
                print(f"[Audio回退] 使用TTS引擎生成音频...")
                self._update_status("🔊 TTS转换中...", "processing")

                # 分句处理（避免一次性转换过长文本）
                sentences = self._extract_complete_sentences(full_response)
                if not sentences:  # 如果没有分句，直接使用完整文本
                    sentences = [full_response]

                for sentence in sentences:
                    audio_file = await self._quick_tts(sentence)
                    if audio_file:
                        self._update_status("🔊 播放AI语音...", "speaking")
                        await self._play_single_audio(audio_file)

                print(f"[Audio回退] TTS转换完成")

            # 添加AI回复到历史（使用文本版本）
            self.conversation_history.append({
                "role": "assistant",
                "content": full_response
            })

            # 4. 检查是否触发大模型（基于文本响应）
            should_trigger_big_model = False
            if (self.enable_dual_model and
                self.dual_model_manager and
                self.dual_model_manager.check_if_trigger_big_model(full_response)):
                should_trigger_big_model = True

            # 如果触发了大模型，后台异步处理
            if should_trigger_big_model:
                print("[Audio模式] 检测到触发词，启动大模型分析...")
                self._update_status("🧠 正在深度分析...", "processing")

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
                print("[Audio模式] 大模型线程已启动")

            self._update_status("✓ 完成", "success")

        except Exception as e:
            self._update_status(f"❌ 错误: {str(e)}", "error")
            print(f"Audio模式错误: {e}")
            import traceback
            traceback.print_exc()

    async def _async_llm_with_realtime_audio(self, user_message: str):
        """Realtime模式：使用 Azure Realtime API 流式输出音频（WebSocket）"""
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
                current_system_prompt = enhanced_prompt
            else:
                current_system_prompt = self.base_system_prompt

            # 调试：打印 system prompt
            print(f"[Realtime调试] System Prompt (前100字): {current_system_prompt[:100]}...")
            print(f"[Realtime调试] 对话历史长度: {len(self.conversation_history)} 条")

            # 2. 创建 Realtime API 客户端
            base_url = self.azure_endpoint.replace("https://", "wss://").rstrip("/") + "/openai/v1"

            realtime_client = AsyncOpenAI(
                websocket_base_url=base_url,
                api_key=self.azure_api_key
            )

            print(f"[Realtime] 连接到: {base_url}")
            print(f"[Realtime] 部署: {self.azure_realtime_deployment}")

            # 3. 创建异步音频队列
            audio_queue = asyncio.Queue()

            # 4. 启动音频播放协程
            async def audio_player():
                """后台播放音频队列中的数据"""
                try:
                    while True:
                        audio_data = await audio_queue.get()

                        # None 表示队列结束
                        if audio_data is None:
                            break

                        # 播放音频（在 executor 中执行，避免阻塞）
                        if self.audio_stream:
                            try:
                                audio_array = np.frombuffer(audio_data, dtype=self.audio_dtype)
                                audio_array = audio_array.reshape(-1, 1)

                                # 使用 run_in_executor 在线程池中执行阻塞操作
                                loop = asyncio.get_event_loop()
                                await loop.run_in_executor(
                                    None,
                                    self.audio_stream.write,
                                    audio_array
                                )
                            except Exception as e:
                                print(f"[Realtime] 音频播放错误: {e}")

                        audio_queue.task_done()
                except Exception as e:
                    print(f"[Realtime] 音频播放器错误: {e}")

            play_task = asyncio.create_task(audio_player())

            # 5. 连接并配置 session
            async with realtime_client.realtime.connect(
                model=self.azure_realtime_deployment,
            ) as connection:
                # 配置 session（不设置 instructions，因为 Azure 可能不支持）
                await connection.session.update(session={
                    "output_modalities": ["audio"],
                    "audio": {
                        "input": {
                            "transcription": {
                                "model": "whisper-1",
                            },
                            "format": {
                                "type": "audio/pcm",
                                "rate": 24000,
                            },
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.5,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 200,
                                "create_response": True,
                            }
                        },
                        "output": {
                            "voice": self.audio_voice,
                            "format": {
                                "type": "audio/pcm",
                                "rate": 24000,
                            }
                        }
                    }
                })

                print(f"[Realtime] Session 配置完成")

                # 6. 将 system prompt 作为第一条消息添加（替代 instructions）
                print(f"[Realtime] 添加 system prompt 作为第一条消息")
                await connection.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "system",
                        "content": [{"type": "input_text", "text": current_system_prompt}],
                    }
                )

                # 7. 添加历史对话到 conversation（排除 system 消息和当前用户消息）
                history_to_add = self.conversation_history[1:-1]

                if history_to_add:
                    print(f"[Realtime] 添加 {len(history_to_add)} 条历史消息到 conversation")
                    for i, msg in enumerate(history_to_add):
                        print(f"[Realtime调试] 历史[{i}]: role={msg['role']}, content={msg['content'][:50]}...")
                        await connection.conversation.item.create(
                            item={
                                "type": "message",
                                "role": msg["role"],
                                "content": [{"type": "input_text", "text": msg["content"]}],
                            }
                        )
                else:
                    print(f"[Realtime] 无历史消息需要添加")

                # 8. 发送当前用户消息
                print(f"[Realtime] 发送用户消息: {user_message[:30]}...")
                await connection.conversation.item.create(
                    item={
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_message}],
                    }
                )
                await connection.response.create()

                # 8. 实时接收事件并放入队列
                self._update_status("🤖 AI思考中...", "processing")
                self._on_ai_response_streaming("")  # 开始新的流式响应

                full_response = ""
                audio_chunk_count = 0

                async for event in connection:
                    if event.type == "response.output_text.delta":
                        # 文本增量（通常不会有，因为output_modalities只有audio）
                        pass

                    elif event.type == "response.output_audio.delta":
                        # 音频数据块 - 放入队列，不阻塞
                        audio_data = base64.b64decode(event.delta)
                        await audio_queue.put(audio_data)

                        audio_chunk_count += 1
                        if audio_chunk_count == 1:
                            # 首次播放时更新状态
                            self._update_status("🔊 播放AI语音...", "speaking")

                    elif event.type == "response.output_audio_transcript.delta":
                        # 音频转录文本（流式）
                        delta_text = event.delta
                        full_response += delta_text
                        self._on_ai_response_streaming(delta_text)

                    elif event.type == "response.output_audio_transcript.done":
                        # 音频转录完成
                        print(f"[Realtime] 转录完成: {full_response[:50]}...")

                    elif event.type == "response.done":
                        # 响应完成
                        print(f"[Realtime] 响应完成，共接收 {audio_chunk_count} 个音频块")
                        break

            # 9. 标记音频队列结束并等待播放完成
            await audio_queue.put(None)
            await play_task
            print(f"[Realtime] 音频播放完成")

            # 10. 添加AI回复到历史（使用转录文本）
            self.conversation_history.append({
                "role": "assistant",
                "content": full_response
            })

            # 11. 检查是否触发大模型
            should_trigger_big_model = False
            if (self.enable_dual_model and
                self.dual_model_manager and
                self.dual_model_manager.check_if_trigger_big_model(full_response)):
                should_trigger_big_model = True

            # 如果触发了大模型，后台异步处理
            if should_trigger_big_model:
                print("[Realtime] 检测到触发词，启动大模型分析...")
                self._update_status("🧠 正在深度分析...", "processing")

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
                print("[Realtime] 大模型线程已启动")

            self._update_status("✓ 完成", "success")

        except Exception as e:
            self._update_status(f"❌ 错误: {str(e)}", "error")
            print(f"Realtime模式错误: {e}")
            import traceback
            traceback.print_exc()

    async def _async_llm_with_text_tts(self, user_message: str):
        """传统模式：LLM生成文本 → TTS转音频"""
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
            audio_queue = []  # 存储待播放的音频文件 (格式: {"audio_file": str, "sentence": str, "index": int})
            should_trigger_big_model = False
            sentence_counter = 0  # 句子计数器

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
                            sentence_counter += 1

                            # 流式更新显示（每生成一个句子就显示）
                            self._on_ai_response_streaming(sentence)

                            # 检测是否触发大模型
                            if (self.enable_dual_model and
                                self.dual_model_manager and
                                self.dual_model_manager.check_if_trigger_big_model(sentence)):
                                should_trigger_big_model = True

                            # 通知TTS开始转换
                            self._on_tts_progress(sentence, sentence_counter, "converting")

                            # 立即进行TTS（传入句子索引）
                            audio_file = await self._quick_tts(sentence, sentence_index=sentence_counter)
                            if audio_file:
                                # 通知TTS转换完成，等待播放
                                self._on_tts_progress(sentence, sentence_counter, "queued")
                                # 将音频文件和句子信息一起入队
                                audio_queue.append({
                                    "audio_file": audio_file,
                                    "sentence": sentence,
                                    "index": sentence_counter
                                })

                                # 首次播放时更新状态
                                if len(audio_queue) == 1:
                                    self._update_status("🔊 播放AI语音...", "speaking")

                        # 重置缓冲区（保留未完成的部分）
                        current_chunk = self._get_remaining_text(current_chunk, sentences)

            # 处理最后剩余的文本
            if current_chunk.strip():
                sentence_counter += 1
                self._on_ai_response_streaming(current_chunk.strip())

                # 通知TTS开始转换
                self._on_tts_progress(current_chunk.strip(), sentence_counter, "converting")

                audio_file = await self._quick_tts(current_chunk.strip(), sentence_index=sentence_counter)
                if audio_file:
                    # 通知TTS转换完成
                    self._on_tts_progress(current_chunk.strip(), sentence_counter, "queued")
                    # 将音频文件和句子信息一起入队
                    audio_queue.append({
                        "audio_file": audio_file,
                        "sentence": current_chunk.strip(),
                        "index": sentence_counter
                    })

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
        """播放单个音频文件（保留文件供调试）"""
        if os.path.exists(audio_file):
            play_process = await asyncio.create_subprocess_exec(
                "afplay", audio_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await play_process.communicate()
            # 不删除文件，保留供调试
            # print(f"[TTS调试] 播放完成: {os.path.basename(audio_file)}")

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

    async def _trim_audio_end(self, input_path: str, trim_ms: int) -> Optional[str]:
        """
        裁剪音频结尾的静音部分

        Args:
            input_path: 输入音频文件路径
            trim_ms: 要裁剪的毫秒数

        Returns:
            裁剪后的音频文件路径（如果成功）
        """
        try:
            # 生成输出文件路径
            base, ext = os.path.splitext(input_path)
            output_path = f"{base}_trimmed{ext}"

            # 使用ffprobe获取音频时长
            probe_process = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                input_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await probe_process.communicate()

            if probe_process.returncode != 0:
                print(f"[音频裁剪] ffprobe失败: {stderr.decode()}")
                return input_path  # 返回原始文件

            # 解析时长
            duration_str = stdout.decode().strip()
            try:
                original_duration = float(duration_str)
            except ValueError:
                print(f"[音频裁剪] 无法解析时长: {duration_str}")
                return input_path

            # 计算新时长（裁剪结尾）
            trim_seconds = trim_ms / 1000.0
            new_duration = original_duration - trim_seconds

            if new_duration <= 0:
                print(f"[音频裁剪] 音频太短，无法裁剪 ({original_duration}s < {trim_seconds}s)")
                return input_path

            # 使用ffmpeg裁剪音频
            trim_process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",  # 覆盖输出文件
                "-i", input_path,
                "-t", str(new_duration),  # 设置新时长
                "-c", "copy",  # 复制编码（快速）
                output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await trim_process.communicate()

            if trim_process.returncode == 0 and os.path.exists(output_path):
                # 删除原始文件
                os.unlink(input_path)
                print(f"[音频裁剪] 成功: {original_duration:.3f}s -> {new_duration:.3f}s (裁剪{trim_ms}ms)")
                return output_path
            else:
                print(f"[音频裁剪] ffmpeg失败: {stderr.decode()}")
                return input_path

        except Exception as e:
            print(f"[音频裁剪] 错误: {e}")
            return input_path  # 返回原始文件

    async def _quick_tts(self, text: str, sentence_index: int = 0) -> Optional[str]:
        """快速TTS（单个句子/短语）- 保存到本地供调试"""
        try:
            # 生成文件名：时间戳 + 句子索引
            timestamp = datetime.now().strftime("%H%M%S")

            if self.tts_engine == "local":
                # macOS say命令（最快）
                filename = f"sentence_{sentence_index:03d}_{timestamp}.m4a"
                audio_path = os.path.join(self.tts_audio_dir, filename)

                process = await asyncio.create_subprocess_exec(
                    "say",
                    "-v", "Tingting",
                    "-o", audio_path,
                    "--data-format=LEF32@22050",
                    text,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()

                if process.returncode == 0 and os.path.exists(audio_path):
                    print(f"[TTS调试] 已保存: {filename} | 内容: {text[:20]}...")

                    # 裁剪音频结尾静音
                    trimmed_path = await self._trim_audio_end(audio_path, self.trim_end_silence_ms)
                    return trimmed_path
                else:
                    return None

            elif self.tts_engine == "edge":
                # Edge TTS
                filename = f"sentence_{sentence_index:03d}_{timestamp}.mp3"
                audio_path = os.path.join(self.tts_audio_dir, filename)

                process = await asyncio.create_subprocess_exec(
                    "edge-tts",
                    "--voice", "zh-CN-XiaoxiaoNeural",
                    "--rate", "+10%",
                    "--pitch", "+5Hz",
                    "--text", text,
                    "--write-media", audio_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()

                if process.returncode == 0 and os.path.exists(audio_path):
                    print(f"[TTS调试] 已保存: {filename} | 内容: {text[:20]}...")

                    # 裁剪音频结尾静音
                    trimmed_path = await self._trim_audio_end(audio_path, self.trim_end_silence_ms)
                    return trimmed_path
                else:
                    return None

            else:  # openai
                # OpenAI TTS（较慢，不推荐流式使用）
                response = await self.client.audio.speech.create(
                    model="tts-1",
                    voice="nova",
                    input=text
                )

                filename = f"sentence_{sentence_index:03d}_{timestamp}.mp3"
                audio_path = os.path.join(self.tts_audio_dir, filename)

                with open(audio_path, 'wb') as f:
                    f.write(response.content)

                print(f"[TTS调试] 已保存: {filename} | 内容: {text[:20]}...")

                # 裁剪音频结尾静音
                trimmed_path = await self._trim_audio_end(audio_path, self.trim_end_silence_ms)
                return trimmed_path

        except Exception as e:
            print(f"快速TTS错误: {e}")
            return None

    async def _audio_player(self, audio_queue: list):
        """音频播放器（并发播放队列中的音频）"""
        try:
            while True:
                # 等待队列中有音频（优化：减少轮询延迟到10ms）
                while len(audio_queue) == 0:
                    await asyncio.sleep(0.01)

                # 取出音频项（可能是字典或None）
                audio_item = audio_queue.pop(0)

                # None表示队列结束
                if audio_item is None:
                    break

                # 通知开始播放
                if isinstance(audio_item, dict):
                    sentence = audio_item["sentence"]
                    index = audio_item["index"]
                    audio_file = audio_item["audio_file"]

                    # 通知UI：正在播放
                    self._on_tts_progress(sentence, index, "playing")
                else:
                    # 兼容旧格式（字符串）
                    audio_file = audio_item

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
