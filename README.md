# C172 TEM 训练器 V2 - 多人协作训练系统

基于 Web 的航空 TEM (Threat and Error Management) 双人协作训练系统，支持本地/远程联网训练，实时监控飞行状态，征兆检测与多事件队列，完整操作日志记录。

---

## 核心特性

✅ **双人角色分工** - PF（操纵飞行员）识别威胁并决策，PM（监控飞行员）验证与监督
✅ **三阶段训练流程** - 起飞前威胁管理 → 空中征兆检测 → 应急程序执行
✅ **征兆检测系统** - 仪表在故障警报前 15-30 秒显示异常征兆，提前发现可获额外分数
✅ **多事件队列** - 一次飞行中顺序触发 2-3 个故障事件，模拟真实复杂场景
✅ **7 个飞行仪表** - SPD / ALT / OIL P / RPM / FUEL / VAC / AMPS，实时平滑更新
✅ **操作日志记录** - 自动记录所有操作和时间点（JSONL 格式），支持后续统计分析
✅ **远程联网支持** - 通过房间号隔离训练，支持多组同时进行

---

## 快速开始

### 本地训练模式

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动服务器
python app_web.py

# 3. 打开两个浏览器窗口
# 窗口1: http://127.0.0.1:5001 (PF 角色)
# 窗口2: http://127.0.0.1:5001 (PM 角色)
# 输入相同的房间号（如：101）即可配对训练
```

### 远程联网模式

```bash
# 1. 启动服务器
python app_web.py

# 2. 启动 ngrok（新终端）
ngrok http 5001

# 3. 分享 ngrok 生成的公网链接
# 例如: https://xxxx-xxxx-xxxx.ngrok-free.app
# 远程学员通过此链接即可加入训练
```

---

## 项目结构

```
TEM_Agent/
├── app_web.py                      # Flask-SocketIO 主应用服务器
├── requirements.txt                # Python 依赖清单
├── config.py                       # 配置文件
│
├── templates/
│   └── index.html                  # Web 前端界面（单页应用）
│
├── data/                           # 数据配置模块
│   ├── phase1_data.py              # Phase 1 威胁库与测试题
│   ├── phase2_scenarios.py         # Phase 2 简单场景（备用）
│   ├── phase2_advanced.py          # Phase 2 高级多事件场景
│   └── qrh_library.py              # QRH 检查单库（7 个检查单）
│
├── logs/                           # 操作日志目录（自动创建）
│   └── session_*.jsonl             # 每次训练的日志文件（JSONL格式）
│
├── engines/                        # 引擎模块（保留用于未来扩展）
│   ├── realtime_voice_engine.py   # 实时语音引擎
│   ├── text_llm_engine.py         # 文本LLM引擎
│   └── mini_tts_engine.py         # Mini TTS引擎
│
└── ui/                            # UI模块（保留用于桌面版）
    └── panels.py                   # 面板组件
```

---

## 训练流程详解

### Phase 1: 起飞前威胁管理（Pre-flight TEM）

**目标**: PF 识别威胁并决策，PM 验证决策的正确性

#### 工作流程

1. **信息源呈现**
   - METAR 天气报告：`CYXH 211800Z 24015G25KT 15SM FEW030`
   - 飞机状态：`C-GABC Fuel: Full Snags: Landing_Light_U/S`
   - 机组信息：`Pilot_A: Rest_8hrs Pilot_B: Recovering_from_Cold`

2. **PF 识别威胁**（点击关键词）
   - `24015G25KT` - 阵风 25 节（可能超出侧风限制）
   - `Landing_Light_U/S` - 着陆灯故障（需查阅 MEL）
   - `Recovering_from_Cold` - 身体恢复中（IMSAFE 检查）

3. **PF 提出决策方案**
   - 弹出模态框，显示 3 个选项
   - 例如："使用侧风起飞标准程序" / "等待风况改善" / "忽略侧风影响"

4. **PM 验证决策**
   - 查看 SOP 参考数据（如 C172 侧风限制：15 节）
   - 判断 PF 方案是否合理
   - 点击"同意方案"或"驳回方案"

#### 评分规则

| PF 决策 | PM 验证 | 分数变化 | 说明 |
|---------|---------|----------|------|
| ✅ 正确 | ✅ 同意 | **+15** | 最佳结果 |
| ✅ 正确 | ❌ 驳回 | **-5**  | PM 判断失误 |
| ❌ 错误 | ✅ 同意 | **-20** | 严重：双人共同失误 |
| ❌ 错误 | ❌ 驳回 | **+5**  | PM 成功发现错误 |

5. **紧急预案知识测试**（PM 操作）
   - 3 道选择题，测试紧急程序记忆
   - 例如："离地后引擎失效且高度低于多少英尺，严禁掉头？"
   - ✅ 答对 +10 分，❌ 答错 -5 分

---

### Phase 2: 空中征兆检测与多事件队列

**目标**: 监控 7 个仪表，通过征兆提前发现故障，处理多个连续事件

#### 仪表系统

| 仪表 | 说明 | 正常范围 | 量程 |
|------|------|----------|------|
| **SPD** | 空速 (Airspeed) | 100-110 KIAS | 40-200 KIAS |
| **ALT** | 高度 (Altitude) | 5400-5600 FT | 0-10000 FT |
| **OIL P** | 滑油压力 (Oil Pressure) | 75-85 PSI | 0-120 PSI |
| **RPM** | 发动机转速 | 2350-2450 RPM | 0-3000 RPM |
| **FUEL** | 燃油量 (平均值) | 20-30 GAL | 0-50 GAL |
| **VAC** | 真空压力 (Vacuum) | 4.5-5.5 IN HG | 0-7 IN HG |
| **AMPS** | 电流表 (Ammeter) | -2 to +2 AMPS | -30 to +30 AMPS |

#### 征兆检测系统

**核心机制**：故障分为三个阶段

1. **征兆阶段** (Precursor Phase)
   - 时间：警报前 15-30 秒
   - 表现：仪表开始异常波动/缓慢变化
   - 操作：点击异常仪表标记监控
   - 奖励：**+20 分**（提前发现奖励）

2. **警报阶段** (Alert Phase)
   - 时间：系统警报触发
   - 表现：右上角红色闪烁告警框
   - 操作：选择对应 QRH 检查单
   - 奖励：**+5 分**（反应奖励）

3. **处置阶段** (Response Phase)
   - 操作：双方完成检查单项目
   - 效果：告警框清除，故障稳定
   - 奖励：QRH 选择正确 **+20 分**

#### 多事件场景示例

**场景 1: 常规巡航 - 双重故障** (180秒)

```
T+0s:    起飞，所有仪表正常
T+20s:   [征兆] FUEL 左右油箱指示差距拉大
T+35s:   [警报] ⚠️ FUEL IMBALANCE - 15 GAL DIFFERENCE
T+60s:   [事件结束] 燃油不平衡已稳定

--- 间隔期（40秒正常飞行）---

T+100s:  [征兆] VAC 真空压力下降，姿态仪摇摆
T+115s:  [警报] ⚠️ VACUUM SYSTEM FAILURE
T+150s:  [事件结束] 真空系统失效已稳定

--- 收尾期（30秒正常飞行）---

T+180s:  场景模拟结束 → 最终结算
```

**场景 2: 冬季运行 - 化油器结冰与电气故障** (180秒)

```
T+25s:   [征兆] RPM 逐渐降低 (2400→2100)
T+40s:   [警报] ⚠️ CARBURETOR ICING SUSPECTED
T+70s:   [事件结束] 化油器结冰已稳定

T+105s:  [征兆] AMPS 显示放电 (0→-12)
T+120s:  [警报] ⚠️ ALTERNATOR FAILURE - BATTERY ONLY
T+160s:  [事件结束] 交流发电机失效已稳定

T+180s:  场景模拟结束 → 最终结算
```

**场景 3: 关键情况 - 滑油压力丧失** (90秒)

```
T+15s:   [征兆] OIL P 指针下降并抖动
T+30s:   [警报] ❌ OIL PRESSURE LOST - EMERGENCY
T+80s:   [事件结束] 滑油压力丧失已稳定

T+90s:   场景模拟结束 → 最终结算
```

#### 技术特性

- **平滑仪表更新**：0.1 秒更新间隔 + 线性插值算法
- **正常飞行波动**：所有仪表持续 ±1% 随机波动
- **燃油正常消耗**：每秒 0.05 加仑
- **征兆视觉反馈**：监控的仪表显示蓝色发光边框
- **事件间隔期**：事件结束后仪表自动恢复正常

---

### Phase 3: 应急程序执行

**目标**: 选择正确的 QRH 检查单并完成项目

#### 可用 QRH 检查单

| QRH | 场景 | 检查单项目数 |
|-----|------|--------------|
| 🔥 **ENGINE FIRE** | 空中引擎起火 | 5 项 |
| 🛢️ **LOW OIL PRESSURE** | 滑油压力丧失 | 3 项 |
| ⚡ **ELECTRICAL FIRE** | 电气火灾 | 4 项 |
| ❄️ **CARBURETOR ICING** | 化油器结冰 | 4 项 |
| ⚖️ **FUEL IMBALANCE** | 燃油不平衡 | 4 项 |
| 🌀 **VACUUM FAILURE** | 真空系统失效 | 4 项 |
| 🔋 **ALTERNATOR FAILURE** | 交流发电机失效 | 5 项 |

#### 工作流程

1. **QRH 决策**
   - Phase 2 期间随时可选择 QRH
   - ✅ 选择正确 **+20 分**
   - ❌ 选择错误 **-20 分**
   - ⚠️ 同一 QRH 只能使用一次

2. **检查单执行**
   - 双方协同完成检查单项目
   - 点击项目完成勾选
   - 所有项目完成后面板关闭

3. **继续监控**
   - 完成检查单后，告警框恢复 "SYSTEM NORMAL"
   - 继续 Phase 2，等待下一个事件
   - 可选择其他 QRH 应对新威胁

4. **最终结算**
   - Phase 2 的 duration 时间结束后触发
   - 显示总分和评价
   - \> 40 分: **Passed** ✅
   - ≤ 40 分: **Debrief Required** ⚠️

---

## 操作日志系统

### 自动记录内容

每次训练自动生成 `logs/session_<房间>_<时间戳>.jsonl`

**Phase 1 日志**:
- `user_joined` - 用户加入
- `phase_started` - 阶段开始
- `pf_identify_threat` - PF 识别威胁
- `pf_submit_decision` - PF 提交决策
- `pm_verify_decision` - PM 验证决策
- `quiz_answer_submitted` - 测试题提交
- `ready_for_phase2` - 准备进入 Phase 2

**Phase 2 日志**:
- `scenario_selected` - 场景抽取
- `monitor_gauge` - 仪表监控标记
- `precursor_detected` - 征兆检测成功
- `event_alert` - 事件警报触发
- `alert_reaction` - 警报反应
- `event_ended` - 事件结束

**Phase 3 日志**:
- `select_qrh` - QRH 选择
- `check_item` - 检查单项目完成
- `checklist_complete` - 检查单完成
- `mission_complete` - 训练完成

### 日志格式（JSONL）

```json
{
  "timestamp": "2025-11-21T14:23:45.123",
  "elapsed_time": 125.3,
  "room": "101",
  "username": "Pilot_A",
  "role": "PF",
  "action": "precursor_detected",
  "details": {
    "event_id": "carb_ice",
    "event_name": "化油器结冰",
    "gauge": "rpm",
    "score_gain": 20,
    "elapsed_time": 125.3
  },
  "phase": "phase2",
  "score": 75
}
```

### 日志用途

- 📊 **训练复盘**: 分析决策时间、操作序列、反应速度
- 📈 **绩效评估**: 统计征兆检测成功率、QRH 选择准确率
- 🔬 **研究数据**: CRM 研究、TEM 效果分析、认知负荷研究
- 📉 **数据可视化**: 使用 Python/R 分析 JSONL 文件

---

## 技术架构

### 后端技术栈

- **Flask** 2.3+ - Web 框架
- **Flask-SocketIO** 5.3+ - WebSocket 实时通信
- **eventlet** 0.33+ - 异步事件驱动
- **Python** 3.8+ - 编程语言

### 前端技术栈

- **Bootstrap 5.1** - 响应式 UI 框架
- **Socket.IO Client** 4.0 - WebSocket 客户端
- **CSS3 Animations** - 仪表动画、进度条
- **Vanilla JavaScript** - 原生 JS（无依赖）

### 核心技术实现

#### 1. 征兆生成算法 (data/phase2_advanced.py:192-256)

```python
def generate_precursor_value(gauge, pattern, elapsed_time):
    """
    根据波动模式生成征兆仪表数值

    - fluctuate_down: 波动下降（抖动 + 趋势下降）
    - gradual_drop: 缓慢下降（线性下降）
    - asymmetric: 不对称（燃油左右油箱消耗速度不同）
    - discharge: 放电（电流表逐渐加深放电）
    """
```

#### 2. 事件队列系统 (app_web.py:526-708)

```python
def run_sim_loop(room):
    """
    Phase 2 高级模拟循环
    - 每 0.1 秒更新所有仪表（基准值 + 1% 波动）
    - 在征兆阶段覆盖异常值
    - 在事件结束时自动恢复正常
    - 支持多事件顺序触发
    """
```

#### 3. 平滑进度条 (index.html:632-668)

```javascript
// 仪表指针角度映射（-135° 到 +135°）
document.getElementById('nd-rpm').style.transform =
    `rotate(${(data.rpm) * (270 / 3000) - 135}deg)`;
```

#### 4. 房间隔离机制 (app_web.py:82-159)

```python
rooms = {
    "101": {
        "users": {...},
        "score": 75,
        "event_queue": [...],
        "monitored_gauges": {...},
        "used_qrh": {...}
    }
}
```

---

## 配置与扩展

### 服务器配置 (app_web.py:689-691)

```python
socketio.run(app,
    debug=True,
    use_reloader=False,
    allow_unsafe_werkzeug=True,
    host='0.0.0.0',  # 允许外部访问
    port=5001        # 服务端口
)
```

### 添加新的场景 (data/phase2_advanced.py:10-132)

```python
MULTI_EVENT_SCENARIOS = {
    "new_scenario": {
        "name": "场景名称",
        "description": "场景描述",
        "duration": 180,  # 总时长（秒）
        "acceptable_qrh": ["qrh_key1", "qrh_key2"],  # 可接受的 QRH
        "events": [
            {
                "id": "event_1",
                "name": "事件名称",
                "precursor_start": 20,   # 征兆开始（秒）
                "alert_start": 35,       # 警报开始（秒）
                "event_end": 60,         # 事件结束（秒）
                "precursor": {
                    "gauge": "rpm",      # 仪表ID
                    "pattern": "gradual_drop",  # 波动模式
                    ...
                },
                "alert": {
                    "type": "warning",
                    "message": "⚠️ 警报消息"
                },
                "detection_score": 20,  # 征兆检测分数
                "reaction_score": 5     # 警报反应分数
            }
        ]
    }
}
```

### 添加新的 QRH (data/qrh_library.py:6-35)

```python
QRH_LIBRARY = {
    "new_qrh": {
        "title": "NEW PROCEDURE",
        "items": [
            "Step 1 - ACTION",
            "Step 2 - ACTION",
            "Step 3 - ACTION"
        ]
    }
}
```

---

## 依赖清单

```
Flask==2.3.3
Flask-SocketIO==5.3.4
eventlet==0.33.3
python-engineio==4.7.1
python-socketio==5.9.0
```

---

## 常见问题

### Q: 如何修改场景时长？

A: 编辑 `data/phase2_advanced.py`，修改 `duration` 参数（单位：秒）

### Q: 如何添加第三个用户（观察员）？

A: 修改 `app_web.py:122` 的房间人数限制：`if len(rooms[room]['users']) >= 3:`

### Q: 日志文件太大怎么办？

A: 每次训练生成一个新文件，可以定期归档 `logs/` 目录

### Q: 如何禁用征兆检测功能？

A: 修改 `app_web.py:606`，注释掉征兆检测分数逻辑

---

## 开发路线图

- [ ] 添加语音通信功能（WebRTC）
- [ ] 实时协作光标显示
- [ ] 训练录像回放功能
- [ ] 自动生成训练报告（PDF）
- [ ] 教员监控面板
- [ ] 多语言支持（英文/中文）

---

## 许可证

MIT License
