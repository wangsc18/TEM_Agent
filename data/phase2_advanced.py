"""
Phase 2 升级版 - 征兆系统与事件队列
Precursor Detection & Event Queue System
"""

# ==========================================
# 1. 多重事件场景库
# ==========================================

MULTI_EVENT_SCENARIOS = {
    "routine_flight": {
        "name": "常规巡航 - 双重故障",
        "description": "看似平静的巡航中遭遇燃油不平衡和真空系统故障",
        "duration": 180,  # 总时长3分钟
        "acceptable_qrh": ["fuel_imbalance", "vacuum_failure"],  # 接受的检查单
        "events": [
            {
                "id": "fuel_imbalance",
                "name": "燃油不平衡",
                "precursor_start": 20,   # T+20s 开始征兆
                "alert_start": 35,       # T+35s 系统警报
                "event_end": 60,         # T+60s 事件结束（故障稳定）
                "precursor": {
                    "gauge": "fuel_qty",  # 燃油量表
                    "description": "左右油箱指示差距拉大",
                    "visual": "FUEL QTY: L/R IMBALANCE DETECTED",
                    "pattern": "asymmetric"  # 不对称消耗
                },
                "alert": {
                    "type": "caution",
                    "message": "⚠️ FUEL IMBALANCE - 15 GAL DIFFERENCE"
                },
                "detection_score": 20,  # 征兆阶段发现
                "reaction_score": 5     # 警报后发现
            },
            {
                "id": "vacuum_failure",
                "name": "真空系统失效",
                "precursor_start": 100,  # T+100s 开始征兆（第一个事件结束后40秒）
                "alert_start": 115,      # T+115s 警报
                "event_end": 150,        # T+150s 事件结束
                "precursor": {
                    "gauge": "vacuum",    # 真空表
                    "description": "真空压力下降，姿态仪摇摆",
                    "visual": "ATTITUDE INDICATOR: PRECESSION",
                    "pattern": "gradual_drop"
                },
                "alert": {
                    "type": "warning",
                    "message": "⚠️ VACUUM SYSTEM FAILURE"
                },
                "detection_score": 20,
                "reaction_score": 5
            }
        ]
    },

    "critical_situation": {
        "name": "关键情况 - 滑油压力丧失",
        "description": "单一关键故障，需要立即响应",
        "duration": 90,
        "acceptable_qrh": ["low_oil_pressure"],
        "events": [
            {
                "id": "oil_pressure_loss",
                "name": "滑油压力丧失",
                "precursor_start": 15,
                "alert_start": 30,
                "event_end": 80,
                "precursor": {
                    "gauge": "oil_p",
                    "description": "滑油压力指针缓慢下降并抖动",
                    "visual": "OIL TEMP: RISING SLOWLY",
                    "pattern": "fluctuate_down"
                },
                "alert": {
                    "type": "failure",
                    "message": "❌ OIL PRESSURE LOST - EMERGENCY"
                },
                "detection_score": 25,
                "reaction_score": 5
            }
        ]
    },

    "winter_ops": {
        "name": "冬季运行 - 化油器结冰与电气故障",
        "description": "低温环境导致的复合问题",
        "duration": 180,
        "acceptable_qrh": ["carburetor_icing", "alternator_failure"],
        "events": [
            {
                "id": "carb_ice",
                "name": "化油器结冰",
                "precursor_start": 25,
                "alert_start": 40,
                "event_end": 70,
                "precursor": {
                    "gauge": "rpm",  # 转速表
                    "description": "RPM 逐渐降低，发动机声音变化",
                    "visual": "ENGINE: POWER LOSS DETECTED",
                    "pattern": "gradual_drop"
                },
                "alert": {
                    "type": "caution",
                    "message": "⚠️ CARBURETOR ICING SUSPECTED"
                },
                "detection_score": 20,
                "reaction_score": 5
            },
            {
                "id": "alternator_failure",
                "name": "交流发电机失效",
                "precursor_start": 105,  # 第一个事件结束后35秒
                "alert_start": 120,
                "event_end": 160,
                "precursor": {
                    "gauge": "ammeter",  # 电流表
                    "description": "电流表显示放电，电压下降",
                    "visual": "ALTERNATOR OUT LIGHT FLICKERING",
                    "pattern": "discharge"
                },
                "alert": {
                    "type": "warning",
                    "message": "⚠️ ALTERNATOR FAILURE - BATTERY ONLY"
                },
                "detection_score": 20,
                "reaction_score": 5
            }
        ]
    }
}

# ==========================================
# 2. 仪表基准值与监控配置
# ==========================================

GAUGE_CONFIGS = {
    "spd": {
        "name": "空速 (Airspeed)",
        "baseline": 105,
        "normal_range": [100, 110],
        "unit": "KIAS"
    },
    "alt": {
        "name": "高度 (Altitude)",
        "baseline": 5500,
        "normal_range": [5400, 5600],
        "unit": "FT"
    },
    "oil_p": {
        "name": "滑油压力 (Oil Pressure)",
        "baseline": 80,
        "normal_range": [75, 85],
        "yellow_zone": [60, 75],  # 黄区
        "red_zone": [0, 30],      # 红区
        "unit": "PSI"
    },
    "rpm": {
        "name": "发动机转速 (RPM)",
        "baseline": 2400,
        "normal_range": [2350, 2450],
        "unit": "RPM"
    },
    "fuel_qty": {
        "name": "燃油量 (Fuel Quantity)",
        "baseline_left": 25,  # 左油箱
        "baseline_right": 25, # 右油箱
        "normal_range": [20, 30],
        "unit": "GAL"
    },
    "vacuum": {
        "name": "真空压力 (Vacuum)",
        "baseline": 5.0,
        "normal_range": [4.5, 5.5],
        "yellow_zone": [3.5, 4.5],
        "unit": "IN HG"
    },
    "ammeter": {
        "name": "电流表 (Ammeter)",
        "baseline": 0,
        "normal_range": [-2, 2],  # 充电/放电小范围
        "discharge_warning": -10,
        "unit": "AMPS"
    }
}

# ==========================================
# 3. 征兆波动模式
# ==========================================

def generate_precursor_value(gauge, pattern, elapsed_time):
    """
    生成征兆阶段的仪表数值

    Args:
        gauge: 仪表ID (如 'oil_p')
        pattern: 波动模式 ('fluctuate_down', 'gradual_drop', etc.)
        elapsed_time: 从征兆开始经过的时间（秒）

    Returns:
        dict: {'value': float, 'fluctuating': bool}
    """
    import random
    import math

    config = GAUGE_CONFIGS[gauge]

    # 基础波动（微小抖动）
    base_noise = random.uniform(-1, 1)

    if pattern == "asymmetric":
        # 不对称（用于燃油）
        # 左油箱正常消耗，右油箱消耗过快
        left_consumption = 0.05  # GAL/s
        right_consumption = 0.15  # GAL/s (3倍速度)
        return {
            'left': max(0, config['baseline_left'] - elapsed_time * left_consumption),
            'right': max(0, config['baseline_right'] - elapsed_time * right_consumption),
            'fluctuating': False
        }

    # 其他模式需要 baseline
    baseline = config['baseline']

    if pattern == "fluctuate_down":
        # 波动下降：整体趋势向下，但有波动
        trend = baseline - (elapsed_time / 15) * 20  # 15秒降低20单位
        noise = random.uniform(-5, 5)
        return {
            'value': max(30, trend + noise),  # 不低于30
            'fluctuating': True
        }

    elif pattern == "gradual_drop":
        # 缓慢下降
        drop_rate = 100 / 15  # 15秒降低100 (对于RPM)
        value = baseline - (elapsed_time * drop_rate / 15)
        return {
            'value': max(baseline - 100, value + base_noise),
            'fluctuating': False
        }

    elif pattern == "discharge":
        # 放电（电流表）
        discharge_value = -5 - (elapsed_time / 15) * 10  # 逐渐加深放电
        return {
            'value': max(-20, discharge_value + base_noise),
            'fluctuating': True
        }

    else:
        return {
            'value': baseline + base_noise,
            'fluctuating': False
        }
