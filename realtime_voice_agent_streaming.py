#!/usr/bin/env python3
"""
Real-time Voice Interaction Agent - Ultra-Fast Streaming Version
超快速流式版本：激进分块 + 本地TTS
"""

import os
import time
import asyncio
import tempfile
import subprocess
from typing import Optional, AsyncIterator, Literal
import wave
import re

import numpy as np
import sounddevice as sd
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()


class UltraFastMetrics:
    """超快速性能指标"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.recording_time = 0.0
        self.stt_time = 0.0
        self.llm_first_token_time = 0.0
        self.first_chunk_tts_time = 0.0
        self.first_audio_play_time = 0.0
        self.total_time = 0.0
        self.transcribed_text = ""
        self.llm_response = ""
        self.chunk_count = 0
        self.chunk_times = []

    def print_summary(self):
        print("\n" + "="*60)
        print("超快速流式 - 性能指标")
        print("="*60)
        print(f"录音:                {self.recording_time:.2f}s")
        print(f"STT:                 {self.stt_time:.2f}s")
        print(f"⚡ 首个token:        {self.llm_first_token_time:.2f}s")
        print(f"⚡ 首块TTS:          {self.first_chunk_tts_time:.2f}s")
        print(f"⚡ 首次播放:         {self.first_audio_play_time:.2f}s (关键)")
        print(f"总耗时:              {self.total_time:.2f}s")
        print(f"处理文本块数:        {self.chunk_count}")
        if self.chunk_times:
            avg = sum(self.chunk_times) / len(self.chunk_times)
            print(f"平均每块耗时:        {avg:.2f}s")
        print("="*60)
        if self.transcribed_text:
            print(f"\n用户: {self.transcribed_text}")
        if self.llm_response:
            print(f"助手: {self.llm_response}")
        print()


class UltraFastVoiceAgent:
    """超快速语音交互Agent"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        stt_model: str = "whisper-1",
        tts_engine: Literal["local", "edge", "openai"] = "local",
        tts_voice: str = "nova"
    ):
        """
        初始化超快速语音交互Agent

        Args:
            tts_engine: TTS引擎选择
                - "local": macOS say命令（最快，~0.1s）
                - "edge": edge-tts（快，~0.5s，需要安装）
                - "openai": OpenAI TTS（慢，~2s，质量最好）
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 OPENAI_API_KEY")

        self.client = AsyncOpenAI(api_key=self.api_key)
        self.model = model
        self.stt_model = stt_model
        self.tts_engine = tts_engine
        self.tts_voice = tts_voice

        self.conversation_history = [
            {
                "role": "system",
                "content": """你是一个友好、自然的AI语音助手。

重要要求：
1. 用口语化的方式说话，就像朋友聊天一样
2. 多用"嗯"、"啊"、"呢"、"哦"等语气词，让对话更自然
3. 句子要短，每句话10-20个字
4. 避免使用书面语，用日常口语
5. 可以适当重复或停顿，就像真人说话
6. 表达情感，比如"太棒了"、"我明白了"、"让我想想"

示例：
❌ 书面：我可以为您提供相关信息。
✅ 口语：好的，我来帮你看看啊。

❌ 书面：关于这个问题，有以下几点需要说明。
✅ 口语：嗯，这个问题呢，我觉得是这样的。

记住：简短、口语、自然！"""
            }
        ]

        self.sample_rate = 16000
        self.channels = 1
        self.metrics = UltraFastMetrics()
        self.audio_queue = asyncio.Queue()
        self.playback_active = False

        # 验证TTS引擎
        self._check_tts_engine()

    def _check_tts_engine(self):
        """检查TTS引擎是否可用"""
        if self.tts_engine == "local":
            # 检查macOS say命令
            result = subprocess.run(["which", "say"], capture_output=True)
            if result.returncode != 0:
                print("⚠️  警告: 未找到macOS say命令，将使用OpenAI TTS")
                self.tts_engine = "openai"
            else:
                print("✓ 使用本地TTS (macOS say) - 超低延迟")

        elif self.tts_engine == "edge":
            # 检查edge-tts
            result = subprocess.run(["which", "edge-tts"], capture_output=True)
            if result.returncode != 0:
                print("⚠️  警告: 未安装edge-tts，将使用OpenAI TTS")
                print("   安装: pip install edge-tts")
                self.tts_engine = "openai"
            else:
                print("✓ 使用Edge TTS - 快速且高质量")

        elif self.tts_engine == "openai":
            print("✓ 使用OpenAI TTS - 最高质量但较慢")

    def _get_volume_bar(self, volume: float, bar_length: int = 30) -> str:
        filled = int(volume * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)
        percentage = int(volume * 100)
        return f"|{bar}| {percentage}%"

    def record_audio(
        self,
        duration: float = 5.0,
        silence_threshold: float = 0.015,
        min_voice_energy: float = 0.02,
        show_volume: bool = True
    ) -> Optional[str]:
        """录制音频（简化版）"""
        print(f"\n🎤 录音中...")

        start_time = time.time()
        recording = []
        silence_duration = 0
        max_silence = 1.5
        has_speech = False

        def audio_callback(indata, frames, time_info, status):
            recording.append(indata.copy())

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            callback=audio_callback,
            dtype=np.float32
        ):
            chunk_duration = 0.1
            chunks = int(duration / chunk_duration)

            for _ in range(chunks):
                sd.sleep(int(chunk_duration * 1000))

                if len(recording) > 0:
                    recent_chunk = recording[-1]
                    volume = np.abs(recent_chunk).mean()

                    if show_volume and len(recording) % 5 == 0:
                        normalized_volume = min(volume / 0.1, 1.0)
                        print(f"\r{self._get_volume_bar(normalized_volume)}", end="", flush=True)

                    if volume > min_voice_energy:
                        has_speech = True

                    if volume < silence_threshold:
                        silence_duration += chunk_duration
                        if silence_duration >= max_silence and has_speech and len(recording) > 10:
                            break
                    else:
                        silence_duration = 0

        if show_volume:
            print()

        self.metrics.recording_time = time.time() - start_time

        if not recording or not has_speech:
            print("❌ 录音失败")
            return None

        audio_data = np.concatenate(recording, axis=0)
        rms = np.sqrt(np.mean(audio_data ** 2))

        if rms < 0.005:
            print("❌ 音量太低")
            return None

        print(f"✓ 录音完成 ({self.metrics.recording_time:.2f}s)")

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        with wave.open(temp_file.name, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            audio_int16 = (audio_data * 32767).astype(np.int16)
            wf.writeframes(audio_int16.tobytes())

        return temp_file.name

    async def speech_to_text(self, audio_file_path: str) -> str:
        """语音转文本"""
        print("🔄 识别中...")
        start_time = time.time()

        with open(audio_file_path, "rb") as audio_file:
            transcript = await self.client.audio.transcriptions.create(
                model=self.stt_model,
                file=audio_file,
                language="zh"
            )

        self.metrics.stt_time = time.time() - start_time
        text = transcript.text
        self.metrics.transcribed_text = text

        print(f"✓ 识别: {text}")
        return text

    def _chunk_text_aggressively(self, text: str, max_chars: int = 20) -> list[str]:
        """
        激进的文本分块策略
        每10-20个字就分一块，不等完整句子

        Args:
            text: 输入文本
            max_chars: 每块最大字符数

        Returns:
            文本块列表
        """
        chunks = []
        current_chunk = ""

        # 按字符和标点分块
        for char in text:
            current_chunk += char

            # 遇到标点或达到最大长度就分块
            is_punctuation = char in '，。！？、；：,. !?;:\n'
            is_max_length = len(current_chunk) >= max_chars

            if (is_punctuation or is_max_length) and len(current_chunk.strip()) > 3:
                chunks.append(current_chunk.strip())
                current_chunk = ""

        # 添加剩余部分
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks

    async def stream_llm_response(self, user_input: str) -> AsyncIterator[str]:
        """流式获取LLM响应"""
        print("🤖 生成中...")

        self.conversation_history.append({"role": "user", "content": user_input})

        llm_start = time.time()
        first_token = True
        full_response = ""

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=self.conversation_history,
            temperature=0.7,
            max_tokens=300,  # 限制长度，鼓励简短回复
            stream=True
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content

                if first_token:
                    self.metrics.llm_first_token_time = time.time() - llm_start
                    print(f"⚡ 首token: {self.metrics.llm_first_token_time:.2f}s")
                    first_token = False

                full_response += content
                yield content

        self.metrics.llm_response = full_response
        self.conversation_history.append({"role": "assistant", "content": full_response})

    async def text_to_speech_local(self, text: str) -> str:
        """本地TTS (macOS say命令) - 超快"""
        # 使用.m4a格式更兼容
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".m4a")
        temp_file.close()

        try:
            # 使用macOS say命令
            # -v Tingting 中文女声（注意：无连字符）
            # --data-format=LEF32@22050 使用兼容格式
            process = await asyncio.create_subprocess_exec(
                "say",
                "-v", "Tingting",  # 中文语音（婷婷）
                "-o", temp_file.name,
                "--data-format=LEF32@22050",  # 指定格式
                text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()

            # 检查是否成功
            if process.returncode != 0:
                print(f"⚠️  say命令错误: {stderr.decode()}")
                # 清理失败的文件
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                return None

            # 确保文件存在
            if not os.path.exists(temp_file.name):
                print(f"⚠️  音频文件未生成")
                return None

            return temp_file.name

        except Exception as e:
            print(f"⚠️  本地TTS错误: {e}")
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            return None

    async def text_to_speech_edge(self, text: str) -> str:
        """Edge TTS - 快速且高质量"""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_file.close()

        try:
            # 使用edge-tts，添加语速和音调参数让语音更自然
            # zh-CN-XiaoxiaoNeural - 女声（温柔自然）
            # zh-CN-YunxiNeural - 男声（更有活力）
            # --rate +10% 稍快一点（更接近真人说话）
            # --pitch +5Hz 稍微提高音调（更有情感）
            process = await asyncio.create_subprocess_exec(
                "edge-tts",
                "--voice", "zh-CN-XiaoxiaoNeural",  # 可选: YunxiNeural (男声)
                "--rate", "+10%",  # 语速加快10%
                "--pitch", "+5Hz",  # 音调提高5Hz
                "--text", text,
                "--write-media", temp_file.name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()

            # 检查是否成功
            if process.returncode != 0:
                print(f"⚠️  Edge TTS错误: {stderr.decode()}")
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
                return None

            if not os.path.exists(temp_file.name):
                print(f"⚠️  音频文件未生成")
                return None

            return temp_file.name

        except Exception as e:
            print(f"⚠️  Edge TTS错误: {e}")
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            return None

    async def text_to_speech_openai(self, text: str) -> str:
        """OpenAI TTS - 高质量但较慢"""
        response = await self.client.audio.speech.create(
            model="tts-1",  # 使用更快的模型
            voice=self.tts_voice,
            input=text,
            response_format="mp3"
        )

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_file.write(response.content)
        temp_file.close()

        return temp_file.name

    async def text_to_speech(self, text: str) -> Optional[str]:
        """根据配置选择TTS引擎"""
        if self.tts_engine == "local":
            return await self.text_to_speech_local(text)
        elif self.tts_engine == "edge":
            return await self.text_to_speech_edge(text)
        else:
            return await self.text_to_speech_openai(text)

    def play_audio_sync(self, audio_file_path: str):
        """同步播放音频"""
        try:
            result = os.system(f'afplay "{audio_file_path}"')
            if result != 0:
                print(f"⚠️  播放失败: {audio_file_path}")
        except Exception as e:
            print(f"⚠️  播放错误: {e}")

    async def audio_player_worker(self):
        """音频播放工作线程"""
        while self.playback_active:
            try:
                audio_file = await asyncio.wait_for(self.audio_queue.get(), timeout=0.5)

                if audio_file is None:  # 结束信号
                    break

                # 检查文件是否有效
                if audio_file and os.path.exists(audio_file):
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, self.play_audio_sync, audio_file)

                    # 播放完成后删除
                    try:
                        os.unlink(audio_file)
                    except:
                        pass

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"⚠️  播放队列错误: {e}")

    async def process_ultra_fast_voice_input(self, recording_duration: float = 5.0):
        """超快速语音交互处理"""
        self.metrics.reset()
        total_start = time.time()

        audio_file = None

        try:
            # 1. 录音
            audio_file = self.record_audio(duration=recording_duration)
            if audio_file is None:
                return

            # 2. STT
            user_text = await self.speech_to_text(audio_file)
            if not user_text.strip():
                return

            # 3. 启动播放线程
            self.playback_active = True
            player_task = asyncio.create_task(self.audio_player_worker())

            # 4. 流式LLM + 激进分块TTS
            buffer = ""
            chunk_index = 0
            first_audio_played = False

            print("\n" + "-"*40)

            async for token in self.stream_llm_response(user_text):
                buffer += token
                print(token, end="", flush=True)

                # 激进分块策略：每15-20个字符就处理一次
                chunks = self._chunk_text_aggressively(buffer, max_chars=20)

                # 处理除最后一个之外的所有块（最后一个可能不完整）
                for i in range(len(chunks) - 1):
                    chunk = chunks[i]
                    if len(chunk) > 2:  # 至少3个字符才处理
                        chunk_start = time.time()

                        if chunk_index == 0:
                            tts_start = time.time()

                        # TTS转换
                        audio_file_path = await self.text_to_speech(chunk)

                        # 跳过失败的TTS
                        if audio_file_path is None:
                            continue

                        if chunk_index == 0:
                            self.metrics.first_chunk_tts_time = time.time() - tts_start
                            print(f"\n⚡ 首块TTS: {self.metrics.first_chunk_tts_time:.2f}s")

                        # 加入播放队列
                        await self.audio_queue.put(audio_file_path)

                        if not first_audio_played:
                            self.metrics.first_audio_play_time = time.time() - total_start
                            print(f"⚡ 首次播放: {self.metrics.first_audio_play_time:.2f}s")
                            first_audio_played = True

                        chunk_time = time.time() - chunk_start
                        self.metrics.chunk_times.append(chunk_time)
                        chunk_index += 1

                # 保留最后一个可能不完整的块
                buffer = chunks[-1] if chunks else ""

            print("\n" + "-"*40)

            # 处理剩余buffer
            if buffer.strip() and len(buffer.strip()) > 2:
                audio_file_path = await self.text_to_speech(buffer.strip())

                if audio_file_path is not None:
                    await self.audio_queue.put(audio_file_path)

                    if not first_audio_played:
                        self.metrics.first_audio_play_time = time.time() - total_start

                    chunk_index += 1

            self.metrics.chunk_count = chunk_index

            # 发送结束信号
            await self.audio_queue.put(None)
            await player_task

            self.metrics.total_time = time.time() - total_start
            self.metrics.print_summary()

        finally:
            if audio_file and os.path.exists(audio_file):
                os.unlink(audio_file)
            self.playback_active = False

    async def run_interactive_loop(self):
        """运行交互式循环"""
        print("\n" + "="*60)
        print("超快速实时语音交互Agent")
        print("="*60)
        print(f"TTS引擎: {self.tts_engine.upper()}")
        print("特性:")
        print("✨ 激进文本分块 - 每10-20字一块")
        print(f"✨ {'本地' if self.tts_engine == 'local' else '快速'}TTS - 极低延迟")
        print("✨ 边生成边播放 - 接近实时")
        print("="*60 + "\n")

        while True:
            user_input = input("按回车开始 (quit退出): ").strip().lower()

            if user_input in ['quit', 'exit', 'q']:
                print("\n👋 再见！")
                break

            await self.process_ultra_fast_voice_input()


async def main():
    """主函数"""
    try:
        # 创建超快速agent
        # tts_engine可选: "local", "edge", "openai"
        agent = UltraFastVoiceAgent(
            model="gpt-4o-mini",
            tts_engine="edge",  # 使用本地TTS获得最快速度
            tts_voice="nova"
        )

        await agent.run_interactive_loop()

    except KeyboardInterrupt:
        print("\n\n👋 程序已中断")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
