"""
Phase 1 数据配置
起飞前威胁识别与管理
支持多场景随机选择
"""

import random

# ============================================================================
# 场景 1: 侧风挑战
# ============================================================================
SCENARIO_1 = {
    "name": "侧风挑战",
    "description": "强侧风阵风条件下的起飞决策",
    "data": [
        {"label": "METAR", "content": "CYXH 211800Z 24015G25KT 15SM FEW030"},
        {"label": "Aircraft", "content": "C-GABC Fuel: Full Snags: Landing_Light_U/S"},
        {"label": "Pilot", "content": "Pilot_A: Rest_8hrs Pilot_B: Recovering_from_Cold"}
    ],
    "threats": {
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
    },
    "quiz": [
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
}

# ============================================================================
# 场景 2: 低能见度挑战
# ============================================================================
SCENARIO_2 = {
    "name": "低能见度挑战",
    "description": "浓雾、低燃油和飞行员疲劳的多重威胁",
    "data": [
        {"label": "METAR", "content": "CYXH 211800Z 09005KT 1/2SM FG OVC002 M02/M02 A3015"},
        {"label": "Aircraft", "content": "C-GDXE Fuel: 1.5hrs_remaining Snags: Left_Brake_Soft"},
        {"label": "Pilot", "content": "Pilot_A: Sleep_5hrs Pilot_B: Rest_adequate"}
    ],
    "threats": {
        "1/2SM FG": {
            "type": "visibility",
            "description": "能见度仅 1/2 英里，浓雾条件",
            "options": [
                {"id": "check_minimums", "text": "检查起飞最低标准，评估是否符合 VFR", "correct": True},
                {"id": "taxi_slow", "text": "慢速滑行，注意观察", "correct": False},
                {"id": "cancel_flight", "text": "取消航班，等待天气改善", "correct": True}
            ],
            "sop_data": {
                "title": "VFR 最低天气标准",
                "content": [
                    "VFR 最低能见度: G类空域 1 SM",
                    "当前能见度: 1/2 SM",
                    "云底高度: 200 英尺 (低于最低)",
                    "状态: ❌ 不符合 VFR 标准",
                    "建议: 取消或等待改善"
                ]
            },
            "scores": {
                "pf_correct_pm_approve": 15,
                "pf_correct_pm_reject": -5,
                "pf_wrong_pm_approve": -25,
                "pf_wrong_pm_reject": 5
            }
        },
        "Fuel: 1.5hrs_remaining": {
            "type": "fuel",
            "description": "燃油仅剩 1.5 小时，计划航程 1 小时",
            "options": [
                {"id": "check_regulations", "text": "检查 VFR 燃油储备要求（日间30分钟）", "correct": True},
                {"id": "sufficient", "text": "足够完成航程，继续", "correct": False},
                {"id": "refuel", "text": "加油至满油，确保充足储备", "correct": True}
            ],
            "sop_data": {
                "title": "VFR 燃油储备要求",
                "content": [
                    "日间 VFR 最低储备: 30 分钟",
                    "计划航程时间: 1.0 小时",
                    "当前燃油: 1.5 小时",
                    "状态: ⚠️ 仅达到最低标准",
                    "建议: 考虑加油，应对备降或复飞"
                ]
            },
            "scores": {
                "pf_correct_pm_approve": 15,
                "pf_correct_pm_reject": -5,
                "pf_wrong_pm_approve": -20,
                "pf_wrong_pm_reject": 5
            }
        },
        "Sleep_5hrs": {
            "type": "pilot_fitness",
            "description": "机长仅睡眠 5 小时，可能存在疲劳风险",
            "options": [
                {"id": "imsafe_fatigue", "text": "执行 IMSAFE 检查，重点评估疲劳状态", "correct": True},
                {"id": "short_flight", "text": "航程短，无影响", "correct": False},
                {"id": "copilot_monitor", "text": "副驾驶监控，必要时接管", "correct": True}
            ],
            "sop_data": {
                "title": "疲劳风险管理",
                "content": [
                    "推荐睡眠时间: 8 小时",
                    "当前睡眠: 5 小时",
                    "疲劳风险: 🟡 中等",
                    "影响: 反应时间变慢，决策能力下降",
                    "建议: 评估是否适合执飞"
                ]
            },
            "scores": {
                "pf_correct_pm_approve": 15,
                "pf_correct_pm_reject": -5,
                "pf_wrong_pm_approve": -20,
                "pf_wrong_pm_reject": 5
            }
        }
    },
    "quiz": [
        {
            "id": "vfr_minimums_day",
            "type": "multiple_choice",
            "question": "日间 VFR 在 G 类空域的最低能见度要求是？",
            "options": [
                {"id": "a", "text": "1/2 英里", "correct": False},
                {"id": "b", "text": "1 英里", "correct": True},
                {"id": "c", "text": "3 英里", "correct": False},
                {"id": "d", "text": "5 英里", "correct": False}
            ],
            "explanation": "G类空域日间VFR最低能见度为1英里"
        },
        {
            "id": "fuel_reserve_day",
            "type": "multiple_choice",
            "question": "VFR 日间飞行的最低燃油储备要求是？",
            "options": [
                {"id": "a", "text": "15 分钟", "correct": False},
                {"id": "b", "text": "30 分钟", "correct": True},
                {"id": "c", "text": "45 分钟", "correct": False},
                {"id": "d", "text": "1 小时", "correct": False}
            ],
            "explanation": "日间VFR最低燃油储备为30分钟"
        },
        {
            "id": "fog_formation",
            "type": "multiple_choice",
            "question": "辐射雾（Radiation Fog）最可能在什么条件下形成？",
            "options": [
                {"id": "a", "text": "白天强对流", "correct": False},
                {"id": "b", "text": "晴朗无风的夜晚", "correct": True},
                {"id": "c", "text": "锋面过境时", "correct": False},
                {"id": "d", "text": "高空急流区", "correct": False}
            ],
            "explanation": "辐射雾在晴朗无风的夜晚因地面辐射冷却而形成"
        }
    ]
}

# ============================================================================
# 场景 3: 雷暴威胁
# ============================================================================
SCENARIO_3 = {
    "name": "雷暴威胁",
    "description": "雷暴接近、通讯故障和副驾驶经验不足",
    "data": [
        {"label": "METAR", "content": "CYXH 211800Z 18020G35KT 5SM TSRA BKN015CB OVC040 22/19 A2990"},
        {"label": "Aircraft", "content": "C-GSKY Fuel: Full Snags: COM2_Intermittent"},
        {"label": "Pilot", "content": "Pilot_A: Total_2500hrs Pilot_B: Total_120hrs"}
    ],
    "threats": {
        "TSRA BKN015CB": {
            "type": "weather",
            "description": "雷暴和降雨，伴有积雨云",
            "options": [
                {"id": "avoid_cb", "text": "绝对避让积雨云，规划绕飞路线", "correct": True},
                {"id": "wait_pass", "text": "等待雷暴通过后再起飞", "correct": True},
                {"id": "climb_above", "text": "快速爬升至云层之上", "correct": False}
            ],
            "sop_data": {
                "title": "雷暴规避程序",
                "content": [
                    "积雨云 (CB) 威胁:",
                    "⚡ 严重湍流和风切变",
                    "🌩️ 闪电和雷击风险",
                    "❄️ 结冰和冰雹",
                    "标准: 至少避让 20 英里",
                    "建议: 推迟起飞或大幅绕飞"
                ]
            },
            "scores": {
                "pf_correct_pm_approve": 15,
                "pf_correct_pm_reject": -5,
                "pf_wrong_pm_approve": -30,
                "pf_wrong_pm_reject": 10
            }
        },
        "COM2_Intermittent": {
            "type": "equipment",
            "description": "备用通讯电台（COM2）间歇性故障",
            "options": [
                {"id": "check_com1", "text": "确认 COM1 工作正常，单电台可放行", "correct": True},
                {"id": "no_backup", "text": "无备份通讯，推迟航班", "correct": True},
                {"id": "vfr_no_issue", "text": "VFR 飞行，通讯不重要", "correct": False}
            ],
            "sop_data": {
                "title": "通讯设备要求",
                "content": [
                    "VFR 通讯要求:",
                    "✅ 至少一部可用电台",
                    "⚠️ 备用电台故障可放行",
                    "当前状态: COM1 正常, COM2 故障",
                    "结论: 符合放行条件",
                    "建议: 记录故障，通知维修"
                ]
            },
            "scores": {
                "pf_correct_pm_approve": 15,
                "pf_correct_pm_reject": -5,
                "pf_wrong_pm_approve": -20,
                "pf_wrong_pm_reject": 5
            }
        },
        "Total_120hrs": {
            "type": "pilot_fitness",
            "description": "副驾驶总飞行时间仅 120 小时，经验有限",
            "options": [
                {"id": "captain_lead", "text": "机长主导操作，副驾驶协助监控", "correct": True},
                {"id": "avoid_complex", "text": "避免复杂操作，简化流程", "correct": True},
                {"id": "normal_ops", "text": "按标准程序分工，无需特殊考虑", "correct": False}
            ],
            "sop_data": {
                "title": "机组资源管理 (CRM)",
                "content": [
                    "副驾驶经验水平: 新手 (120 小时)",
                    "当前条件: 雷暴威胁环境",
                    "风险: ⚠️ 高负荷环境",
                    "建议:",
                    "- 机长主导决策和操作",
                    "- 明确分工和沟通",
                    "- 降低任务复杂度"
                ]
            },
            "scores": {
                "pf_correct_pm_approve": 15,
                "pf_correct_pm_reject": -5,
                "pf_wrong_pm_approve": -20,
                "pf_wrong_pm_reject": 5
            }
        }
    },
    "quiz": [
        {
            "id": "cb_avoidance",
            "type": "multiple_choice",
            "question": "VFR 飞行应至少距离积雨云多远？",
            "options": [
                {"id": "a", "text": "5 英里", "correct": False},
                {"id": "b", "text": "10 英里", "correct": False},
                {"id": "c", "text": "20 英里", "correct": True},
                {"id": "d", "text": "不需要避让", "correct": False}
            ],
            "explanation": "应至少保持20英里距离以避免湍流和风切变"
        },
        {
            "id": "windshear_response",
            "type": "multiple_choice",
            "question": "遭遇低空风切变时的首要操作是？",
            "options": [
                {"id": "a", "text": "立即减速", "correct": False},
                {"id": "b", "text": "全油门复飞", "correct": True},
                {"id": "c", "text": "保持当前状态", "correct": False},
                {"id": "d", "text": "收起襟翼", "correct": False}
            ],
            "explanation": "风切变首要动作：全油门复飞，保持最大性能"
        },
        {
            "id": "thunderstorm_hazard",
            "type": "multiple_choice",
            "question": "雷暴云内最危险的现象是？",
            "options": [
                {"id": "a", "text": "降雨", "correct": False},
                {"id": "b", "text": "严重湍流和风切变", "correct": True},
                {"id": "c", "text": "能见度降低", "correct": False},
                {"id": "d", "text": "闪电", "correct": False}
            ],
            "explanation": "严重湍流和风切变可能导致飞机失控"
        }
    ]
}

# ============================================================================
# 场景库和选择器
# ============================================================================
ALL_SCENARIOS = [SCENARIO_1, SCENARIO_2, SCENARIO_3]

# 全局变量存储当前选择的场景
_current_scenario = None

def select_scenario(scenario_index=None):
    """
    选择一个场景

    Args:
        scenario_index: 指定场景索引(0-2)，None 则随机选择

    Returns:
        选中的场景字典
    """
    global _current_scenario

    if scenario_index is not None:
        if 0 <= scenario_index < len(ALL_SCENARIOS):
            _current_scenario = ALL_SCENARIOS[scenario_index]
        else:
            raise ValueError(f"场景索引必须在 0-{len(ALL_SCENARIOS)-1} 之间")
    else:
        _current_scenario = random.choice(ALL_SCENARIOS)

    return _current_scenario

def get_current_scenario():
    """获取当前场景，如果未选择则随机选择一个"""
    global _current_scenario
    if _current_scenario is None:
        select_scenario()
    return _current_scenario

# ============================================================================
# 向后兼容的变量名（使用场景1作为默认值）
# ============================================================================
# 默认使用场景1，保持向后兼容
PHASE1_DATA = SCENARIO_1["data"]
PHASE1_THREATS = SCENARIO_1["threats"]
EMERGENCY_QUIZ = SCENARIO_1["quiz"]

def update_phase1_data_from_scenario(scenario):
    """
    从指定场景更新全局 PHASE1_DATA、PHASE1_THREATS、EMERGENCY_QUIZ 变量

    注意：由于 Python 的变量作用域特性，这个函数会更新模块级全局变量

    Args:
        scenario: 场景字典（SCENARIO_1, SCENARIO_2 或 SCENARIO_3）
    """
    global PHASE1_DATA, PHASE1_THREATS, EMERGENCY_QUIZ
    PHASE1_DATA = scenario["data"]
    PHASE1_THREATS = scenario["threats"]
    EMERGENCY_QUIZ = scenario["quiz"]
    return scenario

def select_and_apply_scenario(scenario_index=None):
    """
    选择场景并应用到全局变量

    Args:
        scenario_index: 指定场景索引(0-2)，None 则随机选择

    Returns:
        选中的场景字典
    """
    scenario = select_scenario(scenario_index)
    update_phase1_data_from_scenario(scenario)
    return scenario
