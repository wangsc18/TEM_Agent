"""
Phase 2 数据配置
空中飞行场景库
"""

# Phase 2 飞行场景库
SCENARIO_LIBRARY = {
    "oil_loss": {
        "name": "滑油压力丧失",
        "target_qrh": "low_oil_pressure",  # 正确答案的 Key
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
