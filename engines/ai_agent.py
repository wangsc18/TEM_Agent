#!/usr/bin/env python3
"""
双过程AI Agent - 基于双过程理论的飞行员AI

架构：观察(Observation) → 策略(Strategy) → 动作(Action) → 执行(Execute)

核心组件：
- StateObserver: 观察层（提取状态，不用LLM）
- StrategyGenerator: 策略层（Slow Engine，深度推理）
- ActionExecutor: 执行层（Fast Engine，快速响应）
"""
import asyncio
from typing import Dict, Any, Optional, List

# 导入核心模块
from .ai_core import (
    Observation, Strategy, Action,
    StateObserver, StrategyGenerator, ActionExecutor,
    random_delay, extract_quiz_answer, extract_qrh_key, detect_abnormal_gauges
)
from .text_llm_engine import TextLLMEngine


class DualProcessAIAgent:
    """双过程AI Agent - 结合快速响应和深度推理"""

    def __init__(
        self,
        room: str,
        role: str,
        fast_engine: TextLLMEngine,
        slow_engine: TextLLMEngine,
        socketio,
        game_logic,
        config: Optional[Dict] = None
    ):
        """
        初始化双过程AI Agent

        Args:
            room: 房间ID
            role: AI角色 ("PF" or "PM")
            fast_engine: 快速响应引擎 (gpt-4o-mini)
            slow_engine: 策略推理引擎 (gpt-4o)
            socketio: SocketIO实例
            game_logic: GameLogic业务逻辑层实例
            config: 配置参数
        """
        self.room = room
        self.role = role
        self.fast_engine = fast_engine
        self.slow_engine = slow_engine
        self.socketio = socketio
        self.game_logic = game_logic
        self.config = config or {}

        # 虚拟session_id
        self.fake_sid = f"AI_{room}_{role}"

        # 核心组件初始化
        self.observer = StateObserver(role=role)
        self.strategy_gen = StrategyGenerator(
            slow_engine=slow_engine,
            role=role,
            config=config
        )
        self.executor = ActionExecutor(
            fast_engine=fast_engine,
            role=role,
            config=config
        )

        # 状态管理
        self.current_phase = "waiting"
        self.conversation_history = []
        self.pending_actions = []
        self.strategic_context = {}  # 策略上下文（Slow Engine维护）

        # 配置参数
        self.fast_response_delay = config.get('fast_response_delay', (1, 3))
        self.slow_thinking_time = config.get('slow_thinking_time', (3, 6))

        print(f"[DualProcessAI] 初始化 AI {role} for room {room}")
        print(f"[DualProcessAI] Fast Engine: {fast_engine.model}")
        print(f"[DualProcessAI] Slow Engine: {slow_engine.model}")

    # ==========================================
    # Phase 1: 起飞前威胁管理（新架构）
    # ==========================================

    async def on_phase1_start(self, phase1_data: List[Dict]):
        """Phase 1 开始"""
        self.current_phase = "phase1"
        print(f"[DualProcessAI] Phase 1 开始，角色: {self.role}")

        if self.role == "PF":
            await self._phase1_pf_identify_threats(phase1_data)
        else:
            print(f"[DualProcessAI] PM 准备验证 PF 的决策")

    async def _phase1_pf_identify_threats(self, phase1_data: List[Dict]):
        """
        PF识别威胁 - 循环识别所有威胁

        策略：逐个识别威胁，每识别一个就决策一个，直到所有威胁处理完毕
        """
        print(f"[DualProcessAI] PF 开始识别所有威胁...")

        all_text = " ".join([item['content'] for item in phase1_data])

        # 已知威胁列表（从数据中获取）
        from data.phase1_data import PHASE1_THREATS
        all_threats = list(PHASE1_THREATS.keys())

        print(f"[DualProcessAI] 待识别威胁: {all_threats}")

        # 循环识别每个威胁
        for threat_keyword in all_threats:
            # 检查是否已处理
            room_state = self.game_logic.rooms.get(self.room, {})
            if threat_keyword in room_state.get('phase1_threats', {}):
                print(f"[DualProcessAI] 威胁 {threat_keyword} 已处理，跳过")
                continue

            print(f"[DualProcessAI] 准备识别威胁: {threat_keyword}")

            # 模拟识别延迟
            await asyncio.sleep(random_delay(*self.fast_response_delay))

            # 调用业务逻辑层识别威胁
            from game_logic import Actor
            actor = Actor(f"AI {self.role}", self.role, is_ai=True)
            success = self.game_logic.pf_identify_threat(self.room, threat_keyword, actor)

            if success:
                print(f"[DualProcessAI] 威胁 {threat_keyword} 识别成功")

                # 获取威胁数据并触发决策流程
                threat_data = PHASE1_THREATS.get(threat_keyword)
                if threat_data:
                    print(f"[DualProcessAI] 触发PF决策流程: {threat_keyword}")
                    await self.on_pf_decision_request(threat_keyword, threat_data)
                    print(f"[DualProcessAI] 威胁 {threat_keyword} 决策完成")

                    # 等待一段时间再处理下一个威胁（模拟真实思考间隔）
                    await asyncio.sleep(random_delay(1, 2))
            else:
                print(f"[DualProcessAI] 威胁 {threat_keyword} 识别失败")

        print(f"[DualProcessAI] PF 完成所有威胁识别")

    async def on_pf_decision_request(self, keyword: str, threat_data: Dict):
        """
        PF决策请求 - 使用新架构

        流程：观察 → 策略 → 动作 → 执行

        Args:
            keyword: 威胁关键词
            threat_data: 威胁详细数据
        """
        if self.role != "PF":
            return

        print(f"[DualProcessAI] PF 收到决策请求: {keyword}")
        print(f"[新架构] 开始 观察→策略→动作→执行 流程")

        # 步骤1: 观察（从room_state提取信息）
        room_state = self.game_logic.rooms.get(self.room, {})
        observation = self.observer.observe(room_state)
        print(f"[观察层] Phase: {observation.phase}, Role: {observation.role}")

        # 准备完整的威胁数据（包含keyword）
        full_threat_data = {
            'keyword': keyword,
            'description': threat_data.get('description', ''),
            'options': threat_data.get('options', []),
            'sop_data': threat_data.get('sop_data', {})
        }

        # 步骤2: Slow Engine 生成策略（包含推荐选项和解释）
        strategy = await self.strategy_gen.strategize_pf_decision(observation, full_threat_data)
        print(f"[策略层] 推荐方案: {strategy.recommendation}")

        # 步骤3: Fast Engine 生成动作
        action = self.executor.execute_pf_decision(strategy)
        print(f"[执行层] 动作: {action.to_dict()}")

        # 步骤4: 执行动作
        from game_logic import Actor
        actor = Actor(f"AI {self.role}", self.role, is_ai=True)

        if action.action_type == 'pf_submit_decision':
            option_id = action.params.get('option_id', '')
            if option_id:
                success = self.game_logic.pf_submit_decision(self.room, keyword, option_id, actor)
                if success:
                    print(f"[执行完成] PF决策: {option_id} - 已提交到PM验证")
                else:
                    print(f"[执行失败] PF决策提交失败: {option_id}")
                    return
            else:
                print(f"[执行失败] 未获取到有效的option_id")
                return

        # 步骤5: 发送解释消息（如果有）
        if strategy.explanation:
            print(f"[解释发送] {strategy.explanation}")
            # 延迟一下再发送，让决策结果先显示
            await asyncio.sleep(0.5)
            self.game_logic.send_ai_message(self.room, strategy.explanation, actor)

    async def on_pm_verify_request(self, pf_decision_data: Dict):
        """
        PM验证PF决策 - 使用新架构

        流程：观察 → 策略 → 动作 → 执行
        """
        if self.role != "PM":
            return

        print(f"[DualProcessAI] PM 收到验证请求: {pf_decision_data['pf_decision']}")
        print(f"[新架构] 开始 观察→策略→动作→执行 流程")

        # 步骤1: 观察（从room_state提取信息）
        room_state = self.game_logic.rooms.get(self.room, {})
        observation = self.observer.observe(room_state)
        print(f"[观察层] Phase: {observation.phase}, Role: {observation.role}")

        # 步骤2: Slow Engine 生成策略（包含解释）
        strategy = await self.strategy_gen.strategize_pm_verify(observation, pf_decision_data)
        print(f"[策略层] 建议: {strategy.recommendation}")

        # 步骤3: Fast Engine 生成动作
        action = self.executor.execute_pm_verify(strategy)
        print(f"[执行层] 动作: {action.to_dict()}")

        # 步骤4: 执行动作
        from game_logic import Actor
        actor = Actor(f"AI {self.role}", self.role, is_ai=True)

        if action.action_type == 'pm_verify_decision':
            self.game_logic.pm_verify_decision(
                self.room,
                action.params['approve'],
                actor
            )
            print(f"[执行完成] PM验证: {'同意' if action.params['approve'] else '驳回'}")

        # 步骤5: 发送解释消息（如果有）
        if strategy.explanation:
            print(f"[解释发送] {strategy.explanation}")
            # 延迟一下再发送，让验证结果先显示
            await asyncio.sleep(0.5)
            self.game_logic.send_ai_message(self.room, strategy.explanation, actor)

    async def on_quiz_questions(self, questions: List[Dict]):
        """PM答题 - 顺序处理所有题目"""
        if self.role != "PM":
            return

        print(f"[DualProcessAI] PM 收到 {len(questions)} 道测试题，开始顺序答题...")

        for question_data in questions:
            await self._answer_quiz_question(question_data)

    async def _answer_quiz_question(self, question_data: Dict):
        """回答单个测试题"""
        print(f"[DualProcessAI] PM 收到测试题: {question_data['question'][:30]}...")

        options_text = "\n".join([
            f"{opt['id']}: {opt['text']}"
            for opt in question_data['options']
        ])

        prompt = f"""问题: {question_data['question']}

选项:
{options_text}

根据C172应急程序知识，选择正确答案。只返回选项ID（a/b/c/d）。"""

        await asyncio.sleep(random_delay(2, 4))

        try:
            response = await self.fast_engine.chat(prompt, stream=False)
            answer = extract_quiz_answer(response, question_data['options'])

            from game_logic import Actor
            actor = Actor(f"AI {self.role}", self.role, is_ai=True)
            self.game_logic.submit_quiz_answer(self.room, question_data['id'], answer, actor)
        except Exception as e:
            print(f"[FastEngine] 答题错误: {e}")

    # ==========================================
    # Phase 2: 空中监控（旧实现）
    # ==========================================

    async def on_phase2_gauge_update(self, gauge_states: Dict):
        """Phase 2: 监控仪表 - 快速检测异常"""
        abnormal = detect_abnormal_gauges(gauge_states)

        if abnormal:
            from game_logic import Actor
            actor = Actor(f"AI {self.role}", self.role, is_ai=True)

            for gauge_id in abnormal:
                await asyncio.sleep(0.3)
                self.game_logic.monitor_gauge(self.room, gauge_id, actor)

    # ==========================================
    # Phase 3: QRH选择（旧实现）
    # ==========================================

    async def on_event_alert(self, event_data: Dict):
        """事件警报 - 快速匹配QRH"""
        print(f"[DualProcessAI] 收到事件警报: {event_data['msg']}")

        # 简单规则匹配
        msg = event_data['msg'].upper()

        qrh_keywords = {
            'OIL PRESSURE': 'low_oil_pressure',
            'CARBURETOR ICING': 'carburetor_icing',
            'FUEL IMBALANCE': 'fuel_imbalance',
            'VACUUM': 'vacuum_failure',
            'ALTERNATOR': 'alternator_failure',
            'ENGINE FIRE': 'engine_fire',
            'ELECTRICAL FIRE': 'electrical_fire'
        }

        qrh_key = None
        for keyword, key in qrh_keywords.items():
            if keyword in msg:
                qrh_key = key
                break

        if qrh_key:
            await asyncio.sleep(1)

            from game_logic import Actor
            actor = Actor(f"AI {self.role}", self.role, is_ai=True)
            self.game_logic.select_qrh(self.room, qrh_key, actor)

    async def on_checklist_shown(self, checklist_data: Dict):
        """执行检查单 - Fast Engine快速执行"""
        items_count = len(checklist_data['items'])

        print(f"[DualProcessAI] 执行检查单: {checklist_data['title']} ({items_count}项)")

        from game_logic import Actor
        actor = Actor(f"AI {self.role}", self.role, is_ai=True)

        for i in range(items_count):
            await asyncio.sleep(random_delay(1.5, 3))
            self.game_logic.check_item(self.room, i, actor)

    # ==========================================
    # 聊天消息响应（新增）
    # ==========================================

    async def on_chat_message(self, chat_data: Dict):
        """
        处理聊天消息 - 判断是否需要回复

        Args:
            chat_data: 聊天消息数据
                - sender: 发送者名字
                - role: 发送者角色
                - message: 消息内容
                - timestamp: 时间戳
        """
        sender = chat_data['sender']
        sender_role = chat_data['role']
        message = chat_data['message']

        print(f"[DualProcessAI] 收到聊天消息: {sender} ({sender_role}): {message}")

        # 获取聊天历史（最近5条）
        chat_history = self.game_logic.get_chat_history(self.room, limit=5)

        # 获取当前阶段信息
        room_state = self.game_logic.rooms.get(self.room, {})
        current_phase = room_state.get('current_phase', 'unknown')

        # 构建上下文
        history_text = ""
        if len(chat_history) > 1:  # 至少有2条消息（包括刚发送的）
            for msg in chat_history[:-1]:  # 排除最新这条
                history_text += f"{msg['username']}: {msg['message']}\n"

        # Fast Engine 快速判断是否需要回复
        prompt = f"""你是一名{self.role}飞行员，正在与搭档进行飞行训练。

【当前阶段】
{current_phase}

【最近对话】
{history_text if history_text else "(这是第一条消息)"}

【搭档刚才说】
{sender} ({sender_role}): {message}

【你的任务】
快速判断是否需要回复这条消息。

【需要回复的情况】
✅ 对方在向你提问
✅ 对方在寻求你的意见
✅ 对方在讨论飞行决策
✅ 对方在分享重要观察
✅ 对方在表达担忧
✅ 需要确认或回应的信息

【不需要回复的情况】
❌ 对方只是自言自语
❌ 对方在陈述事实，不需要回应
❌ 对方说的话不涉及你
❌ 简单的确认消息（如"收到"、"好的"）

返回JSON格式：
{{
    "should_reply": true/false,
    "reply_message": "如果需要回复，写一句简短自然的回复（10-30字）；如果不需要回复，留空",
    "reasoning": "简短说明为什么回复或不回复"
}}
"""

        try:
            # Fast Engine快速判断（1-2秒）
            await asyncio.sleep(random_delay(1, 2))
            response = await self.fast_engine.chat(prompt, stream=False)

            # 解析响应
            from .ai_core.utils import parse_json_response
            result = parse_json_response(response)

            should_reply = result.get('should_reply', False)
            reply_message = result.get('reply_message', '').strip()
            reasoning = result.get('reasoning', '')

            print(f"[FastEngine] 回复判断: {should_reply}, 理由: {reasoning}")

            if should_reply and reply_message:
                print(f"[FastEngine] 准备回复: {reply_message}")

                # 发送回复
                from game_logic import Actor
                actor = Actor(f"AI {self.role}", self.role, is_ai=True)
                self.game_logic.send_ai_message(self.room, reply_message, actor)
            else:
                print(f"[FastEngine] 不需要回复")

        except Exception as e:
            print(f"[FastEngine] 聊天响应错误: {e}")
            import traceback
            traceback.print_exc()
