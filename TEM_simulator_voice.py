#!/usr/bin/env python3
"""
TEM双人推演模拟器 - 语音交互版本
整合实时语音识别、LLM对话和TTS功能
"""
import tkinter as tk
from tkinter import messagebox, scrolledtext
import os
import time
import asyncio
import tempfile
import threading
from typing import Optional, Literal
import math

import numpy as np
import sounddevice as sd
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# --- 模拟的后台数据 ---
MOCK_DATA = {
    "OFP": "飞行计划 (OFP):\n\n航线: ZSSS -> ZBAA\n预计油耗: 15.2吨\n备降场: ZBTJ\n巡航高度: FL350\n备注: 乘客中有医疗急救人员，需尽快抵达。",
    "WEATHER": "气象报告 (METAR & TAF):\n\nZSSS (出发地): 24015KT 9999 FEW030 25/18 Q1012 NOSIG\n\nZBAA (目的地): 20005KT 3000 BR SCT010 BKN020\nTAF ZBAA: ... TEMPO 0406 0500 FG BKN002\n(威胁: 目的地机场有雾，能见度可能在预计抵达时急剧下降至500米)",
    "TECH_LOG": "飞机技术日志:\n\n日期: 2025-10-26\n项目: APU（辅助动力单元）启动发电机故障\n状态: 已根据MEL 49-11-01保留\n影响: 地面无法使用APU供电和引气，必须依赖地面设备。",
    "NOTAMS": "航行通告 (NOTAMs):\n\nB3454/25 NOTAMN\nQ) ZSHA/QMRHW/IV/NBO/A/000/999/3114N12147E005\nA) ZSSS B) 2510250800 C) 2510251100\nE) RWY 17L/35R 因施工，可用起飞距离缩短400米。\n(威胁: 跑道长度缩短，需重新计算起飞性能)",
}

# --- 动态事件定义 ---
DYNAMIC_EVENT = {
    "title": "!! 紧急通知: 来自签派 !!",
    "message": "最新消息: 机上将增加一名需要担架的医疗旅客及陪同家属，总重210公斤。请立即重新计算重心和载重，并评估对起飞性能的影响。",
}


# ============================================================================
# 头像动画组件
# ============================================================================
class AvatarWidget(tk.Canvas):
    """动态头像组件 - 支持说话动画效果"""

    def __init__(self, master, name: str, emoji: str, color: str, **kwargs):
        """
        初始化头像组件

        Args:
            name: 名称（"你" 或 "AI伙伴"）
            emoji: 表情符号（"👨‍✈️" 或 "🤖"）
            color: 主题颜色
        """
        super().__init__(master, width=120, height=140, bg="white", highlightthickness=0, **kwargs)

        self.name = name
        self.emoji = emoji
        self.color = color
        self.is_speaking = False
        self.animation_frame = 0
        self.animation_job = None

        # 绘制静态元素
        self._draw_static()

    def _draw_static(self):
        """绘制静态元素（头像圆圈、名称）"""
        # 清空画布
        self.delete("all")

        # 外圈（用于动画）
        self.outer_circle = self.create_oval(
            20, 20, 100, 100,
            outline=self.color,
            width=2,
            tags="outer"
        )

        # 内圈（头像背景）
        self.inner_circle = self.create_oval(
            30, 30, 90, 90,
            fill="#f0f0f0",
            outline=self.color,
            width=2,
            tags="inner"
        )

        # 表情符号
        self.emoji_text = self.create_text(
            60, 60,
            text=self.emoji,
            font=("Arial", 32),
            tags="emoji"
        )

        # 名称
        self.name_text = self.create_text(
            60, 115,
            text=self.name,
            font=("Helvetica", 11, "bold"),
            fill="#333"
        )

        # 音量波形条（初始隐藏）
        self.wave_bars = []
        for i in range(5):
            bar = self.create_rectangle(
                15 + i * 22, 90,
                30 + i * 22, 95,
                fill=self.color,
                outline="",
                tags="wave",
                state="hidden"
            )
            self.wave_bars.append(bar)

    def start_speaking(self):
        """开始说话动画"""
        if not self.is_speaking:
            self.is_speaking = True
            self.animation_frame = 0
            self._animate()

    def stop_speaking(self):
        """停止说话动画"""
        self.is_speaking = False
        if self.animation_job:
            self.after_cancel(self.animation_job)
            self.animation_job = None

        # 恢复静态状态
        self._draw_static()

    def _animate(self):
        """动画循环"""
        if not self.is_speaking:
            return

        self.animation_frame += 1
        frame = self.animation_frame

        # 1. 外圈脉冲效果（缩放）
        scale = 1.0 + 0.1 * math.sin(frame * 0.3)
        center = 60
        radius_outer = 40 * scale
        self.coords(
            self.outer_circle,
            center - radius_outer, center - radius_outer,
            center + radius_outer, center + radius_outer
        )

        # 2. 外圈颜色变化
        color_rgb = self._hex_to_rgb(self.color)
        animated_color = f'#{color_rgb[0]:02x}{color_rgb[1]:02x}{color_rgb[2]:02x}'
        self.itemconfig(self.outer_circle, outline=animated_color, width=int(2 + 2 * math.sin(frame * 0.3)))

        # 3. 音量波形动画
        for i, bar in enumerate(self.wave_bars):
            # 每个柱子不同相位
            height = 5 + 15 * abs(math.sin(frame * 0.2 + i * 0.5))
            self.coords(
                bar,
                15 + i * 22, 95 - height,
                30 + i * 22, 95
            )
            self.itemconfig(bar, state="normal")

        # 4. 表情符号轻微跳动
        offset_y = 2 * math.sin(frame * 0.25)
        self.coords(self.emoji_text, 60, 60 + offset_y)

        # 继续动画
        self.animation_job = self.after(50, self._animate)  # 20 FPS

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """将十六进制颜色转为RGB"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


# ============================================================================
# 语音交互引擎（整合自 realtime_voice_agent_streaming.py）
# ============================================================================
class VoiceInteractionEngine:
    """语音交互引擎 - 用于TEM模拟器"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        tts_engine: Literal["local", "edge", "openai"] = "local",
        callback_on_user_text=None,
        callback_on_ai_text=None,
        callback_on_ai_text_streaming=None,
        callback_on_status=None
    ):
        """
        初始化语音交互引擎

        Args:
            callback_on_user_text: 当识别到用户语音时的回调 (user_text)
            callback_on_ai_text: 当AI生成完整回复时的回调 (ai_text)
            callback_on_ai_text_streaming: 当AI流式生成时的回调 (partial_text)
            callback_on_status: 状态更新回调 (status_text, status_type)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 OPENAI_API_KEY")

        self.client = AsyncOpenAI(api_key=self.api_key)
        self.model = model
        self.tts_engine = tts_engine

        self.callback_on_user_text = callback_on_user_text
        self.callback_on_ai_text = callback_on_ai_text
        self.callback_on_ai_text_streaming = callback_on_ai_text_streaming
        self.callback_on_status = callback_on_status

        # 录音参数
        self.sample_rate = 16000
        self.max_recording_duration = 10
        self.silence_threshold = 1.5
        self.silence_duration_to_stop = 0.02

        # 对话历史 - TEM场景专用prompt
        self.conversation_history = [
            {
                "role": "system",
                "content": """你是一名经验丰富的航空飞行员AI伙伴，正在与另一名飞行员进行TEM（威胁与差错管理）案例讨论。

重要要求：
1. 用口语化、自然的方式交流，像真实的驾驶舱对话
2. 使用航空专业术语，但保持对话流畅
3. 积极识别威胁（Threats）、差错（Errors）和不良状态（Undesired States）
4. 提供建设性的决策建议
5. 句子简短（10-20字），便于语音交流
6. 适当使用"嗯"、"好的"、"我认为"等口语化表达

示例：
❌ 书面：根据当前气象条件分析，我们需要制定备降方案。
✅ 口语：嗯，看这天气，咱们得准备好备降预案啊。

记住：简洁、专业、口语化！"""
            }
        ]

        # 用于在后台线程运行异步任务
        self.loop = None
        self.recording = False
        self.current_audio_data = []

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
        """处理用户消息（LLM对话+TTS）"""
        def run_async_processing():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.loop = loop
            loop.run_until_complete(self._async_llm_and_tts(user_message))

        thread = threading.Thread(target=run_async_processing, daemon=True)
        thread.start()

    async def _async_llm_and_tts(self, user_message: str):
        """异步LLM生成和TTS播放"""
        try:
            # 添加用户消息到历史
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })

            # 1. 开始流式LLM生成
            self._update_status("🤖 AI思考中...", "processing")

            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation_history,
                stream=True,
                temperature=0.7,
                max_tokens=300
            )

            # 2. 流式处理：边生成边TTS
            full_response = ""
            current_chunk = ""
            audio_queue = []  # 存储待播放的音频文件

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
                # 流式更新显示最后一段
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

            # 回调显示完整回复
            self._on_ai_response(full_response.strip())

            self._update_status("✓ 完成", "success")

        except Exception as e:
            self._update_status(f"❌ 错误: {str(e)}", "error")
            print(f"流式LLM+TTS错误: {e}")

    def _extract_complete_sentences(self, text: str) -> list:
        """提取完整的句子（按标点符号分割）"""
        import re
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
                if os.path.exists(audio_file):
                    play_process = await asyncio.create_subprocess_exec(
                        "afplay", audio_file,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await play_process.communicate()

                    # 播放完成后删除临时文件
                    try:
                        os.unlink(audio_file)
                    except:
                        pass

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
            import wave
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

    async def _get_llm_response(self, user_message: str) -> str:
        """获取LLM回复"""
        try:
            # 添加用户消息到历史
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })

            # 调用LLM（流式）
            full_response = ""
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation_history,
                stream=True,
                temperature=0.7,
                max_tokens=300
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    full_response += chunk.choices[0].delta.content

            # 添加AI回复到历史
            self.conversation_history.append({
                "role": "assistant",
                "content": full_response
            })

            return full_response.strip()

        except Exception as e:
            print(f"LLM错误: {e}")
            return ""

    async def _text_to_speech_and_play(self, text: str):
        """文字转语音并播放"""
        try:
            if self.tts_engine == "local":
                # macOS say命令
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
                    # 播放音频
                    play_process = await asyncio.create_subprocess_exec(
                        "afplay", temp_file.name,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await play_process.communicate()
                    os.unlink(temp_file.name)

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
                    play_process = await asyncio.create_subprocess_exec(
                        "afplay", temp_file.name,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await play_process.communicate()
                    os.unlink(temp_file.name)

            else:  # openai
                # OpenAI TTS
                response = await self.client.audio.speech.create(
                    model="tts-1",
                    voice="nova",
                    input=text
                )

                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                temp_file.write(response.content)
                temp_file.close()

                play_process = await asyncio.create_subprocess_exec(
                    "afplay", temp_file.name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await play_process.communicate()
                os.unlink(temp_file.name)

        except Exception as e:
            print(f"TTS错误: {e}")


# ============================================================================
# TEM模拟器主应用
# ============================================================================
class TEMSimulatorApp:
    """主应用控制器"""
    def __init__(self, root):
        self.root = root
        self.root.title("TEM双人推演模拟器 - 语音交互版")
        self.root.geometry("1200x800")

        self.current_phase = "INDIVIDUAL"

        # 初始化语音引擎
        self.voice_engine = None
        self._init_voice_engine()

        # --- UI 面板初始化 ---
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=3)
        self.root.grid_columnconfigure(2, weight=2)

        self.left_panel = LeftPanel(self.root, self)
        self.center_panel = CenterPanel(self.root, self)
        self.right_panel = RightPanel(self.root, self)

        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.center_panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self.right_panel.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)

    def _init_voice_engine(self):
        """初始化语音引擎"""
        try:
            self.voice_engine = VoiceInteractionEngine(
                tts_engine="edge",  # 使用edgeTTS，综合速度和质量
                callback_on_user_text=self._on_user_speech_recognized,
                callback_on_ai_text=self._on_ai_speech_generated,
                callback_on_ai_text_streaming=self._on_ai_speech_streaming,
                callback_on_status=self._on_voice_status_update
            )
            print("[语音引擎] 初始化成功")
        except Exception as e:
            print(f"[语音引擎] 初始化失败: {e}")
            messagebox.showerror("错误", f"语音引擎初始化失败：{str(e)}\n请检查.env中的OPENAI_API_KEY")

    def _on_user_speech_recognized(self, text: str):
        """用户语音识别完成的回调 - 填充到输入框"""
        # 在主线程填充输入框
        self.root.after(0, lambda: self.right_panel.fill_input_from_voice(text))

    def _on_ai_speech_streaming(self, text: str):
        """AI流式生成回调 - 实时更新显示"""
        # 在主线程流式更新对话框
        self.root.after(0, lambda: self.right_panel.append_ai_message_streaming(text))

    def _on_ai_speech_generated(self, _text: str):
        """AI回复生成完成的回调"""
        # 流式模式下不需要这个回调（已通过streaming更新）
        pass

    def _on_voice_status_update(self, status_text: str, status_type: str):
        """语音状态更新回调"""
        # 在主线程更新状态显示和头像动画
        def update_ui():
            self.right_panel.update_voice_status(status_text, status_type)

            # 控制头像动画
            if status_type == "recording":
                # 用户正在说话
                self.right_panel.user_avatar.start_speaking()
                self.right_panel.ai_avatar.stop_speaking()
            elif status_type == "speaking":
                # AI正在说话
                self.right_panel.user_avatar.stop_speaking()
                self.right_panel.ai_avatar.start_speaking()
            elif status_type in ["success", "error"]:
                # 完成或错误，停止所有动画
                self.right_panel.user_avatar.stop_speaking()
                self.right_panel.ai_avatar.stop_speaking()
                # 结束AI流式显示
                if status_type == "success":
                    self.right_panel._end_ai_streaming()

        self.root.after(0, update_ui)

    def on_voice_input_button_click(self):
        """语音输入按钮被点击"""
        if self.voice_engine:
            self.voice_engine.start_recording()
        else:
            messagebox.showwarning("警告", "语音引擎未初始化")

    def on_info_button_click(self, info_type):
        """当左侧信息按钮被点击时"""
        print(f"[事件] 用户请求查看 '{info_type}'")
        data_to_display = MOCK_DATA.get(info_type, "未找到信息。")
        self.center_panel.display_info(info_type, data_to_display)

    def start_team_discussion(self):
        """切换到双人协作阶段"""
        if self.current_phase == "INDIVIDUAL":
            print("[事件] 切换到协作讨论阶段。")

            # 1. 保存个人威胁备忘录内容
            personal_threats = self.right_panel.get_personal_threats()

            # 2. 切换到协作阶段
            self.current_phase = "COLLABORATIVE"
            self.right_panel.setup_collaborative_view()
            self.left_panel.disable_buttons()

            # 3. 在中间面板显示个人威胁总结
            self.center_panel.display_personal_threats(personal_threats)

            # 4. 3秒后注入动态事件
            self.root.after(3000, self.inject_dynamic_event)

    def inject_dynamic_event(self):
        """注入动态事件"""
        print("[事件] 注入动态事件！")
        messagebox.showwarning(DYNAMIC_EVENT["title"], DYNAMIC_EVENT["message"])


# ============================================================================
# UI面板组件
# ============================================================================
class LeftPanel(tk.Frame):
    """左侧导航栏"""
    def __init__(self, master, controller):
        super().__init__(master, bd=2, relief=tk.SUNKEN)
        self.controller = controller

        tk.Label(self, text="信息源", font=("Helvetica", 14, "bold")).pack(pady=10)

        self.buttons = {}
        info_types = {"OFP": "飞行计划", "WEATHER": "天气", "TECH_LOG": "技术日志", "NOTAMS": "航行通告"}
        for key, text in info_types.items():
            btn = tk.Button(self, text=text, command=lambda k=key: self.controller.on_info_button_click(k))
            btn.pack(fill=tk.X, padx=10, pady=5)
            self.buttons[key] = btn

    def disable_buttons(self):
        for btn in self.buttons.values():
            btn.config(state=tk.DISABLED)


class CenterPanel(tk.Frame):
    """中间信息显示区"""
    def __init__(self, master, controller):
        super().__init__(master, bd=2, relief=tk.SUNKEN)
        self.controller = controller

        self.title_label = tk.Label(self, text="请从左侧选择信息源", font=("Helvetica", 14, "bold"))
        self.title_label.pack(pady=10)

        self.text_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, font=("Helvetica", 12))
        self.text_area.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        self.text_area.config(state=tk.DISABLED)

    def display_info(self, title, content):
        self.title_label.config(text=title)
        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete('1.0', tk.END)
        self.text_area.insert(tk.END, content)
        self.text_area.config(state=tk.DISABLED)

    def display_personal_threats(self, threats_content: str):
        """显示个人威胁总结（阶段二）"""
        self.title_label.config(text="📋 个人威胁总结", fg="#FF5722")
        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete('1.0', tk.END)

        if threats_content.strip():
            self.text_area.insert(tk.END, "以下是你在个人信息收集阶段总结的潜在威胁：\n\n")
            self.text_area.insert(tk.END, "="*50 + "\n\n")
            self.text_area.insert(tk.END, threats_content)
        else:
            self.text_area.insert(tk.END, "（你在阶段一没有记录任何威胁）\n\n")
            self.text_area.insert(tk.END, "建议：在团队讨论中，可以回顾左侧信息源，识别新的威胁。")

        self.text_area.config(state=tk.DISABLED)


class RightPanel(tk.Frame):
    """右侧协作与决策区"""
    def __init__(self, master, controller):
        super().__init__(master, bd=2, relief=tk.SUNKEN)
        self.controller = controller
        self.setup_individual_view()

    def clear_panel(self):
        for widget in self.winfo_children():
            widget.destroy()

    def get_personal_threats(self) -> str:
        """获取个人威胁备忘录内容（在切换阶段前调用）"""
        if hasattr(self, 'memo_area'):
            return self.memo_area.get('1.0', tk.END).strip()
        return ""

    def setup_individual_view(self):
        """设置个人信息收集阶段的界面"""
        self.clear_panel()
        tk.Label(self, text="个人威胁备忘录", font=("Helvetica", 14, "bold")).pack(pady=10)

        self.memo_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, height=10)
        self.memo_area.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)

        tk.Button(self, text="进入团队讨论 >>", command=self.controller.start_team_discussion).pack(pady=10)

    def setup_collaborative_view(self):
        """设置双人讨论阶段的界面（带语音交互）"""
        self.clear_panel()

        # 头像显示区
        avatar_frame = tk.Frame(self, bg="white")
        avatar_frame.pack(fill=tk.X, padx=10, pady=10)

        # 用户头像（左侧）
        self.user_avatar = AvatarWidget(
            avatar_frame,
            name="你",
            emoji="👨‍✈️",
            color="#2196F3"  # 蓝色
        )
        self.user_avatar.pack(side=tk.LEFT, padx=10)

        # AI头像（右侧）
        self.ai_avatar = AvatarWidget(
            avatar_frame,
            name="AI伙伴",
            emoji="🤖",
            color="#4CAF50"  # 绿色
        )
        self.ai_avatar.pack(side=tk.RIGHT, padx=10)

        # 分隔线
        tk.Frame(self, height=2, bg="#e0e0e0").pack(fill=tk.X, padx=10, pady=5)

        # 威胁日志（缩小）
        tk.Label(self, text="团队威胁日志", font=("Helvetica", 11, "bold")).pack(pady=3)
        self.threat_log = tk.Listbox(self, height=4)
        self.threat_log.pack(fill=tk.X, padx=10, pady=3)

        # 对话区（缩小高度）
        tk.Label(self, text="团队通讯", font=("Helvetica", 11, "bold")).pack(pady=3)
        self.chat_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, height=6)
        self.chat_area.pack(fill=tk.BOTH, padx=10, pady=3)
        self.chat_area.config(state=tk.DISABLED)

        # 语音交互控制区
        voice_frame = tk.LabelFrame(self, text="🎤 语音交互", font=("Helvetica", 11, "bold"))
        voice_frame.pack(fill=tk.X, padx=10, pady=10)

        # 语音输入按钮
        self.voice_button = tk.Button(
            voice_frame,
            text="🎤 语音输入",
            font=("Helvetica", 12, "bold"),
            bg="#4CAF50",
            fg="white",
            height=2,
            command=self.controller.on_voice_input_button_click
        )
        self.voice_button.pack(fill=tk.X, padx=10, pady=5)

        # 状态显示
        self.status_label = tk.Label(
            voice_frame,
            text="点击上方按钮开始语音输入",
            font=("Helvetica", 10),
            fg="gray"
        )
        self.status_label.pack(pady=5)

        # 文字输入区
        text_input_frame = tk.Frame(voice_frame)
        text_input_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(text_input_frame, text="消息输入:", font=("Helvetica", 9)).pack(anchor=tk.W)

        entry_frame = tk.Frame(text_input_frame)
        entry_frame.pack(fill=tk.X)

        self.chat_entry = tk.Entry(entry_frame, font=("Helvetica", 10))
        self.chat_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.chat_entry.bind("<Return>", lambda _event: self.send_text_message())

        tk.Button(entry_frame, text="发送", command=self.send_text_message).pack(side=tk.RIGHT, padx=(5, 0))

    def fill_input_from_voice(self, text: str):
        """从语音识别结果填充输入框"""
        self.chat_entry.delete(0, tk.END)
        self.chat_entry.insert(0, text)
        self.chat_entry.focus_set()  # 聚焦到输入框，方便用户修改

    def send_text_message(self):
        """发送文字消息 - 触发LLM对话"""
        message = self.chat_entry.get()
        if message.strip():
            # 1. 添加用户消息到对话框
            self.add_chat_message("你", message)
            self.chat_entry.delete(0, tk.END)

            # 2. 准备接收AI流式回复
            self._start_ai_streaming()

            # 3. 触发语音引擎处理（LLM + TTS）
            if self.controller.voice_engine:
                self.controller.voice_engine.process_user_message(message)

    def _start_ai_streaming(self):
        """开始AI流式回复（初始化状态）"""
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, "AI伙伴: ")
        self.chat_area.yview(tk.END)
        self.chat_area.config(state=tk.DISABLED)
        self._ai_streaming_active = True

    def append_ai_message_streaming(self, text: str):
        """流式追加AI消息内容"""
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, text)
        self.chat_area.yview(tk.END)
        self.chat_area.config(state=tk.DISABLED)

    def _end_ai_streaming(self):
        """结束AI流式回复"""
        if hasattr(self, '_ai_streaming_active') and self._ai_streaming_active:
            self.chat_area.config(state=tk.NORMAL)
            self.chat_area.insert(tk.END, "\n")
            self.chat_area.yview(tk.END)
            self.chat_area.config(state=tk.DISABLED)
            self._ai_streaming_active = False

    def add_chat_message(self, author, message):
        """添加聊天消息"""
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, f"{author}: {message}\n")
        self.chat_area.yview(tk.END)
        self.chat_area.config(state=tk.DISABLED)

    def update_voice_status(self, status_text: str, status_type: str):
        """更新语音状态显示"""
        color_map = {
            "recording": "#FF5722",  # 红色-录音中
            "processing": "#2196F3",  # 蓝色-处理中
            "speaking": "#4CAF50",    # 绿色-播放中
            "success": "#4CAF50",     # 绿色-成功
            "error": "#F44336",       # 红色-错误
            "info": "gray"            # 灰色-信息
        }

        self.status_label.config(
            text=status_text,
            fg=color_map.get(status_type, "gray")
        )


# ============================================================================
# 主程序入口
# ============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = TEMSimulatorApp(root)
    root.mainloop()
