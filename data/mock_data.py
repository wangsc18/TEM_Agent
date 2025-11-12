#!/usr/bin/env python3
"""
模拟数据 - TEM场景背景信息
"""

MOCK_DATA = {
    "OFP": "飞行计划 (OFP):\n\n航线: ZSSS -> ZBAA\n预计油耗: 15.2吨\n备降场: ZBTJ\n巡航高度: FL350\n备注: 乘客中有医疗急救人员，需尽快抵达。",
    "WEATHER": "气象报告 (METAR & TAF):\n\nZSSS (出发地): 24015KT 9999 FEW030 25/18 Q1012 NOSIG\n\nZBAA (目的地): 20005KT 3000 BR SCT010 BKN020\nTAF ZBAA: ... TEMPO 0406 0500 FG BKN002\n(威胁: 目的地机场有雾，能见度可能在预计抵达时急剧下降至500米)",
    "TECH_LOG": "飞机技术日志:\n\n日期: 2025-10-26\n项目: APU（辅助动力单元）启动发电机故障\n状态: 已根据MEL 49-11-01保留\n影响: 地面无法使用APU供电和引气，必须依赖地面设备。",
    "NOTAMS": "航行通告 (NOTAMs):\n\nB3454/25 NOTAMN\nQ) ZSHA/QMRHW/IV/NBO/A/000/999/3114N12147E005\nA) ZSSS B) 2510250800 C) 2510251100\nE) RWY 17L/35R 因施工，可用起飞距离缩短400米。\n(威胁: 跑道长度缩短，需重新计算起飞性能)",
}

DYNAMIC_EVENT = {
    "title": "!! 紧急通知: 来自签派 !!",
    "message": "最新消息: 机上将增加一名需要担架的医疗旅客及陪同家属，总重210公斤。请立即重新计算重心和载重，并评估对起飞性能的影响。",
}
