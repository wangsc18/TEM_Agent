import eventlet
# 关键：不要 patch threading，保留原生线程用于 TTS
eventlet.monkey_patch(thread=False)

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room
import time
import random
import json
import os
from datetime import datetime
import asyncio
import base64
import threading
import queue

# 导入数据配置
from data.phase1_data import PHASE1_DATA, PHASE1_THREATS, EMERGENCY_QUIZ
from data.phase2_scenarios import SCENARIO_LIBRARY  # 保留作为备选
from data.phase2_advanced import (
    MULTI_EVENT_SCENARIOS,
    GAUGE_CONFIGS,
    generate_precursor_value
)
from data.qrh_library import QRH_LIBRARY

# 导入AI Agent和业务逻辑层
from engines.ai_agent import DualProcessAIAgent
from engines.text_llm_engine import TextLLMEngine
from game_logic import GameLogic, Actor
from config import (
    OPENAI_API_KEY,
    CUSTOM_BASE_URL,
    AI_ENABLED,
    AI_FAST_MODEL,
    AI_SLOW_MODEL,
    AI_FAST_TEMPERATURE,
    AI_SLOW_TEMPERATURE,
    AI_FAST_MAX_TOKENS,
    AI_SLOW_MAX_TOKENS,
    AI_FAST_RESPONSE_DELAY,
    AI_SLOW_THINKING_TIME
)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tem_multi_scenario'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

rooms = {}

# ==========================================
# TTS 语音生成 - 原生线程生成，队列传递，greenlet发送
# ==========================================

# TTS音频队列（线程安全）
_tts_audio_queue = queue.Queue()

async def _generate_tts_audio_only(text: str, voice: str):
    """
    纯音频生成（运行在原生线程中）

    Args:
        text: 要转换的文本
        voice: 语音类型

    Returns:
        bytes: 音频数据
    """
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    audio_bytes = b""

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes += chunk["data"]

    return audio_bytes

def _tts_sender_loop():
    """
    TTS发送循环（运行在greenlet中，从队列取数据发送）
    """
    while True:
        try:
            # 从队列获取数据（阻塞等待）
            data = _tts_audio_queue.get(timeout=0.1)
            if data is None:
                continue

            room, message_id, sentence_index, audio_bytes = data

            if not audio_bytes:
                print(f"[TTS] 警告: 没有音频数据")
                continue

            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            print(f"[TTS] 音频生成成功: {len(audio_bytes)} 字节")

            # 在greenlet中发送
            socketio.emit('tts_audio', {
                'message_id': message_id,
                'sentence_index': sentence_index,
                'audio_base64': audio_base64
            }, room=room)
            print(f"[TTS] 句子 #{sentence_index} 音频已发送")

        except queue.Empty:
            pass
        except Exception as e:
            print(f"[TTS] 发送错误: {e}")
            import traceback
            traceback.print_exc()

        # 让出控制权给其他greenlet
        eventlet.sleep(0)

def submit_tts_request(text: str, room: str, message_id: str,
                      sentence_index: int, voice: str = "zh-CN-XiaoxiaoNeural"):
    """
    提交TTS请求（原生线程生成 + 队列传递 + greenlet发送）

    Args:
        text: 要转换的文本
        room: 房间ID
        message_id: 消息ID
        sentence_index: 句子索引
        voice: 语音类型
    """
    print(f"[TTS] 请求: 句子 #{sentence_index}: {text[:30]}...")

    def run_in_thread():
        """在原生线程中生成音频"""
        try:
            print(f"[TTS] 开始生成音频...")

            # 原生线程中生成音频
            audio_bytes = asyncio.run(_generate_tts_audio_only(text, voice))

            print(f"[TTS] 音频生成完成，大小: {len(audio_bytes)} 字节")

            # 把音频数据放入队列（线程安全）
            _tts_audio_queue.put((room, message_id, sentence_index, audio_bytes))

        except Exception as e:
            print(f"[TTS] 生成错误: {e}")
            import traceback
            traceback.print_exc()

    # 使用原生线程生成音频
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()

# ==========================================
# 初始化业务逻辑层（全局单例）
# ==========================================

game_logic = None  # 延迟初始化，在log_action定义后

# 工具函数：在eventlet中运行async函数
# ==========================================

def run_async_in_greenlet(coro):
    """
    在eventlet greenlet中运行async协程
    解决eventlet与asyncio不兼容的问题
    """
    import asyncio

    def wrapper():
        try:
            # 使用 asyncio.run() 而不是手动管理 event loop
            # asyncio.run() 会自动创建、运行、清理 event loop
            return asyncio.run(coro)
        except Exception as e:
            print(f"[AsyncRunner] 错误: {e}")
            import traceback
            traceback.print_exc()

    socketio.start_background_task(wrapper)

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

# 初始化业务逻辑层（全局单例）
game_logic = GameLogic(rooms, socketio, log_action)

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
            "pending_decisions_queue": [],  # PM验证决策队列（支持AI异步处理多个威胁）
            # Phase 2 高级功能状态
            "event_queue": [],  # 当前场景的事件队列
            "current_event_index": -1,  # 当前处理到第几个事件
            "monitored_gauges": set(),  # 用户标记监控的仪表
            "event_detections": {},  # 记录每个事件的检测情况 {event_id: {'detected_at': 'precursor'/'alert', 'timestamp': float}}
            "gauge_states": {},  # 当前所有仪表的实时状态
            "sim_start_time": None,  # Phase 2 模拟开始时间
            "used_qrh": set(),  # 已使用的 QRH 检查单
            # AI Agent 状态（新增）
            "mode": "dual_player",  # "dual_player" or "single_player"
            "ai_enabled": False,     # 是否启用AI
            "ai_agent": None,        # DualProcessAIAgent 实例
            "human_sid": None,       # 单人模式下的人类session_id
            # 聊天历史
            "chat_history": []       # 保存聊天消息历史，供AI分析使用
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
    mode = data.get('mode', 'dual_player')  # 新增：从前端获取模式

    # === 核心修改：支持单人+AI模式 ===
    if mode == 'single_player' and AI_ENABLED:
        print(f"[AI Mode] 创建单人+AI训练房间 {room}")

        # 设置单人模式
        rooms[room]['mode'] = 'single_player'
        rooms[room]['ai_enabled'] = True
        rooms[room]['human_sid'] = request.sid

        # 确定AI角色（与人类相反）
        ai_role = "PM" if role == "PF" else "PF"

        # 创建双引擎LLM
        fast_engine = TextLLMEngine(
            api_key=OPENAI_API_KEY,
            base_url=CUSTOM_BASE_URL,
            model=AI_FAST_MODEL,
            system_prompt=f"你是一名专业的航空飞行员，角色是{ai_role}。你的回答要简洁、快速、准确。",
            temperature=AI_FAST_TEMPERATURE,
            max_tokens=AI_FAST_MAX_TOKENS
        )

        slow_engine = TextLLMEngine(
            api_key=OPENAI_API_KEY,
            base_url=CUSTOM_BASE_URL,
            model=AI_SLOW_MODEL,
            system_prompt=f"你是一名经验丰富的航空飞行员，角色是{ai_role}。你需要深入分析情况，提供详细的策略和理由。",
            temperature=AI_SLOW_TEMPERATURE,
            max_tokens=AI_SLOW_MAX_TOKENS
        )

        # 创建双过程AI Agent
        ai_agent = DualProcessAIAgent(
            room=room,
            role=ai_role,
            fast_engine=fast_engine,
            slow_engine=slow_engine,
            socketio=socketio,
            game_logic=game_logic,  # 传入业务逻辑层
            config={
                'fast_response_delay': AI_FAST_RESPONSE_DELAY,
                'slow_thinking_time': AI_SLOW_THINKING_TIME
            }
        )

        rooms[room]['ai_agent'] = ai_agent

        # 添加人类用户
        rooms[room]['users'][request.sid] = {
            'username': username,
            'role': role,
            'is_ai': False
        }

        # 添加AI用户（虚拟session_id）
        rooms[room]['users'][ai_agent.fake_sid] = {
            'username': f"AI {ai_role}",
            'role': ai_role,
            'is_ai': True
        }

        # 记录AI加入
        log_action(room, f"AI {ai_role}", ai_role, "ai_joined",
                   details={
                       "ai_mode": "dual_process",
                       "fast_model": AI_FAST_MODEL,
                       "slow_model": AI_SLOW_MODEL
                   },
                   phase="waiting")

        # 达到2人（1人+AI），启动训练
        rooms[room]['current_phase'] = "phase1"
        socketio.emit('start_phase_1', {"data": PHASE1_DATA}, room=room)

        # 触发AI准备（使用通用异步运行器）
        run_async_in_greenlet(ai_agent.on_phase1_start(PHASE1_DATA))

        # 通知房间内人数
        socketio.emit('user_count_update', {
            'count': 2,
            'usernames': [username, f"🤖 AI {ai_role}"]
        }, room=room)

        print(f"[AI Mode] 单人+AI模式启动成功: {username} ({role}) + AI ({ai_role})")

    else:
        # === 双人模式：原有逻辑 ===
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

    # 调用统一业务逻辑层
    actor = Actor(username, user_role, is_ai=False, sid=request.sid)
    success = game_logic.pf_identify_threat(room, keyword, actor)

    if not success:
        emit('error_msg', {'msg': "威胁识别失败"})
        return

    # 获取威胁数据用于AI触发
    threat_data = PHASE1_THREATS[keyword]

    # === AI触发：如果AI是PF，触发AI决策 ===
    if rooms[room]['ai_enabled']:
        ai_agent = rooms[room]['ai_agent']
        if ai_agent and ai_agent.role == "PF":
            run_async_in_greenlet(ai_agent.on_pf_decision_request(keyword, threat_data))


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

    # 调用统一业务逻辑层
    actor = Actor(username, user_role, is_ai=False, sid=request.sid)
    game_logic.pf_submit_decision(room, keyword, selected_option_id, actor)

    # === AI触发：如果AI是PM，触发AI验证 ===
    if rooms[room]['ai_enabled']:
        ai_agent = rooms[room]['ai_agent']
        if ai_agent and ai_agent.role == "PM":
            threat_data = PHASE1_THREATS[keyword]
            selected_option = next((opt for opt in threat_data['options'] if opt['id'] == selected_option_id), None)
            pm_data = {
                'keyword': keyword,
                'pf_username': username,
                'pf_decision': selected_option['text'],
                'sop_data': threat_data['sop_data']
            }
            run_async_in_greenlet(ai_agent.on_pm_verify_request(pm_data))


@socketio.on('pm_verify_decision')
def handle_pm_verify(data):
    """PM 验证 PF 的决策（socketio事件入口）"""
    room = data['room']
    approved = data['approved']

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    # 验证是否为 PM
    if user_role != 'PM':
        return

    # 调用统一业务逻辑层
    actor = Actor(username, user_role, is_ai=False, sid=request.sid)
    game_logic.pm_verify_decision(room, approved, actor)

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

    # === AI触发：如果AI是PM，触发AI答题 ===
    if rooms[room]['ai_enabled']:
        ai_agent = rooms[room]['ai_agent']
        if ai_agent and ai_agent.role == "PM":
            # 传入所有题目，让AI内部顺序处理（避免多个event loop冲突）
            run_async_in_greenlet(ai_agent.on_quiz_questions(EMERGENCY_QUIZ))


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

    # 调用统一业务逻辑层
    actor = Actor(username, user_role, is_ai=False, sid=request.sid)
    game_logic.submit_quiz_answer(room, question_id, selected_answer, actor)


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

    # === 修复：单人模式下直接进入Phase 2 ===
    mode = rooms[room].get('mode', 'dual_player')
    required_ready_count = 1 if mode == 'single_player' else 2

    if len(rooms[room]['ready_for_next']) >= required_ready_count:
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

                        # === AI触发：事件警报时，AI选择QRH ===
                        if rooms[room]['ai_enabled']:
                            ai_agent = rooms[room]['ai_agent']
                            if ai_agent:
                                event_data = {
                                    'type': alert['type'],
                                    'msg': alert['message'],
                                    'progress': progress
                                }

                                # 后台任务中调用：使用线程隔离避免event loop冲突
                                def event_alert_in_thread():
                                    import asyncio
                                    import threading
                                    # 在原生线程中运行，完全隔离
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    try:
                                        loop.run_until_complete(ai_agent.on_event_alert(event_data))
                                    finally:
                                        loop.close()

                                # 使用原生线程而非greenlet
                                thread = threading.Thread(target=event_alert_in_thread, daemon=True)
                                thread.start()

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

    # 调用统一业务逻辑层
    actor = Actor(username, user_role, is_ai=False, sid=request.sid)
    gauge_info = game_logic.monitor_gauge(room, gauge_id, actor)

    # === AI触发：人类点击仪表时，AI用Slow Engine分析并提供教学 ===
    if rooms[room]['ai_enabled'] and gauge_info.get('success'):
        ai_agent = rooms[room]['ai_agent']
        if ai_agent:
            print(f"[AI触发] 用户点击仪表 {gauge_id}，触发AI深度分析...")
            # socketio事件中，使用标准方式（与Phase 1相同）
            run_async_in_greenlet(ai_agent.on_gauge_monitored_by_human(gauge_info))

# --- Phase 3: 动态决策判定 ---
@socketio.on('select_checklist')
def handle_select(data):
    room = data['room']
    selected_key = data['key']

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    # 调用统一业务逻辑层
    actor = Actor(username, user_role, is_ai=False, sid=request.sid)
    success = game_logic.select_qrh(room, selected_key, actor)

    if not success:
        emit('error_msg', {'msg': f"该检查单已经执行过了，请选择其他应急程序"})
        return

    # === AI触发：显示检查单后，AI执行检查单 ===
    if rooms[room]['ai_enabled']:
        ai_agent = rooms[room]['ai_agent']
        if ai_agent:
            qrh = QRH_LIBRARY.get(selected_key)
            checklist_data = {
                'title': qrh['title'],
                'items': qrh['items'],
                'msg': ''  # AI不需要msg
            }
            # socketio事件中，使用标准方式（与Phase 1相同）
            run_async_in_greenlet(ai_agent.on_checklist_shown(checklist_data))

@socketio.on('check_item')
def handle_check(data):
    room = data['room']
    idx = data['index']

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    # 调用统一业务逻辑层
    actor = Actor(username, user_role, is_ai=False, sid=request.sid)
    game_logic.check_item(room, idx, actor)

# --- 聊天消息处理 ---
@socketio.on('send_chat_message')
def handle_chat_message(data):
    """处理用户发送的聊天消息"""
    room = data['room']
    message = data['message']

    if room not in rooms:
        return

    # 获取用户信息
    user_info = rooms[room]['users'][request.sid]
    username = user_info['username']
    user_role = user_info['role']

    # 创建消息记录
    chat_record = {
        'username': username,
        'role': user_role,
        'message': message,
        'timestamp': datetime.now().isoformat(),
        'is_ai': user_info.get('is_ai', False)
    }

    # 保存到聊天历史
    rooms[room]['chat_history'].append(chat_record)
    # 限制历史记录数量，避免内存过大
    if len(rooms[room]['chat_history']) > 100:
        rooms[room]['chat_history'] = rooms[room]['chat_history'][-100:]

    # 记录聊天消息
    log_action(room, username, user_role, "chat_message",
               details={"message": message},
               phase=rooms[room].get('current_phase', 'unknown'))

    # 广播消息给房间内所有人（包括发送者）
    socketio.emit('chat_message', {
        'username': username,
        'role': user_role,
        'message': message,
        'timestamp': chat_record['timestamp']
    }, room=room)

    # === AI触发：监听人类消息并判断是否需要回复 ===
    if rooms[room]['ai_enabled'] and not user_info.get('is_ai', False):
        ai_agent = rooms[room]['ai_agent']
        if ai_agent:
            # 创建聊天消息数据
            chat_data = {
                'sender': username,
                'role': user_role,
                'message': message,
                'timestamp': chat_record['timestamp']
            }
            # socketio事件中，使用标准方式（与Phase 1相同）
            run_async_in_greenlet(ai_agent.on_chat_message(chat_data))

# --- TTS 语音生成请求 ---
@socketio.on('request_tts')
def handle_tts_request(data):
    """处理TTS语音生成请求 - 使用socketio后台任务"""
    room = data['room']
    text = data['text']
    message_id = data.get('message_id', '')
    sentence_index = data.get('sentence_index', 0)  # 句子索引
    total_sentences = data.get('total_sentences', 1)  # 总句子数

    if room not in rooms:
        return

    print(f"[TTS] 请求: 句子 #{sentence_index}/{total_sentences}: {text[:25]}...")

    # 使用socketio后台任务处理TTS请求
    submit_tts_request(
        text=text,
        room=room,
        message_id=message_id,
        sentence_index=sentence_index,
        voice="zh-CN-XiaoxiaoNeural"
    )


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
    # 启动TTS发送循环（在greenlet中运行）
    socketio.start_background_task(_tts_sender_loop)
    print("[TTS] 发送循环已启动")
    # 将 5000 改为 5001
    socketio.run(app, debug=True, use_reloader=False, allow_unsafe_werkzeug=True, host='0.0.0.0', port=5001)