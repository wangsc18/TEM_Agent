#!/usr/bin/env python3
"""
配置文件 - TEM模拟器配置
"""
import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI API配置
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 模型配置
SMALL_MODEL = "gpt-4o-mini"  # 快速响应的小模型
BIG_MODEL = "gpt-4o"          # 深度分析的大模型

# TTS引擎配置
# 可选: "local" (macOS say), "edge" (Edge TTS), "openai" (OpenAI TTS)
TTS_ENGINE = "edge"

# 窗口配置
WINDOW_TITLE = "TEM双人推演模拟器 - 双模型语音交互版"
WINDOW_GEOMETRY = "1200x800"

# 双模型功能开关
ENABLE_DUAL_MODEL = True
