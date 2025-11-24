#!/usr/bin/env python3
"""
工具函数集

提供LLM响应解析、随机延迟等辅助功能
"""
import random
import json
import re
from typing import Optional, Dict, List


def random_delay(min_sec: float, max_sec: float) -> float:
    """
    生成随机延迟

    Args:
        min_sec: 最小延迟（秒）
        max_sec: 最大延迟（秒）

    Returns:
        float: 随机延迟时间
    """
    return random.uniform(min_sec, max_sec)


def extract_threat_keyword(llm_response: str, source_text: str) -> Optional[str]:
    """
    从LLM响应中提取威胁关键词

    Args:
        llm_response: LLM返回的文本
        source_text: 原始数据文本

    Returns:
        Optional[str]: 威胁关键词
    """
    from data.phase1_data import PHASE1_THREATS

    # 优先在响应中查找
    for keyword in PHASE1_THREATS.keys():
        if keyword in llm_response or keyword in source_text:
            return keyword

    # 降级：返回第一个威胁
    return list(PHASE1_THREATS.keys())[0] if PHASE1_THREATS else None


def extract_option_id(llm_response: str, options: List[Dict]) -> str:
    """
    从LLM响应中提取选项ID

    Args:
        llm_response: LLM返回的文本
        options: 选项列表

    Returns:
        str: 选项ID
    """
    response_lower = llm_response.lower()

    for opt in options:
        if opt['id'] in response_lower:
            return opt['id']

    # 降级：返回第一个选项
    return options[0]['id']


def extract_quiz_answer(llm_response: str, options: List[Dict]) -> str:
    """
    从LLM响应中提取测试题答案

    Args:
        llm_response: LLM返回的文本
        options: 选项列表

    Returns:
        str: 答案ID
    """
    response_lower = llm_response.lower()

    for opt in options:
        if opt['id'] in response_lower:
            return opt['id']

    return options[0]['id']


def extract_qrh_key(llm_response: str) -> Optional[str]:
    """
    从LLM响应中提取QRH键名

    Args:
        llm_response: LLM返回的文本

    Returns:
        Optional[str]: QRH键名
    """
    from data.qrh_library import QRH_LIBRARY

    response_upper = llm_response.upper()

    for key, qrh in QRH_LIBRARY.items():
        if key in llm_response.lower() or qrh['title'] in response_upper:
            return key

    # 降级：返回第一个QRH
    return list(QRH_LIBRARY.keys())[0] if QRH_LIBRARY else None


def parse_approval(llm_response: str) -> bool:
    """
    解析同意/驳回

    Args:
        llm_response: LLM返回的文本

    Returns:
        bool: True=同意, False=驳回
    """
    response_lower = llm_response.lower()

    keywords_approve = ['同意', '正确', '合理', 'approve', 'yes', 'true', '符合']
    keywords_reject = ['驳回', '错误', '不合理', 'reject', 'no', 'false', '不符合']

    for kw in keywords_reject:
        if kw in response_lower:
            return False

    for kw in keywords_approve:
        if kw in response_lower:
            return True

    # 默认同意
    return True


def parse_json_response(llm_response: str) -> Dict:
    """
    解析JSON响应

    Args:
        llm_response: LLM返回的文本

    Returns:
        Dict: 解析后的字典
    """
    try:
        # 尝试直接解析
        return json.loads(llm_response)
    except:
        # 尝试提取JSON块
        match = re.search(r'\{.*\}', llm_response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass

    # 降级：返回空字典
    return {}


def detect_abnormal_gauges(gauge_states: Dict) -> List[str]:
    """
    快速规则检测异常仪表（不使用LLM）

    Args:
        gauge_states: 仪表状态字典

    Returns:
        List[str]: 异常仪表ID列表
    """
    abnormal = []

    # 简单阈值判断
    if gauge_states.get('oil_p', 80) < 60:
        abnormal.append('oil_p')
    if gauge_states.get('rpm', 2400) < 2300:
        abnormal.append('rpm')
    if gauge_states.get('vacuum', 5.0) < 4.0:
        abnormal.append('vacuum')
    if gauge_states.get('ammeter', 0) < -5:
        abnormal.append('ammeter')

    # 燃油不平衡检测
    left = gauge_states.get('fuel_qty_left', 25)
    right = gauge_states.get('fuel_qty_right', 25)
    if abs(left - right) > 10:
        abnormal.append('fuel_qty')

    return abnormal
