#!/usr/bin/env python3
"""
配置文件 - TEM模拟器配置
"""
import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI API配置
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Azure OpenAI Realtime API 配置（可选）
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")  # 例如: https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_REALTIME_DEPLOYMENT = os.getenv("AZURE_REALTIME_DEPLOYMENT", "gpt-realtime-mini")

# 自定义 API Base URL（用于第三方平台）
CUSTOM_BASE_URL = "https://yunwu.zeabur.app"  # 修改为你的平台地址，会自动添加 https:// 和 /v1

# 模型配置
SMALL_MODEL = "gpt-4o-audio-preview"  # 支持音频的小模型（快速响应）
MINI_MODEL = "gpt-4o-mini"            # 保底小模型（搭配 edge-tts）
BIG_MODEL = "gpt-4o"                  # 深度分析的大模型

# 语音交互模式
# "realtime" - 使用 Azure Realtime API（流式音频，推荐）
# "mini_tts" - 保底方案：gpt-4o-mini + edge-tts（流式文本 + 流式TTS）
# "audio"    - 使用 gpt-4o-audio-preview 直接输出音频
# "text"     - 传统模式：LLM输出文本 → TTS转音频
VOICE_MODE = "mini_tts"

# 引擎优先级（如果首选引擎不可用，自动降级）
# 1. realtime (Azure Realtime API)
# 2. mini_tts (gpt-4o-mini + edge-tts)
# 3. audio (gpt-4o-audio-preview)
ENGINE_FALLBACK_ORDER = ["realtime", "mini_tts", "audio"]

# 音频输出配置（仅在 VOICE_MODE="realtime" 或 "audio" 时有效）
AUDIO_VOICE = "alloy"  # 可选: alloy, echo, shimmer

# Mini+TTS 引擎配置（仅在 VOICE_MODE="mini_tts" 时有效）
MINI_TTS_VOICE = "zh-CN-XiaoxiaoNeural"  # edge-tts 语音（中文女声）
MINI_TTS_MAX_TOKENS = 1000               # 最大 token 数

# TTS引擎配置（仅在 VOICE_MODE="text" 时有效）
# 可选: "local" (macOS say), "edge" (Edge TTS), "openai" (OpenAI TTS)
TTS_ENGINE = "edge"

# 窗口配置
WINDOW_TITLE = "TEM双人推演模拟器 - 双模型语音交互版"
WINDOW_GEOMETRY = "1200x800"

# 双模型功能开关
ENABLE_DUAL_MODEL = True
