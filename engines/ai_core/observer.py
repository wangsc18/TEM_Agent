#!/usr/bin/env python3
"""
观察层 - 提取当前状态（不用LLM）

负责从游戏状态中提取关键信息，不进行任何推理或决策
"""
from typing import Dict
from .models import Observation


class StateObserver:
    """状态观察器 - 纯数据提取，无LLM调用"""

    def __init__(self, role: str):
        """
        初始化观察器

        Args:
            role: AI角色 (PF or PM)
        """
        self.role = role

    def observe(self, room_state: Dict) -> Observation:
        """
        观察当前状态，提取关键信息

        Args:
            room_state: 房间状态字典

        Returns:
            Observation: 观察结果
        """
        phase = room_state.get('current_phase', 'waiting')

        # 根据不同阶段提取不同的上下文
        if phase == 'phase1':
            context = self._observe_phase1(room_state)
        elif phase == 'phase2':
            context = self._observe_phase2(room_state)
        elif phase == 'phase3':
            context = self._observe_phase3(room_state)
        else:
            context = {"status": "waiting"}

        return Observation(phase=phase, role=self.role, context=context)

    def _observe_phase1(self, room_state: Dict) -> Dict:
        """
        Phase 1 观察：威胁识别与决策

        Args:
            room_state: 房间状态

        Returns:
            Dict: Phase 1 上下文信息
        """
        return {
            "phase1_data_available": room_state.get('phase1_data_loaded', False),
            "identified_threats": list(room_state.get('phase1_threats', {}).keys()),
            "pending_decision": room_state.get('pending_decision'),
            "quiz_started": len(room_state.get('phase1_quiz_results', [])) > 0,
            "all_threats_handled": len(room_state.get('phase1_threats', {})) >= 3,
        }

    def _observe_phase2(self, room_state: Dict) -> Dict:
        """
        Phase 2 观察：飞行监控

        Args:
            room_state: 房间状态

        Returns:
            Dict: Phase 2 上下文信息
        """
        return {
            "sim_active": room_state.get('sim_active', False),
            "gauge_states": room_state.get('gauge_states', {}),
            "monitored_gauges": list(room_state.get('monitored_gauges', set())),
            "event_detections": room_state.get('event_detections', {}),
            "current_event_index": room_state.get('current_event_index', -1),
        }

    def _observe_phase3(self, room_state: Dict) -> Dict:
        """
        Phase 3 观察：QRH检查单

        Args:
            room_state: 房间状态

        Returns:
            Dict: Phase 3 上下文信息
        """
        return {
            "used_qrh": list(room_state.get('used_qrh', set())),
            "current_qrh": room_state.get('current_qrh'),
            "checked_items": list(room_state.get('checked_items', set())),
            "active_checklist_len": room_state.get('active_checklist_len', 0),
        }
