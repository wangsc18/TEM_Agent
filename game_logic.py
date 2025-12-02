#!/usr/bin/env python3
"""
游戏业务逻辑层 - 统一的接口供人类和AI调用
所有业务逻辑都在这里，与socketio解耦
"""
from typing import Dict, Optional, Any
from dataclasses import dataclass
from data.phase1_data import PHASE1_THREATS, EMERGENCY_QUIZ
from data.qrh_library import QRH_LIBRARY
from data.phase2_advanced import GAUGE_CONFIGS


@dataclass
class Actor:
    """操作者信息（人类或AI）"""
    username: str
    role: str  # "PF" or "PM"
    is_ai: bool = False
    sid: Optional[str] = None  # session ID，用于向特定用户发送消息


class GameLogic:
    """
    TEM训练游戏的核心业务逻辑

    设计原则：
    1. 所有方法接收room和Actor，不依赖request.sid
    2. 通过socketio参数广播结果，但不依赖Flask的全局对象
    3. 人类和AI调用相同的接口
    """

    def __init__(self, rooms: Dict, socketio, log_action_func):
        """
        初始化游戏逻辑

        Args:
            rooms: 房间状态字典（引用）
            socketio: SocketIO实例（用于广播）
            log_action_func: 日志记录函数
        """
        self.rooms = rooms
        self.socketio = socketio
        self.log_action = log_action_func

    # ==========================================
    # 通用方法
    # ==========================================

    def send_ai_message(self, room: str, message: str, actor: Actor, enable_tts: bool = True) -> bool:
        """
        AI发送聊天消息

        Args:
            room: 房间ID
            message: 消息内容
            actor: AI Actor信息
            enable_tts: 是否启用TTS语音（默认True）

        Returns:
            bool: 是否发送成功
        """
        if room not in self.rooms:
            return False

        from datetime import datetime

        # 创建消息记录
        chat_record = {
            'username': actor.username,
            'role': actor.role,
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'is_ai': True
        }

        # 保存到聊天历史
        self.rooms[room]['chat_history'].append(chat_record)
        # 限制历史记录数量
        if len(self.rooms[room]['chat_history']) > 100:
            self.rooms[room]['chat_history'] = self.rooms[room]['chat_history'][-100:]

        # 记录日志
        self.log_action(room, actor.username, actor.role, "ai_chat_message",
                       details={"message": message, "enable_tts": enable_tts},
                       phase=self.rooms[room].get('current_phase', 'unknown'))

        # 广播消息给房间内所有人
        self.socketio.emit('chat_message', {
            'username': actor.username,
            'role': actor.role,
            'message': message,
            'timestamp': chat_record['timestamp'],
            'enable_tts': enable_tts  # 新增：告知前端是否需要TTS
        }, room=room)

        return True

    def get_chat_history(self, room: str, limit: int = 20) -> list:
        """
        获取聊天历史

        Args:
            room: 房间ID
            limit: 返回最近的消息数量

        Returns:
            list: 聊天历史列表
        """
        if room not in self.rooms:
            return []

        history = self.rooms[room].get('chat_history', [])
        return history[-limit:] if len(history) > limit else history

    # ==========================================
    # Phase 1: 威胁识别与决策
    # ==========================================

    def pf_identify_threat(self, room: str, keyword: str, actor: Actor) -> bool:
        """
        PF识别威胁关键词

        Returns:
            bool: 是否识别成功
        """
        # 验证角色
        if actor.role != 'PF':
            return False

        # 检查关键词是否在威胁库中
        if keyword not in PHASE1_THREATS:
            self.log_action(room, actor.username, actor.role, "identify_invalid_threat",
                           details={"keyword": keyword},
                           phase="phase1")
            return False

        # 检查是否已处理过此威胁
        if keyword in self.rooms[room]['phase1_threats']:
            return False

        # 记录 PF 识别威胁
        self.log_action(room, actor.username, actor.role, "pf_identify_threat",
                       details={"keyword": keyword},
                       phase="phase1")

        # 获取威胁数据
        threat_data = PHASE1_THREATS[keyword]

        # 发送决策模态框（只发给PF，如果是人类）
        if not actor.is_ai and actor.sid:
            # 人类PF：显示模态框（只发送给该用户）
            self.socketio.emit('show_pf_decision_modal', {
                'keyword': keyword,
                'description': threat_data['description'],
                'options': threat_data['options']
            }, room=actor.sid)

        return True

    def pf_submit_decision(self, room: str, keyword: str, option_id: str, actor: Actor) -> bool:
        """
        PF提交决策方案（支持队列机制）

        工作流程：
        1. 将决策加入队列
        2. 如果当前没有待验证的决策，立即处理队列第一个
        3. 否则等待PM验证完成后自动处理下一个

        Returns:
            bool: 是否提交成功
        """
        # 验证角色
        if actor.role != 'PF':
            return False

        # 获取威胁数据
        threat_data = PHASE1_THREATS[keyword]

        # 找到选中的选项
        selected_option = next((opt for opt in threat_data['options'] if opt['id'] == option_id), None)

        if not selected_option:
            return False

        # 创建决策数据
        decision_data = {
            'keyword': keyword,
            'option_id': option_id,
            'option_text': selected_option['text'],
            'is_correct': selected_option.get('correct', False),
            'pf_username': actor.username,
            'sop_data': threat_data['sop_data']
        }

        # 记录 PF 决策
        self.log_action(room, actor.username, actor.role, "pf_submit_decision",
                       details={
                           "keyword": keyword,
                           "option_id": option_id,
                           "option_text": selected_option['text'],
                           "is_correct": selected_option.get('correct', False),
                           "queued": True  # 标记为加入队列
                       },
                       phase="phase1")

        # 将决策加入队列
        self.rooms[room]['pending_decisions_queue'].append(decision_data)
        print(f"[GameLogic] 决策已加入队列: {keyword}, 队列长度: {len(self.rooms[room]['pending_decisions_queue'])}")

        # 如果当前没有待验证的决策，立即处理队列的第一个
        if self.rooms[room]['pending_decision'] is None:
            self._process_next_decision_in_queue(room)

        # 通知 PF 等待 PM 验证（只通知人类PF）
        if not actor.is_ai and actor.sid:
            queue_position = len(self.rooms[room]['pending_decisions_queue'])
            self.socketio.emit('waiting_pm_verify', {
                'keyword': keyword,
                'msg': f"等待 PM 验证方案... (队列位置: {queue_position})"
            }, room=actor.sid)

        return True

    def _process_next_decision_in_queue(self, room: str):
        """
        处理队列中的下一个决策

        从队列中取出第一个决策，设置为当前待验证决策，并发送给PM
        """
        queue = self.rooms[room]['pending_decisions_queue']

        if not queue:
            print(f"[GameLogic] 决策队列为空，无需处理")
            return

        # 从队列中取出第一个决策
        decision_data = queue.pop(0)
        print(f"[GameLogic] 处理队列决策: {decision_data['keyword']}, 剩余队列: {len(queue)}")

        # 设置为当前待验证决策
        self.rooms[room]['pending_decision'] = decision_data

        # 找到 PM 并发送验证请求（只发给人类PM）
        for sid, user in self.rooms[room]['users'].items():
            if user['role'] == 'PM' and not user.get('is_ai', False):
                # 发送给人类 PM 进行验证
                self.socketio.emit('show_pm_verify_panel', {
                    'keyword': decision_data['keyword'],
                    'pf_username': decision_data['pf_username'],
                    'pf_decision': decision_data['option_text'],
                    'sop_data': decision_data['sop_data']
                }, room=sid)
                print(f"[GameLogic] 已发送验证请求给PM: {decision_data['keyword']}")
                break

    def pm_verify_decision(self, room: str, approved: bool, actor: Actor) -> bool:
        """
        PM验证PF的决策

        Args:
            room: 房间ID
            approved: True=同意, False=驳回
            actor: 操作者信息

        Returns:
            bool: 是否验证成功
        """
        # 验证角色
        if actor.role != 'PM':
            return False

        # 获取待验证的决策
        pending = self.rooms[room].get('pending_decision')
        if not pending:
            return False

        keyword = pending['keyword']
        pf_is_correct = pending['is_correct']

        # 获取威胁数据
        threat_data = PHASE1_THREATS[keyword]
        scores = threat_data['scores']

        # 计算分数和结果
        if pf_is_correct and approved:
            # PF 正确 + PM 同意 = 最佳结果
            score_change = scores['pf_correct_pm_approve']
            result = "success"
            msg = f"✅ 双方协同正确！威胁 '{keyword}' 处置得当。"
            color = "green"
        elif pf_is_correct and not approved:
            # PF 正确 + PM 驳回 = PM 判断失误
            score_change = scores['pf_correct_pm_reject']
            result = "pm_error"
            msg = f"⚠️ PM 驳回了正确方案，需要重新评估。"
            color = "orange"
        elif not pf_is_correct and approved:
            # PF 错误 + PM 同意 = 双人共同失误（严重）
            score_change = scores['pf_wrong_pm_approve']
            result = "critical_error"
            msg = f"❌ 严重：PF 方案错误且 PM 未发现，双人失误！"
            color = "red"
        else:
            # PF 错误 + PM 驳回 = PM 成功发现错误
            score_change = scores['pf_wrong_pm_reject']
            result = "pm_catch"
            msg = f"✅ PM 成功识别错误方案，威胁管理有效。"
            color = "yellow"

        # 更新分数
        self.rooms[room]['score'] += score_change

        # 记录威胁处理结果
        self.rooms[room]['phase1_threats'][keyword] = {
            'pf_decision': pending['option_text'],
            'pf_correct': pf_is_correct,
            'pm_approved': approved,
            'result': result,
            'score_change': score_change
        }

        # 清除待验证决策
        self.rooms[room]['pending_decision'] = None

        # 记录日志
        self.log_action(room, actor.username, actor.role, "pm_verify_decision",
                       details={
                           "keyword": keyword,
                           "approved": approved,
                           "pf_decision": pending['option_text'],
                           "pf_correct": pf_is_correct,
                           "result": result,
                           "score_change": score_change
                       },
                       phase="phase1")

        # 广播结果给双方
        self.socketio.emit('threat_decision_result', {
            'keyword': keyword,
            'result': result,
            'msg': msg,
            'color': color,
            'score_change': score_change
        }, room=room)

        # 更新分数显示
        self.socketio.emit('update_score', {'score': self.rooms[room]['score']}, room=room)

        # === 关键：处理队列中的下一个决策 ===
        self._process_next_decision_in_queue(room)

        return True

    def submit_quiz_answer(self, room: str, question_id: str, answer: str, actor: Actor) -> bool:
        """
        提交紧急测试题答案

        Returns:
            bool: 是否提交成功
        """
        # 验证角色
        if actor.role != 'PM':
            return False

        # 找到对应的题目
        question = next((q for q in EMERGENCY_QUIZ if q['id'] == question_id), None)
        if not question:
            return False

        # 判断答案是否正确
        correct_option = next((opt for opt in question['options'] if opt.get('correct', False)), None)
        is_correct = (answer == correct_option['id']) if correct_option else False

        # 计算分数
        score_change = 10 if is_correct else -5

        # 更新分数
        self.rooms[room]['score'] += score_change

        # 保存测试结果
        self.rooms[room]['phase1_quiz_results'].append({
            'question_id': question_id,
            'question': question['question'],
            'answer': answer,
            'correct': is_correct,
            'score_change': score_change
        })

        # 记录日志
        self.log_action(room, actor.username, actor.role, "quiz_answer_submitted",
                       details={
                           "question_id": question_id,
                           "question": question['question'],
                           "answer": answer,
                           "correct": is_correct,
                           "score_change": score_change
                       },
                       phase="phase1")

        # 广播结果
        self.socketio.emit('quiz_answer_result', {
            'question_id': question_id,
            'correct': is_correct,
            'explanation': question['explanation'],
            'score_change': score_change
        }, room=room)

        # 更新分数
        self.socketio.emit('update_score', {'score': self.rooms[room]['score']}, room=room)

        return True

    # ==========================================
    # Phase 2: 仪表监控
    # ==========================================

    def monitor_gauge(self, room: str, gauge_id: str, actor: Actor) -> Dict:
        """
        用户标记监控某个仪表

        Returns:
            Dict: 仪表监控信息（包含当前状态）
        """
        if room not in self.rooms:
            return {'success': False}

        # 添加到监控集合
        self.rooms[room]['monitored_gauges'].add(gauge_id)

        # 获取当前仪表状态
        current_value = self.rooms[room]['gauge_states'].get(gauge_id)

        # 记录日志
        self.log_action(room, actor.username, actor.role, "monitor_gauge",
                       details={
                           "gauge_id": gauge_id,
                           "gauge_name": GAUGE_CONFIGS[gauge_id]['name'],
                           "current_value": current_value
                       },
                       phase="phase2")

        # 通知前端该仪表已被标记
        self.socketio.emit('gauge_monitored', {
            'gauge_id': gauge_id,
            'msg': f"已标记监控: {GAUGE_CONFIGS[gauge_id]['name']}"
        }, room=room)

        # 返回仪表信息供AI分析
        return {
            'success': True,
            'gauge_id': gauge_id,
            'gauge_name': GAUGE_CONFIGS[gauge_id]['name'],
            'current_value': current_value,
            'gauge_config': GAUGE_CONFIGS.get(gauge_id, {})
        }

    # ==========================================
    # Phase 3: QRH检查单
    # ==========================================

    def select_qrh(self, room: str, qrh_key: str, actor: Actor) -> bool:
        """
        选择QRH检查单

        Returns:
            bool: 是否选择成功
        """
        # 检查是否已经使用过这个 QRH
        if qrh_key in self.rooms[room]['used_qrh']:
            return False

        # 更新当前阶段
        self.rooms[room]['current_phase'] = "phase3"

        # 记录使用的 QRH
        self.rooms[room]['used_qrh'].add(qrh_key)
        self.rooms[room]['current_qrh'] = qrh_key

        # 获取QRH数据
        qrh = QRH_LIBRARY.get(qrh_key)
        self.rooms[room]['checked_items'] = set()
        self.rooms[room]['active_checklist_len'] = len(qrh['items'])

        # 根据当前剧本判断对错
        current_scenario = self.rooms[room]['current_scenario']
        acceptable_qrh_list = current_scenario.get('acceptable_qrh', [])

        is_correct = (qrh_key in acceptable_qrh_list)

        if is_correct:
            self.rooms[room]['score'] += 20
            msg = f"✅ 决策正确：{qrh['title']} 是合适的应对方案"
        else:
            self.rooms[room]['score'] -= 20
            acceptable_names = [QRH_LIBRARY[k]['title'] for k in acceptable_qrh_list if k in QRH_LIBRARY]
            msg = f"❌ 决策错误：当前故障是 {current_scenario['name']}，应该选择 {' 或 '.join(acceptable_names)}"

        # 记录QRH选择
        self.log_action(room, actor.username, actor.role, "select_qrh",
                       details={
                           "selected_qrh": qrh_key,
                           "qrh_title": qrh['title'],
                           "acceptable_qrh": acceptable_qrh_list,
                           "is_correct": is_correct,
                           "score_change": 20 if is_correct else -20
                       },
                       phase="phase3")

        # 广播检查单
        self.socketio.emit('show_checklist', {
            'title': qrh['title'],
            'items': qrh['items'],
            'msg': msg
        }, room=room)

        self.socketio.emit('update_score', {'score': self.rooms[room]['score']}, room=room)

        return True

    def check_item(self, room: str, item_index: int, actor: Actor) -> bool:
        """
        完成检查单项目

        Returns:
            bool: 是否完成成功
        """
        self.rooms[room]['checked_items'].add(item_index)

        # 记录检查单项目完成
        self.log_action(room, actor.username, actor.role, "check_item",
                       details={
                           "item_index": item_index,
                           "checked_count": len(self.rooms[room]['checked_items']),
                           "total_items": self.rooms[room]['active_checklist_len']
                       },
                       phase=self.rooms[room]['current_phase'])

        # 广播完成状态
        self.socketio.emit('item_checked', {
            'index': item_index,
            'role': actor.role
        }, room=room)

        # 检查单完成后，不结束训练，只是关闭检查单面板
        if len(self.rooms[room]['checked_items']) == self.rooms[room]['active_checklist_len']:
            # 记录检查单完成
            self.log_action(room, "SYSTEM", "SYSTEM", "checklist_complete",
                           details={
                               "checked_count": len(self.rooms[room]['checked_items']),
                               "total_items": self.rooms[room]['active_checklist_len'],
                               "qrh_key": self.rooms[room].get('current_qrh')
                           },
                           phase=self.rooms[room]['current_phase'])

            # 通知前端检查单完成（不是任务完成）
            self.socketio.emit('checklist_complete', {
                'msg': "✅ 检查单完成！继续监控飞行...",
                'qrh_key': self.rooms[room].get('current_qrh')
            }, room=room)

        return True
