import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room
import time
import random
import json
import os
from datetime import datetime

# 导入数据配置
from data.phase1_data import PHASE1_DATA, PHASE1_THREATS, EMERGENCY_QUIZ
from data.phase2_scenarios import SCENARIO_LIBRARY  # 保留作为备选
from data.phase2_advanced import (
    MULTI_EVENT_SCENARIOS,
    GAUGE_CONFIGS,
    generate_precursor_value
)
from data.qrh_library import QRH_LIBRARY

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tem_multi_scenario'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

rooms = {}

# ==========================================
# 0. 日志记录系统
# ==========================================

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def log_action(room, username, role, action, details=None, phase=None):
    """
    记录用户操作到日志文件

    Args:
        room: 房间ID
        username: 用户名
        role: 角色 (PF/PM)
        action: 操作类型 (join, tag_threat, select_qrh, check_item, etc.)
        details: 操作详情 (dict)
        phase: 当前阶段 (phase1, phase2, phase3)
    """
    if room not in rooms:
        return

    # 计算相对时间（从会话开始到现在的秒数）
    elapsed_time = 0
    if 'session_start_time' in rooms[room]:
        elapsed_time = time.time() - rooms[room]['session_start_time']

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "elapsed_time": round(elapsed_time, 3),
        "room": room,
        "username": username,
        "role": role,
        "action": action,
        "details": details or {},
        "phase": phase,
        "score": rooms[room].get('score', 0)
    }

    # 追加写入到日志文件
    log_file = rooms[room].get('log_file')
    if log_file:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

# ==========================================
# 1. 核心逻辑 - Web 路由
# ==========================================

@app.route('/')
def index():
    """主页路由 - 渲染主界面"""
    return render_template('index.html')

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)

    if room not in rooms:
        # 创建日志文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"session_{room}_{timestamp}.jsonl"
        log_filepath = os.path.join(LOG_DIR, log_filename)

        rooms[room] = {
            "users": {},
            "score": 0,
            "sim_active": False,
            "found_threats": [],
            "active_checklist_len": 0,
            "checked_items": set(),
            "ready_for_next": set(),
            "current_scenario": None,
            "log_file": log_filepath,
            "session_start_time": time.time(),
            "current_phase": "waiting",
            # Phase 1 新增状态
            "phase1_threats": {},  # 追踪每个威胁的处理状态
            "phase1_quiz_results": [],  # 存储测试题结果
            "pending_decision": None,  # 当前等待 PM 验证的决策
            # Phase 2 高级功能状态
            "event_queue": [],  # 当前场景的事件队列
            "current_event_index": -1,  # 当前处理到第几个事件
            "monitored_gauges": set(),  # 用户标记监控的仪表
            "event_detections": {},  # 记录每个事件的检测情况 {event_id: {'detected_at': 'precursor'/'alert', 'timestamp': float}}
            "gauge_states": {},  # 当前所有仪表的实时状态
            "sim_start_time": None,  # Phase 2 模拟开始时间
            "used_qrh": set()  # 已使用的 QRH 检查单
        }

        # 写入会话开始日志
        with open(log_filepath, 'w', encoding='utf-8') as f:
            session_init = {
                "event": "session_created",
                "timestamp": datetime.now().isoformat(),
                "room": room,
                "log_file": log_filename
            }
            f.write(json.dumps(session_init, ensure_ascii=False) + '\n')

    # 存储用户信息
    username = data['username']
    role = data['role']

    # === 核心修复：房间人数限制 ===
    # 检查房间是否已满（最多2人）
    if len(rooms[room]['users']) >= 2:
        # 房间已满，拒绝加入
        emit('room_full', {
            'msg': f"房间 {room} 已满（2/2人），请选择其他房间号或等待当前训练结束。",
            'room': room,
            'current_users': len(rooms[room]['users'])
        })
        return  # 不加入房间

    # 房间未满，允许加入
    rooms[room]['users'][request.sid] = {
        'username': username,
        'role': role
    }

    # 记录用户加入
    log_action(room, username, role, "user_joined",
               details={
                   "session_id": request.sid,
                   "current_user_count": len(rooms[room]['users'])
               },
               phase=rooms[room]['current_phase'])

    # 通知房间内所有人当前人数
    socketio.emit('user_count_update', {
        'count': len(rooms[room]['users']),
        'usernames': [u['username'] for u in rooms[room]['users'].values()]
    }, room=room)

    # 当第2个人加入时，启动训练
    if len(rooms[room]['users']) == 2:
        rooms[room]['current_phase'] = "phase1"
        log_action(room, "SYSTEM", "SYSTEM", "phase_started",
                   details={"phase": "phase1", "data": PHASE1_DATA},
                   phase="phase1")
        socketio.emit('start_phase_1', {"data": PHASE1_DATA}, room=room)

# --- Phase 1: 威胁识别与决策 ---
@socketio.on('pf_identify_threat')
def handle_pf_identify(data):
    """PF 点击识别威胁关键词"""
    room = data['room']
    keyword = data['keyword']

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    # 验证是否为 PF
    if user_role != 'PF':
        emit('error_msg', {'msg': "只有 PF 可以识别威胁"})
        return

    # 检查关键词是否在威胁库中
    if keyword not in PHASE1_THREATS:
        log_action(room, username, user_role, "identify_invalid_threat",
                   details={"keyword": keyword},
                   phase="phase1")
        emit('error_msg', {'msg': f"'{keyword}' 不是有效的威胁关键词"})
        return

    # 检查是否已处理过此威胁
    if keyword in rooms[room]['phase1_threats']:
        emit('error_msg', {'msg': f"威胁 '{keyword}' 已经处理过了"})
        return

    # 记录 PF 识别威胁
    log_action(room, username, user_role, "pf_identify_threat",
               details={"keyword": keyword},
               phase="phase1")

    # 获取威胁数据
    threat_data = PHASE1_THREATS[keyword]

    # 发送决策模态框给 PF
    emit('show_pf_decision_modal', {
        'keyword': keyword,
        'description': threat_data['description'],
        'options': threat_data['options']
    })


@socketio.on('pf_submit_decision')
def handle_pf_decision(data):
    """PF 提交决策方案"""
    room = data['room']
    keyword = data['keyword']
    selected_option_id = data['option_id']

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    # 验证是否为 PF
    if user_role != 'PF':
        return

    # 获取威胁数据
    threat_data = PHASE1_THREATS[keyword]

    # 找到选中的选项
    selected_option = next((opt for opt in threat_data['options'] if opt['id'] == selected_option_id), None)

    if not selected_option:
        return

    # 保存待验证的决策
    rooms[room]['pending_decision'] = {
        'keyword': keyword,
        'option_id': selected_option_id,
        'option_text': selected_option['text'],
        'is_correct': selected_option.get('correct', False),
        'pf_username': username
    }

    # 记录 PF 决策
    log_action(room, username, user_role, "pf_submit_decision",
               details={
                   "keyword": keyword,
                   "option_id": selected_option_id,
                   "option_text": selected_option['text'],
                   "is_correct": selected_option.get('correct', False)
               },
               phase="phase1")

    # 找到 PM 并发送验证请求
    pm_sid = None
    for sid, user in rooms[room]['users'].items():
        if user['role'] == 'PM':
            pm_sid = sid
            break

    if pm_sid:
        # 发送给 PM 进行验证
        socketio.emit('show_pm_verify_panel', {
            'keyword': keyword,
            'pf_username': username,
            'pf_decision': selected_option['text'],
            'sop_data': threat_data['sop_data']
        }, room=pm_sid)

        # 通知 PF 等待 PM 验证
        emit('waiting_pm_verify', {
            'keyword': keyword,
            'msg': f"等待 PM 验证方案..."
        })


@socketio.on('pm_verify_decision')
def handle_pm_verify(data):
    """PM 验证 PF 的决策"""
    room = data['room']
    approved = data['approved']  # True = 同意, False = 驳回

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    # 验证是否为 PM
    if user_role != 'PM':
        return

    # 获取待验证的决策
    pending = rooms[room].get('pending_decision')
    if not pending:
        return

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
    rooms[room]['score'] += score_change

    # 记录威胁处理结果
    rooms[room]['phase1_threats'][keyword] = {
        'pf_decision': pending['option_text'],
        'pf_correct': pf_is_correct,
        'pm_approved': approved,
        'result': result,
        'score_change': score_change
    }

    # 清除待验证决策
    rooms[room]['pending_decision'] = None

    # 记录日志
    log_action(room, username, user_role, "pm_verify_decision",
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
    socketio.emit('threat_decision_result', {
        'keyword': keyword,
        'result': result,
        'msg': msg,
        'color': color,
        'score_change': score_change
    }, room=room)

    # 更新分数显示
    socketio.emit('update_score', {'score': rooms[room]['score']}, room=room)


# --- Phase 1: 紧急预案测试 ---
@socketio.on('start_emergency_quiz')
def handle_start_quiz(data):
    """开始紧急预案测试"""
    room = data['room']

    # 记录测试开始
    log_action(room, "SYSTEM", "SYSTEM", "emergency_quiz_started",
               details={"quiz_count": len(EMERGENCY_QUIZ)},
               phase="phase1")

    # 发送测试题给双方
    socketio.emit('show_emergency_quiz', {
        'questions': EMERGENCY_QUIZ
    }, room=room)


@socketio.on('submit_quiz_answer')
def handle_quiz_answer(data):
    """提交测试题答案（PM 操作）"""
    room = data['room']
    question_id = data['question_id']
    selected_answer = data['answer']

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    # 验证是否为 PM
    if user_role != 'PM':
        emit('error_msg', {'msg': "测试题应由 PM 操作"})
        return

    # 找到对应的题目
    question = next((q for q in EMERGENCY_QUIZ if q['id'] == question_id), None)
    if not question:
        return

    # 判断答案是否正确
    correct_option = next((opt for opt in question['options'] if opt.get('correct', False)), None)
    is_correct = (selected_answer == correct_option['id']) if correct_option else False

    # 计算分数
    score_change = 10 if is_correct else -5

    # 更新分数
    rooms[room]['score'] += score_change

    # 保存测试结果
    rooms[room]['phase1_quiz_results'].append({
        'question_id': question_id,
        'question': question['question'],
        'answer': selected_answer,
        'correct': is_correct,
        'score_change': score_change
    })

    # 记录日志
    log_action(room, username, user_role, "quiz_answer_submitted",
               details={
                   "question_id": question_id,
                   "question": question['question'],
                   "answer": selected_answer,
                   "correct": is_correct,
                   "score_change": score_change
               },
               phase="phase1")

    # 广播结果
    socketio.emit('quiz_answer_result', {
        'question_id': question_id,
        'correct': is_correct,
        'explanation': question['explanation'],
        'score_change': score_change
    }, room=room)

    # 更新分数
    socketio.emit('update_score', {'score': rooms[room]['score']}, room=room)


@socketio.on('req_phase_2')
def handle_req_phase_2(data):
    room = data['room']

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    rooms[room]['ready_for_next'].add(request.sid)

    # 记录用户准备进入下一阶段
    log_action(room, username, user_role, "ready_for_phase2",
               details={"ready_count": len(rooms[room]['ready_for_next'])},
               phase="phase1")

    if len(rooms[room]['ready_for_next']) >= 2:
        start_simulation(room)
    else:
        emit('sys_msg', {'msg': "等待机组搭档确认..."}, room=room)

# --- Phase 2: 随机剧本加载 ---
def start_simulation(room):
    if not rooms[room]['sim_active']:
        rooms[room]['sim_active'] = True
        rooms[room]['current_phase'] = "phase2"

        # === 使用新的多事件场景库 ===
        scenario_key = random.choice(list(MULTI_EVENT_SCENARIOS.keys()))
        scenario_data = MULTI_EVENT_SCENARIOS[scenario_key]

        rooms[room]['current_scenario'] = {
            'key': scenario_key,
            'name': scenario_data['name'],
            'description': scenario_data['description'],
            'duration': scenario_data['duration'],
            'events': scenario_data['events'],
            'acceptable_qrh': scenario_data.get('acceptable_qrh', [])  # 可接受的检查单列表
        }

        # 初始化事件队列
        rooms[room]['event_queue'] = scenario_data['events'].copy()
        rooms[room]['current_event_index'] = -1
        rooms[room]['sim_start_time'] = time.time()

        # 初始化所有仪表状态为基准值
        for gauge_id, config in GAUGE_CONFIGS.items():
            if 'baseline' in config:
                rooms[room]['gauge_states'][gauge_id] = config['baseline']
            elif 'baseline_left' in config:  # 燃油双油箱
                rooms[room]['gauge_states'][f"{gauge_id}_left"] = config['baseline_left']
                rooms[room]['gauge_states'][f"{gauge_id}_right"] = config['baseline_right']

        scenario_name = scenario_data['name']

        # 记录剧本选择
        log_action(room, "SYSTEM", "SYSTEM", "scenario_selected",
                   details={
                       "scenario_key": scenario_key,
                       "scenario_name": scenario_name,
                       "event_count": len(scenario_data['events'])
                   },
                   phase="phase2")

        socketio.emit('sys_msg', {'msg': f"系统注入随机情景: {scenario_name}"}, room=room)
        socketio.emit('start_phase_2', {'duration': scenario_data['duration']}, room=room)
        socketio.start_background_task(run_sim_loop, room)

def run_sim_loop(room):
    """
    Phase 2 高级模拟循环
    - 支持多事件队列
    - 支持征兆检测（precursor detection）
    - 平滑仪表数值更新
    """
    if room not in rooms:
        return

    start_time = time.time()
    duration = rooms[room]['current_scenario']['duration']
    events = rooms[room]['event_queue']

    # 更新间隔（秒）
    update_interval = 0.1

    # 记录每个事件是否已触发警报
    event_alerted = {event['id']: False for event in events}

    # 记录每个事件是否已结束通知
    event_ended_notified = {event['id']: False for event in events}

    # 记录每个仪表是否正在显示征兆
    active_precursors = {}  # {gauge_id: event_id}

    while True:
        if room not in rooms:
            break

        elapsed_time = time.time() - start_time

        # 场景结束
        if elapsed_time >= duration:
            socketio.emit('sys_msg', {'msg': "场景模拟结束，进行训练总结..."}, room=room)

            # 触发最终结算
            final_score = rooms[room]['score']
            scenario_name = rooms[room]['current_scenario']['name']
            result = "Passed" if final_score > 40 else "Debrief Required"

            # 记录任务完成
            log_action(room, "SYSTEM", "SYSTEM", "mission_complete",
                       details={
                           "final_score": final_score,
                           "result": result,
                           "scenario_name": scenario_name
                       },
                       phase=rooms[room].get('current_phase', 'phase2'))

            socketio.emit('mission_complete', {
                'score': final_score,
                'result': result,
                'summary': f"情景 [{scenario_name}] 训练结束。"
            }, room=room)

            break

        # 计算进度百分比
        progress = (elapsed_time / duration) * 100

        # === 先设置所有仪表为基准值（带小幅随机波动） ===
        import random
        for gauge_id, config in GAUGE_CONFIGS.items():
            if 'baseline' in config:
                # 添加 ±1% 的随机波动，模拟正常飞行
                noise = config['baseline'] * 0.01 * random.uniform(-1, 1)
                rooms[room]['gauge_states'][gauge_id] = config['baseline'] + noise
            elif 'baseline_left' in config:  # 燃油
                # 正常消耗：每秒 0.05 加仑
                consumption = elapsed_time * 0.05
                rooms[room]['gauge_states'][f"{gauge_id}_left"] = max(0, config['baseline_left'] - consumption)
                rooms[room]['gauge_states'][f"{gauge_id}_right"] = max(0, config['baseline_right'] - consumption)

        # === 处理每个事件的征兆和警报 ===
        for event in events:
            event_id = event['id']
            precursor_start = event['precursor_start']
            alert_start = event['alert_start']
            event_end = event.get('event_end', duration)  # 事件结束时间，默认为整个场景结束
            gauge_id = event['precursor']['gauge']
            pattern = event['precursor']['pattern']

            # === 事件活跃期 (precursor_start <= t < event_end) ===
            if precursor_start <= elapsed_time < event_end:

                # === 征兆阶段 (precursor_start <= t < alert_start) ===
                if elapsed_time < alert_start:
                    # 计算从征兆开始经过的时间
                    precursor_elapsed = elapsed_time - precursor_start

                    # 生成征兆仪表数值
                    precursor_value = generate_precursor_value(gauge_id, pattern, precursor_elapsed)

                    # 覆盖该仪表的正常值为异常值
                    if pattern == "asymmetric":  # 燃油不平衡
                        rooms[room]['gauge_states'][f"{gauge_id}_left"] = precursor_value['left']
                        rooms[room]['gauge_states'][f"{gauge_id}_right"] = precursor_value['right']
                    else:
                        rooms[room]['gauge_states'][gauge_id] = precursor_value['value']

                    active_precursors[gauge_id] = event_id

                    # 检查用户是否标记了这个仪表（征兆检测）
                    if gauge_id in rooms[room]['monitored_gauges'] and event_id not in rooms[room]['event_detections']:
                        # 用户在征兆阶段发现了异常
                        rooms[room]['event_detections'][event_id] = {
                            'detected_at': 'precursor',
                            'timestamp': elapsed_time
                        }

                        # 给予征兆检测分数
                        score_gain = event['detection_score']
                        rooms[room]['score'] += score_gain

                        # 记录日志
                        log_action(room, "USER", "TEAM", "precursor_detected",
                                   details={
                                       "event_id": event_id,
                                       "event_name": event['name'],
                                       "gauge": gauge_id,
                                       "score_gain": score_gain,
                                       "elapsed_time": elapsed_time
                                   },
                                   phase="phase2")

                        # 通知前端
                        socketio.emit('precursor_detected', {
                            'event_name': event['name'],
                            'gauge': gauge_id,
                            'score': score_gain,
                            'msg': f"✅ 征兆检测：提前发现 {event['name']} 的异常征兆！"
                        }, room=room)

                        socketio.emit('update_score', {'score': rooms[room]['score']}, room=room)

                # === 警报阶段 (alert_start <= t < event_end) ===
                else:
                    # 触发警报（只触发一次）
                    if not event_alerted[event_id]:
                        event_alerted[event_id] = True

                        # 触发事件告警
                        alert = event['alert']
                        log_action(room, "SYSTEM", "SYSTEM", "event_alert",
                                   details={
                                       "event_id": event_id,
                                       "event_name": event['name'],
                                       "alert_type": alert['type'],
                                       "alert_message": alert['message']
                                   },
                                   phase="phase2")

                        socketio.emit('event_trigger', {
                            'type': alert['type'],
                            'msg': alert['message'],
                            'progress': progress
                        }, room=room)

                        # 如果用户之前没有在征兆阶段检测到，给予警报反应分数
                        if event_id not in rooms[room]['event_detections']:
                            rooms[room]['event_detections'][event_id] = {
                                'detected_at': 'alert',
                                'timestamp': elapsed_time
                            }

                            # 给予警报反应分数（较低）
                            score_gain = event['reaction_score']
                            rooms[room]['score'] += score_gain

                            log_action(room, "USER", "TEAM", "alert_reaction",
                                       details={
                                           "event_id": event_id,
                                           "event_name": event['name'],
                                           "score_gain": score_gain
                                       },
                                       phase="phase2")

                    # 警报阶段保持异常状态
                    if pattern == "asymmetric":
                        # 燃油继续不平衡
                        precursor_elapsed = elapsed_time - precursor_start
                        precursor_value = generate_precursor_value(gauge_id, pattern, precursor_elapsed)
                        rooms[room]['gauge_states'][f"{gauge_id}_left"] = precursor_value['left']
                        rooms[room]['gauge_states'][f"{gauge_id}_right"] = precursor_value['right']
                    else:
                        # 其他故障设置为严重状态
                        if gauge_id == 'oil_p':
                            rooms[room]['gauge_states'][gauge_id] = 10  # 滑油压力极低
                        elif gauge_id == 'rpm':
                            rooms[room]['gauge_states'][gauge_id] = 2100  # RPM 下降
                        elif gauge_id == 'vacuum':
                            rooms[room]['gauge_states'][gauge_id] = 3.0  # 真空压力下降
                        elif gauge_id == 'ammeter':
                            rooms[room]['gauge_states'][gauge_id] = -12  # 放电

            # === 事件结束后 (t >= event_end)：仪表恢复正常 ===
            # 不需要额外处理，因为在循环开始时已经将所有仪表重置为正常值
            elif elapsed_time >= event_end and not event_ended_notified[event_id]:
                event_ended_notified[event_id] = True

                # 记录日志
                log_action(room, "SYSTEM", "SYSTEM", "event_ended",
                           details={
                               "event_id": event_id,
                               "event_name": event['name'],
                               "elapsed_time": elapsed_time
                           },
                           phase="phase2")

                # 通知用户事件已稳定
                socketio.emit('sys_msg', {
                    'msg': f"✓ {event['name']} 已稳定，继续监控其他仪表..."
                }, room=room)

        # === 发送仪表更新 ===
        # 构建仪表数据包（包含所有仪表状态）
        flight_data = {
            'spd': rooms[room]['gauge_states'].get('spd', 105),
            'alt': rooms[room]['gauge_states'].get('alt', 5500),
            'oil_p': rooms[room]['gauge_states'].get('oil_p', 80),
            'rpm': rooms[room]['gauge_states'].get('rpm', 2400),
            'fuel_qty_left': rooms[room]['gauge_states'].get('fuel_qty_left', 25),
            'fuel_qty_right': rooms[room]['gauge_states'].get('fuel_qty_right', 25),
            'vacuum': rooms[room]['gauge_states'].get('vacuum', 5.0),
            'ammeter': rooms[room]['gauge_states'].get('ammeter', 0),
            'progress': progress
        }

        socketio.emit('flight_update', flight_data, room=room)

        socketio.sleep(update_interval)

# --- Phase 2: 仪表监控标记 ---
@socketio.on('monitor_gauge')
def handle_monitor_gauge(data):
    """用户点击仪表，标记为监控状态"""
    room = data['room']
    gauge_id = data['gauge_id']

    if room not in rooms:
        return

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    # 添加到监控集合
    rooms[room]['monitored_gauges'].add(gauge_id)

    # 记录日志
    log_action(room, username, user_role, "monitor_gauge",
               details={
                   "gauge_id": gauge_id,
                   "gauge_name": GAUGE_CONFIGS[gauge_id]['name']
               },
               phase="phase2")

    # 通知前端该仪表已被标记
    socketio.emit('gauge_monitored', {
        'gauge_id': gauge_id,
        'msg': f"已标记监控: {GAUGE_CONFIGS[gauge_id]['name']}"
    }, room=room)

# --- Phase 3: 动态决策判定 ---
@socketio.on('select_checklist')
def handle_select(data):
    room = data['room']
    selected_key = data['key']

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    # 检查是否已经使用过这个 QRH
    if selected_key in rooms[room]['used_qrh']:
        emit('error_msg', {'msg': f"该检查单已经执行过了，请选择其他应急程序"})
        return

    # 更新当前阶段
    rooms[room]['current_phase'] = "phase3"

    # 记录使用的 QRH
    rooms[room]['used_qrh'].add(selected_key)
    rooms[room]['current_qrh'] = selected_key  # 记录当前使用的 QRH

    # === 核心修改：根据当前剧本判断对错（支持多正确答案） ===
    current_scenario = rooms[room]['current_scenario']
    acceptable_qrh_list = current_scenario.get('acceptable_qrh', [])

    qrh = QRH_LIBRARY.get(selected_key)
    rooms[room]['checked_items'] = set()
    rooms[room]['active_checklist_len'] = len(qrh['items'])

    is_correct = (selected_key in acceptable_qrh_list)

    if is_correct:
        rooms[room]['score'] += 20
        msg = f"✅ 决策正确：{qrh['title']} 是合适的应对方案"
    else:
        rooms[room]['score'] -= 20  # 加重惩罚
        acceptable_names = [QRH_LIBRARY[k]['title'] for k in acceptable_qrh_list if k in QRH_LIBRARY]
        msg = f"❌ 决策错误：当前故障是 {current_scenario['name']}，应该选择 {' 或 '.join(acceptable_names)}"

    # 记录QRH选择
    log_action(room, username, user_role, "select_qrh",
               details={
                   "selected_qrh": selected_key,
                   "qrh_title": qrh['title'],
                   "acceptable_qrh": acceptable_qrh_list,
                   "is_correct": is_correct,
                   "score_change": 20 if is_correct else -20
               },
               phase="phase3")

    emit('show_checklist', {'title': qrh['title'], 'items': qrh['items'], 'msg': msg}, room=room)
    emit('update_score', {'score': rooms[room]['score']}, room=room)

@socketio.on('check_item')
def handle_check(data):
    room = data['room']
    idx = data['index']

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    rooms[room]['checked_items'].add(idx)

    # 记录检查单项目完成
    log_action(room, username, user_role, "check_item",
               details={
                   "item_index": idx,
                   "checked_count": len(rooms[room]['checked_items']),
                   "total_items": rooms[room]['active_checklist_len']
               },
               phase=rooms[room]['current_phase'])

    emit('item_checked', {'index': idx, 'role': user_role}, room=room)

    # 检查单完成后，不结束训练，只是关闭检查单面板
    if len(rooms[room]['checked_items']) == rooms[room]['active_checklist_len']:
        # 记录检查单完成
        log_action(room, "SYSTEM", "SYSTEM", "checklist_complete",
                   details={
                       "checked_count": len(rooms[room]['checked_items']),
                       "total_items": rooms[room]['active_checklist_len'],
                       "qrh_key": rooms[room].get('current_qrh')
                   },
                   phase=rooms[room]['current_phase'])

        # 通知前端检查单完成（不是任务完成）
        socketio.emit('checklist_complete', {
            'msg': "✅ 检查单完成！继续监控飞行...",
            'qrh_key': rooms[room].get('current_qrh')  # 传递完成的 QRH key，用于清除对应告警
        }, room=room)

# --- 用户断开连接处理 ---
@socketio.on('disconnect')
def on_disconnect():
    """处理用户断开连接"""
    # 查找用户所在的房间
    for room_id, room_data in rooms.items():
        if request.sid in room_data['users']:
            user_info = room_data['users'][request.sid]
            username = user_info['username']
            role = user_info['role']

            # 记录用户离开
            log_action(room_id, username, role, "user_left",
                       details={"session_id": request.sid},
                       phase=room_data.get('current_phase', 'unknown'))

            # 从房间中移除用户
            del room_data['users'][request.sid]

            # 通知房间内剩余用户
            socketio.emit('user_left', {
                'username': username,
                'role': role,
                'remaining_count': len(room_data['users'])
            }, room=room_id)

            # 如果房间为空，可以选择清理房间数据（可选）
            if len(room_data['users']) == 0:
                log_action(room_id, "SYSTEM", "SYSTEM", "room_empty",
                           details={"reason": "all_users_left"},
                           phase="end")

            break

if __name__ == '__main__':
    print("启动服务器: http://0.0.0.0:5001")
    # 将 5000 改为 5001
    socketio.run(app, debug=True, use_reloader=False, allow_unsafe_werkzeug=True, host='0.0.0.0', port=5001)