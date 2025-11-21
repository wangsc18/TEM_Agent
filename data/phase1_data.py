"""
Phase 1 数据配置
起飞前威胁识别与管理
"""

# Phase 1 文本信息源
PHASE1_DATA = [
    {"label": "METAR", "content": "CYXH 211800Z 24015G25KT 15SM FEW030"},
    {"label": "Aircraft", "content": "C-GABC Fuel: Full Snags: Landing_Light_U/S"},
    {"label": "Pilot", "content": "Pilot_A: Rest_8hrs Pilot_B: Recovering_from_Cold"}
]

# Phase 1 威胁库 - 包含决策选项和 SOP 数据
PHASE1_THREATS = {
    "24015G25KT": {
        "type": "crosswind",
        "description": "METAR 显示阵风 25 节，可能超出侧风限制",
        "options": [
            {"id": "standard_procedure", "text": "使用侧风起飞标准程序", "correct": True},
            {"id": "wait_wind", "text": "等待风况改善后起飞", "correct": True},
            {"id": "ignore_wind", "text": "忽略侧风影响，正常起飞", "correct": False}
        ],
        "sop_data": {
            "title": "C172 侧风限制",
            "content": [
                "最大演示侧风限制: 15 节",
                "当前阵风: 25 节",
                "状态: ⚠️ 超出限制",
                "建议: 等待风况改善或使用侧风程序"
            ]
        },
        "scores": {
            "pf_correct_pm_approve": 15,
            "pf_correct_pm_reject": -5,
            "pf_wrong_pm_approve": -20,
            "pf_wrong_pm_reject": 5
        }
    },
    "Landing_Light_U/S": {
        "type": "equipment",
        "description": "着陆灯故障（Landing Light Unserviceable）",
        "options": [
            {"id": "check_mel", "text": "查阅 MEL，确认可放行条件", "correct": True},
            {"id": "daylight_ok", "text": "白天飞行无影响，继续起飞", "correct": False},
            {"id": "defer_flight", "text": "推迟航班，等待维修", "correct": True}
        ],
        "sop_data": {
            "title": "MEL 着陆灯条款",
            "content": [
                "着陆灯故障放行条件:",
                "✅ 日间 VFR: 可放行",
                "❌ 夜间或 IFR: 必须工作",
                "当前条件: 日间 VFR (1800Z)",
                "结论: 可放行，需记录"
            ]
        },
        "scores": {
            "pf_correct_pm_approve": 15,
            "pf_correct_pm_reject": -5,
            "pf_wrong_pm_approve": -20,
            "pf_wrong_pm_reject": 5
        }
    },
    "Recovering_from_Cold": {
        "type": "pilot_fitness",
        "description": "副驾驶身体状态：感冒恢复中",
        "options": [
            {"id": "imsafe_check", "text": "执行 IMSAFE 检查，评估适航性", "correct": True},
            {"id": "simple_flight", "text": "简单航线无影响，继续", "correct": False},
            {"id": "monitor_condition", "text": "飞行中持续监控身体状态", "correct": True}
        ],
        "sop_data": {
            "title": "IMSAFE 检查",
            "content": [
                "I - Illness (疾病)",
                "M - Medication (药物)",
                "S - Stress (压力)",
                "A - Alcohol (酒精)",
                "F - Fatigue (疲劳)",
                "E - Eating (饮食)",
                "⚠️ 感冒可能影响判断力和反应时间"
            ]
        },
        "scores": {
            "pf_correct_pm_approve": 15,
            "pf_correct_pm_reject": -5,
            "pf_wrong_pm_approve": -20,
            "pf_wrong_pm_reject": 5
        }
    }
}

# Phase 1 紧急预案知识测试
EMERGENCY_QUIZ = [
    {
        "id": "engine_failure_turn",
        "type": "multiple_choice",
        "question": "离地后，如果引擎失效且高度低于多少英尺，严禁掉头？",
        "options": [
            {"id": "a", "text": "200 英尺", "correct": False},
            {"id": "b", "text": "500 英尺", "correct": True},
            {"id": "c", "text": "1000 英尺", "correct": False},
            {"id": "d", "text": "1500 英尺", "correct": False}
        ],
        "explanation": "标准程序：500 英尺以下直线迫降，避免失速螺旋"
    },
    {
        "id": "fire_memory_item",
        "type": "multiple_choice",
        "question": "发现引擎火警时，第一记忆项目是？",
        "options": [
            {"id": "a", "text": "关闭主电门", "correct": False},
            {"id": "b", "text": "混合比 - CUTOFF", "correct": True},
            {"id": "c", "text": "打开灭火器", "correct": False},
            {"id": "d", "text": "宣布 MAYDAY", "correct": False}
        ],
        "explanation": "引擎火警首要动作：切断燃油供应"
    },
    {
        "id": "electrical_fire",
        "type": "multiple_choice",
        "question": "电气火灾的标准处置程序中，第一步是？",
        "options": [
            {"id": "a", "text": "打开所有通风口", "correct": False},
            {"id": "b", "text": "关闭主电门 (Master Switch OFF)", "correct": True},
            {"id": "c", "text": "降低高度", "correct": False},
            {"id": "d", "text": "使用灭火器", "correct": False}
        ],
        "explanation": "电气火灾首要：切断电源"
    }
]
