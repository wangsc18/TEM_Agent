#!/usr/bin/env python3
"""
Real-time Voice Interaction Agent
使用 OpenAI API 实现实时语音交互，包括性能监控
"""

import os
import time
import asyncio
import tempfile
from pathlib import Path
from typing import Optional
import wave

import numpy as np
import sounddevice as sd
from openai import AsyncOpenAI
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class PerformanceMetrics:
    """性能指标收集器"""

    def __init__(self):
        self.reset()

    def reset(self):
        """重置所有指标"""
        self.recording_time = 0.0
        self.stt_time = 0.0
        self.llm_time = 0.0
        self.tts_time = 0.0
        self.playback_time = 0.0
        self.total_time = 0.0
        self.transcribed_text = ""
        self.llm_response = ""

    def print_summary(self):
        """打印性能摘要"""
        print("\n" + "="*60)
        print("性能指标摘要")
        print("="*60)
        print(f"录音时长:        {self.recording_time:.2f}s")
        print(f"语音识别(STT):   {self.stt_time:.2f}s")
        print(f"LLM处理:         {self.llm_time:.2f}s")
        print(f"语音合成(TTS):   {self.tts_time:.2f}s")
        print(f"音频播放:        {self.playback_time:.2f}s")
        print(f"-" * 60)
        print(f"总耗时:          {self.total_time:.2f}s")
        print(f"非录音耗时:      {self.total_time - self.recording_time:.2f}s")
        print("="*60)
        if self.transcribed_text:
            print(f"\n用户: {self.transcribed_text}")
        if self.llm_response:
            print(f"助手: {self.llm_response}")
        print()


class RealtimeVoiceAgent:
    """实时语音交互Agent"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        stt_model: str = "whisper-1",
        tts_model: str = "tts-1",
        tts_voice: str = "alloy"
    ):
        """
        初始化语音交互Agent

        Args:
            api_key: OpenAI API密钥
            model: LLM模型名称
            stt_model: 语音识别模型
            tts_model: 语音合成模型
            tts_voice: TTS语音类型 (alloy, echo, fable, onyx, nova, shimmer)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 OPENAI_API_KEY，请设置环境变量或传入参数")

        self.client = AsyncOpenAI(api_key=self.api_key)
        self.model = model
        self.stt_model = stt_model
        self.tts_model = tts_model
        self.tts_voice = tts_voice

        # 对话历史
        self.conversation_history = [
            {"role": "system", "content": "你是一个友好的AI助手，请用简洁明了的方式回答用户的问题。"}
        ]

        # 录音参数
        self.sample_rate = 16000
        self.channels = 1

        # 性能指标
        self.metrics = PerformanceMetrics()

    def _get_volume_bar(self, volume: float, bar_length: int = 30) -> str:
        """
        生成音量可视化条

        Args:
            volume: 音量值（0-1）
            bar_length: 进度条长度

        Returns:
            可视化字符串
        """
        filled = int(volume * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)
        percentage = int(volume * 100)
        return f"|{bar}| {percentage}%"

    def _check_audio_quality(self, audio_data: np.ndarray) -> dict:
        """
        检查音频质量

        Args:
            audio_data: 音频数据数组

        Returns:
            包含质量指标的字典
        """
        # 计算整体音量（RMS）
        rms = np.sqrt(np.mean(audio_data ** 2))

        # 计算峰值音量
        peak = np.max(np.abs(audio_data))

        # 计算非静音比例（音量高于阈值的部分）
        voice_threshold = 0.02
        voice_ratio = np.sum(np.abs(audio_data) > voice_threshold) / len(audio_data)

        # 计算动态范围
        dynamic_range = peak / (rms + 1e-10)

        return {
            "rms": rms,
            "peak": peak,
            "voice_ratio": voice_ratio,
            "dynamic_range": dynamic_range,
            "duration": len(audio_data) / self.sample_rate
        }

    def record_audio(
        self,
        duration: float = 5.0,
        silence_threshold: float = 0.015,
        min_voice_energy: float = 0.02,
        show_volume: bool = True
    ) -> Optional[str]:
        """
        录制音频（带质量检测）

        Args:
            duration: 最大录音时长（秒）
            silence_threshold: 静音阈值
            min_voice_energy: 最小语音能量阈值
            show_volume: 是否显示实时音量

        Returns:
            临时音频文件路径，如果录音质量不合格则返回None
        """
        print(f"\n🎤 开始录音 (最长 {duration} 秒，说完后保持安静即可自动停止)...")
        if show_volume:
            print("💡 提示: 请在安静环境中对着麦克风清晰说话\n")

        start_time = time.time()
        recording = []
        silence_duration = 0
        max_silence = 1.5  # 1.5秒静音后停止
        has_speech = False  # 是否检测到有效语音
        max_volume_seen = 0.0

        def audio_callback(indata, frames, time_info, status):
            """音频回调函数"""
            if status:
                print(f"录音状态: {status}")
            recording.append(indata.copy())

        # 开始录音
        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            callback=audio_callback,
            dtype=np.float32
        ):
            chunk_duration = 0.1  # 每100ms检查一次
            chunks = int(duration / chunk_duration)

            for _ in range(chunks):
                sd.sleep(int(chunk_duration * 1000))

                # 检查最近的音频块
                if len(recording) > 0:
                    recent_chunk = recording[-1]
                    volume = np.abs(recent_chunk).mean()
                    max_volume_seen = max(max_volume_seen, volume)

                    # 显示实时音量
                    if show_volume and len(recording) % 5 == 0:  # 每0.5秒更新一次
                        normalized_volume = min(volume / 0.1, 1.0)  # 归一化到0-1
                        print(f"\r音量: {self._get_volume_bar(normalized_volume)}", end="", flush=True)

                    # 检测是否有有效语音
                    if volume > min_voice_energy:
                        has_speech = True

                    # 检测静音
                    if volume < silence_threshold:
                        silence_duration += chunk_duration
                        # 只有在检测到语音后才能通过静音停止
                        if silence_duration >= max_silence and has_speech and len(recording) > 10:
                            print("\n检测到静音，停止录音")
                            break
                    else:
                        silence_duration = 0

        if show_volume:
            print()  # 换行

        self.metrics.recording_time = time.time() - start_time

        # 合并录音数据
        if not recording:
            print("❌ 录音失败：没有录制到任何数据")
            return None

        audio_data = np.concatenate(recording, axis=0)

        # 检查音频质量
        quality = self._check_audio_quality(audio_data)

        print(f"✓ 录音完成 ({self.metrics.recording_time:.2f}s)")
        print(f"📊 音频质量检测:")
        print(f"   - 平均音量(RMS): {quality['rms']:.4f}")
        print(f"   - 峰值音量: {quality['peak']:.4f}")
        print(f"   - 语音占比: {quality['voice_ratio']*100:.1f}%")

        # 质量验证
        if quality['rms'] < 0.005:
            print("❌ 音频质量不合格：录音音量太低（可能没有说话或麦克风未工作）")
            print("   建议：")
            print("   1. 检查麦克风是否正常工作")
            print("   2. 确保在安静环境中说话")
            print("   3. 离麦克风近一些，说话声音清晰一些")
            return None

        if quality['voice_ratio'] < 0.1:
            print("⚠️  警告：录音中有效语音内容较少（可能录制了背景音）")
            print("   建议：关闭其他正在播放的音频/视频")
            return None

        if not has_speech:
            print("❌ 未检测到有效语音信号")
            return None

        print("✓ 音频质量合格")

        # 保存为临时WAV文件
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        with wave.open(temp_file.name, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            # 转换为16-bit PCM
            audio_int16 = (audio_data * 32767).astype(np.int16)
            wf.writeframes(audio_int16.tobytes())

        return temp_file.name

    async def speech_to_text(self, audio_file_path: str) -> str:
        """
        语音转文本

        Args:
            audio_file_path: 音频文件路径

        Returns:
            识别出的文本
        """
        print("🔄 正在进行语音识别...")
        start_time = time.time()

        with open(audio_file_path, "rb") as audio_file:
            transcript = await self.client.audio.transcriptions.create(
                model=self.stt_model,
                file=audio_file,
                language="zh"  # 指定中文可以提高识别准确度
            )

        self.metrics.stt_time = time.time() - start_time
        text = transcript.text
        self.metrics.transcribed_text = text

        print(f"✓ 识别完成 ({self.metrics.stt_time:.2f}s): {text}")
        return text

    async def get_llm_response(self, user_input: str) -> str:
        """
        获取LLM响应

        Args:
            user_input: 用户输入文本

        Returns:
            LLM响应文本
        """
        print("🤖 正在生成回复...")
        start_time = time.time()

        # 添加用户消息到历史
        self.conversation_history.append({"role": "user", "content": user_input})

        # 调用LLM
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=self.conversation_history,
            temperature=0.7,
            max_tokens=500
        )

        assistant_message = response.choices[0].message.content
        self.conversation_history.append({"role": "assistant", "content": assistant_message})

        self.metrics.llm_time = time.time() - start_time
        self.metrics.llm_response = assistant_message

        print(f"✓ 回复生成完成 ({self.metrics.llm_time:.2f}s)")
        return assistant_message

    async def text_to_speech(self, text: str) -> str:
        """
        文本转语音

        Args:
            text: 要转换的文本

        Returns:
            音频文件路径
        """
        print("🔊 正在合成语音...")
        start_time = time.time()

        response = await self.client.audio.speech.create(
            model=self.tts_model,
            voice=self.tts_voice,
            input=text,
            response_format="mp3"
        )

        # 保存音频文件
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_file.write(response.content)
        temp_file.close()

        self.metrics.tts_time = time.time() - start_time
        print(f"✓ 语音合成完成 ({self.metrics.tts_time:.2f}s)")

        return temp_file.name

    def play_audio(self, audio_file_path: str):
        """
        播放音频文件

        Args:
            audio_file_path: 音频文件路径
        """
        print("▶️  正在播放回复...")
        start_time = time.time()

        # 使用系统默认播放器（macOS）
        if os.system(f'afplay "{audio_file_path}"') != 0:
            print("⚠️  音频播放失败，请检查系统音频设置")

        self.metrics.playback_time = time.time() - start_time
        print(f"✓ 播放完成 ({self.metrics.playback_time:.2f}s)")

    async def process_voice_input(self, recording_duration: float = 5.0):
        """
        处理一轮语音交互

        Args:
            recording_duration: 录音时长（秒）
        """
        self.metrics.reset()
        total_start = time.time()

        audio_file = None
        response_audio = None

        try:
            # 1. 录音
            audio_file = self.record_audio(duration=recording_duration)

            # 如果录音质量不合格，返回
            if audio_file is None:
                print("\n⚠️  录音未通过质量检测，请重试")
                print("💡 提示：确保在安静环境中清晰说话，并关闭其他音频/视频播放")
                return

            # 2. 语音识别
            user_text = await self.speech_to_text(audio_file)

            if not user_text.strip():
                print("⚠️  未识别到有效语音，请重试")
                return

            # 3. LLM处理
            assistant_text = await self.get_llm_response(user_text)

            # 4. 语音合成
            response_audio = await self.text_to_speech(assistant_text)

            # 5. 播放回复
            self.play_audio(response_audio)

            # 计算总耗时
            self.metrics.total_time = time.time() - total_start

            # 打印性能指标
            self.metrics.print_summary()

        finally:
            # 清理临时文件
            if audio_file and os.path.exists(audio_file):
                os.unlink(audio_file)
            if response_audio and os.path.exists(response_audio):
                os.unlink(response_audio)

    async def run_interactive_loop(self):
        """运行交互式循环"""
        print("\n" + "="*60)
        print("实时语音交互Agent已启动")
        print("="*60)
        print("使用说明:")
        print("- 按回车键开始录音")
        print("- 对着麦克风清晰说话（会显示实时音量）")
        print("- 说完后保持安静1.5秒自动停止")
        print("- 系统会自动检测音频质量")
        print("- 输入 'quit' 或 'exit' 退出程序")
        print("\n重要提示:")
        print("⚠️  请在安静环境中使用，关闭其他音频/视频播放")
        print("⚠️  如果没有说话，系统会拒绝处理低质量录音")
        print("="*60 + "\n")

        while True:
            user_input = input("按回车开始对话 (或输入 'quit' 退出): ").strip().lower()

            if user_input in ['quit', 'exit', 'q']:
                print("\n👋 再见！")
                break

            await self.process_voice_input()


async def main():
    """主函数"""
    try:
        # 创建Agent实例
        agent = RealtimeVoiceAgent(
            model="gpt-4o-mini",  # 使用更快的模型
            tts_voice="nova"  # 可选: alloy, echo, fable, onyx, nova, shimmer
        )

        # 运行交互循环
        await agent.run_interactive_loop()

    except KeyboardInterrupt:
        print("\n\n👋 程序已中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
