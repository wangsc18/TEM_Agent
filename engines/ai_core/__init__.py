#!/usr/bin/env python3
"""
AI核心模块 - 观察→策略→动作架构

提供统一的AI决策接口
"""

# 数据结构
from .models import Observation, Strategy, Action

# 各层组件
from .observer import StateObserver
from .strategies import StrategyGenerator
from .executors import ActionExecutor

# 工具函数
from .utils import (
    random_delay,
    extract_threat_keyword,
    extract_option_id,
    extract_quiz_answer,
    extract_qrh_key,
    parse_approval,
    parse_json_response,
    detect_abnormal_gauges
)

__all__ = [
    # 数据结构
    'Observation',
    'Strategy',
    'Action',
    
    # 核心组件
    'StateObserver',
    'StrategyGenerator',
    'ActionExecutor',
    
    # 工具函数
    'random_delay',
    'extract_threat_keyword',
    'extract_option_id',
    'extract_quiz_answer',
    'extract_qrh_key',
    'parse_approval',
    'parse_json_response',
    'detect_abnormal_gauges',
]
