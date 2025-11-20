import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room
import time
import random
import json
import os
from datetime import datetime

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
# 1. 基础配置
# ==========================================

# Phase 1 数据 (通用)
PHASE1_DATA = [
    {"label": "METAR", "content": "CYXH 211800Z 24015G25KT 15SM FEW030", "threats": ["24015G25KT", "FEW030"]},
    {"label": "Aircraft", "content": "C-GABC Fuel: Full Snags: Landing_Light_U/S", "threats": ["Landing_Light_U/S"]},
    {"label": "Pilot", "content": "Pilot_A: Rest_8hrs Pilot_B: Recovering_from_Cold", "threats": ["Recovering_from_Cold"]}
]

# === 新增：剧本库 (Scenario Library) ===
SCENARIO_LIBRARY = {
    "oil_loss": {
        "name": "滑油压力丧失",
        "target_qrh": "low_oil_pressure", # 正确答案的 Key
        "events": [
            (0,  {"spd": 100, "alt": 5500, "oil_p": 80, "progress": 0},  "normal", "Takeoff"),
            (15, {"spd": 105, "alt": 5500, "oil_p": 60, "progress": 25}, "warning", "Oil Pressure Dropping"),
            (30, {"spd": 105, "alt": 5450, "oil_p": 0,  "progress": 50}, "failure", "OIL PRESSURE LOST"),
            (60, {"spd": 80,  "alt": 4000, "oil_p": 0,  "progress": 100}, "end", "End")
        ]
    },
    "engine_fire": {
        "name": "空中引擎起火",
        "target_qrh": "engine_fire",
        "events": [
            (0,  {"spd": 100, "alt": 5500, "oil_p": 80, "progress": 0},  "normal", "Takeoff"),
            (10, {"spd": 105, "alt": 5500, "oil_p": 85, "progress": 15}, "normal", "Cruise"),
            (20, {"spd": 105, "alt": 5500, "oil_p": 95, "progress": 30}, "warning", "High Oil Temp Detected"),
            (25, {"spd": 105, "alt": 5500, "oil_p": 0,  "progress": 40}, "failure", "FIRE! SMOKE IN COCKPIT!"),
            (60, {"spd": 120, "alt": 3000, "oil_p": 0,  "progress": 100}, "end", "Emergency Descent")
        ]
    },
    "elec_fire": {
        "name": "电气火灾",
        "target_qrh": "electrical_fire",
        "events": [
            (0,  {"spd": 100, "alt": 5500, "oil_p": 80, "progress": 0},  "normal", "Takeoff"),
            (15, {"spd": 105, "alt": 5500, "oil_p": 80, "progress": 25}, "warning", "Acrid Smell (焦糊味)"),
            (25, {"spd": 105, "alt": 5500, "oil_p": 80, "progress": 40}, "failure", "CIRCUIT BREAKER POPPED / SMOKE"),
            (60, {"spd": 90,  "alt": 4500, "oil_p": 80, "progress": 100}, "end", "End")
        ]
    }
}

# QRH 内容库
QRH_LIBRARY = {
    "low_oil_pressure": {
        "title": "LOW OIL PRESSURE",
        "items": ["Throttle - REDUCE", "Landing Area - SELECT", "Prepare - FOR ENGINE FAILURE"]
    },
    "engine_fire": {
        "title": "ENGINE FIRE IN FLIGHT",
        "items": ["Mixture - CUTOFF", "Fuel Valve - OFF", "Master Switch - OFF", "Cabin Heat - OFF", "Airspeed - 105 KIAS"]
    },
    "electrical_fire": {
        "title": "ELECTRICAL FIRE",
        "items": ["Master Switch - OFF", "Vents/Cabin Air - CLOSED", "Fire Extinguisher - ACTIVATE", "Avionics - OFF"]
    }
}

# ==========================================
# 2. 核心逻辑
# ==========================================

@app.route('/')
def index():
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
            "session_start_time": time.time(),  # 记录会话开始时间
            "current_phase": "waiting"
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
    rooms[room]['users'][request.sid] = {
        'username': username,
        'role': role
    }

    # 记录用户加入
    log_action(room, username, role, "user_joined",
               details={"session_id": request.sid},
               phase=rooms[room]['current_phase'])

    if len(rooms[room]['users']) >= 2:
        rooms[room]['current_phase'] = "phase1"
        log_action(room, "SYSTEM", "SYSTEM", "phase_started",
                   details={"phase": "phase1", "data": PHASE1_DATA},
                   phase="phase1")
        socketio.emit('start_phase_1', {"data": PHASE1_DATA}, room=room)

# --- Phase 1: 保持不变 ---
@socketio.on('tag_item')
def handle_tag(data):
    room = data['room']
    keyword = data['keyword']

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    is_valid = False
    for section in PHASE1_DATA:
        if keyword in section['threats']:
            is_valid = True
            break

    if is_valid:
        if keyword not in rooms[room]['found_threats']:
            rooms[room]['found_threats'].append(keyword)
            rooms[room]['score'] += 10

            # 记录日志：标注威胁成功
            log_action(room, username, user_role, "tag_threat_success",
                       details={"keyword": keyword, "score_gained": 10},
                       phase="phase1")

            emit('mark_success', {'keyword': keyword, 'role': user_role}, room=room)
            emit('update_score', {'score': rooms[room]['score']}, room=room)
        else:
            # 记录日志：重复标注
            log_action(room, username, user_role, "tag_threat_duplicate",
                       details={"keyword": keyword},
                       phase="phase1")
    else:
        # 记录日志：标注无效
        log_action(room, username, user_role, "tag_threat_invalid",
                   details={"keyword": keyword},
                   phase="phase1")

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

        # === 核心修改：随机抽取剧本 ===
        scenario_key = random.choice(list(SCENARIO_LIBRARY.keys()))
        rooms[room]['current_scenario'] = SCENARIO_LIBRARY[scenario_key]

        scenario_name = rooms[room]['current_scenario']['name']

        # 记录剧本选择
        log_action(room, "SYSTEM", "SYSTEM", "scenario_selected",
                   details={
                       "scenario_key": scenario_key,
                       "scenario_name": scenario_name,
                       "target_qrh": rooms[room]['current_scenario']['target_qrh']
                   },
                   phase="phase2")

        socketio.emit('sys_msg', {'msg': f"系统注入随机情景: {scenario_name} (训练模式可见)"}, room=room)

        socketio.emit('start_phase_2', {'duration': 60}, room=room)
        socketio.start_background_task(run_sim_loop, room)

def run_sim_loop(room):
    start_time = time.time()
    idx = 0

    # 获取当前房间的剧本事件
    events = rooms[room]['current_scenario']['events']

    # 平滑更新间隔（秒）
    update_interval = 0.1

    while idx < len(events):
        if room not in rooms: break

        current_time = time.time() - start_time
        target_time, flight_data, type, desc = events[idx]

        # === 核心改进：线性插值实现平滑进度 ===
        if idx == 0:
            # 第一个事件：直接发送数据
            if current_time >= target_time:
                socketio.emit('flight_update', flight_data, room=room)
                if type in ['warning', 'failure']:
                    socketio.emit('event_trigger', {
                        'type': type,
                        'msg': desc,
                        'progress': flight_data['progress']
                    }, room=room)
                idx += 1
        else:
            # 获取前一个事件的数据用于插值
            prev_time, prev_data, _, _ = events[idx - 1]

            # 如果当前时间在两个事件之间，进行线性插值
            if prev_time <= current_time < target_time:
                # 计算插值比例
                ratio = (current_time - prev_time) / (target_time - prev_time)

                # 对各个参数进行线性插值
                interpolated_data = {
                    'spd': prev_data['spd'] + (flight_data['spd'] - prev_data['spd']) * ratio,
                    'alt': prev_data['alt'] + (flight_data['alt'] - prev_data['alt']) * ratio,
                    'oil_p': prev_data['oil_p'] + (flight_data['oil_p'] - prev_data['oil_p']) * ratio,
                    'progress': prev_data['progress'] + (flight_data['progress'] - prev_data['progress']) * ratio
                }

                # 持续发送插值后的数据
                socketio.emit('flight_update', interpolated_data, room=room)

            # 到达事件时间点，触发事件
            elif current_time >= target_time:
                # 发送精确的目标数据
                socketio.emit('flight_update', flight_data, room=room)

                # 触发事件告警
                if type in ['warning', 'failure']:
                    # 记录事件触发
                    log_action(room, "SYSTEM", "SYSTEM", "event_triggered",
                               details={
                                   "event_type": type,
                                   "description": desc,
                                   "flight_data": flight_data
                               },
                               phase="phase2")

                    socketio.emit('event_trigger', {
                        'type': type,
                        'msg': desc,
                        'progress': flight_data['progress']
                    }, room=room)
                idx += 1

        socketio.sleep(update_interval)

# --- Phase 3: 动态决策判定 ---
@socketio.on('select_checklist')
def handle_select(data):
    room = data['room']
    selected_key = data['key']

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    # 更新当前阶段
    rooms[room]['current_phase'] = "phase3"

    # === 核心修改：根据当前剧本判断对错 ===
    current_scenario = rooms[room]['current_scenario']
    correct_key = current_scenario['target_qrh']

    qrh = QRH_LIBRARY.get(selected_key)
    rooms[room]['checked_items'] = set()
    rooms[room]['active_checklist_len'] = len(qrh['items'])

    is_correct = (selected_key == correct_key)

    if is_correct:
        rooms[room]['score'] += 20
        msg = "✅ 决策正确：识别准确"
    else:
        rooms[room]['score'] -= 20 # 加重惩罚
        msg = f"❌ 决策错误：当前故障是 {current_scenario['name']}，你选择了 {qrh['title']}"

    # 记录QRH选择
    log_action(room, username, user_role, "select_qrh",
               details={
                   "selected_qrh": selected_key,
                   "qrh_title": qrh['title'],
                   "correct_qrh": correct_key,
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
               phase="phase3")

    emit('item_checked', {'index': idx, 'role': user_role}, room=room)

    if len(rooms[room]['checked_items']) == rooms[room]['active_checklist_len']:
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
                   phase="phase3")

        emit('mission_complete', {
            'score': final_score,
            'result': result,
            'summary': f"情景 [{scenario_name}] 处置结束。"
        }, room=room)

if __name__ == '__main__':
    print("启动服务器: http://0.0.0.0:5001")
    # 将 5000 改为 5001
    socketio.run(app, debug=True, use_reloader=False, allow_unsafe_werkzeug=True, host='0.0.0.0', port=5001)