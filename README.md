# TEM 双人推演模拟器 - Web 联网训练版

基于 Web 的航空 TEM (Threat and Error Management) 双人协作训练系统，支持本地/远程联网训练，实时监控飞行状态，随机故障场景注入，完整操作日志记录。

---

## 核心特性

✅ **双人协作训练** - PF（操纵）/ PM（监控）角色分工，真实模拟机组资源管理
✅ **三阶段训练流程** - 起飞前检查 → 空中巡航监控 → 应急决策执行
✅ **随机故障场景** - 滑油压力丧失、引擎火灾、电气火灾等多种应急场景
✅ **实时可视化** - 飞行仪表、航路进度、事件打点、检查单执行
✅ **操作日志记录** - 自动记录所有操作和时间点，支持后续统计分析
✅ **远程联网支持** - 通过 ngrok 实现远程双人训练

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
```

### 远程联网模式

```bash
# 1. 启动服务器
python app_web.py

# 2. 启动 ngrok（新终端）
ngrok http 5001

# 3. 分享 ngrok 生成的公网链接
# 例如: https://xxxx-xxxx-xxxx.ngrok.io
# 远程学员通过此链接即可加入训练
```

---

## 项目结构

```
TEM_Agent/
├── app_web.py                      # 主应用服务器（Flask-SocketIO）
├── templates/
│   └── index.html                  # Web 前端界面
│
├── logs/                           # 操作日志目录
│   └── session_*.jsonl             # 每次训练的日志文件（JSONL格式）
│
├── config.py                       # 配置文件
├── requirements.txt                # Python 依赖清单
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

## 训练流程

### Phase 1: 起飞前检查（Pre-flight TEM）

**目标**: 识别并标注飞行前信息源中的潜在威胁

- 📋 查看 METAR 天气报告、飞机状态、机组信息
- 🔍 点击文本中的威胁关键词进行标注（如：大风、故障、疲劳）
- ✅ 成功标注 +10 分
- 👥 双方确认后进入 Phase 2

**示例威胁**:
- METAR: `24015G25KT` (大风阵风)
- Aircraft: `Landing_Light_U/S` (着陆灯故障)
- Pilot: `Recovering_from_Cold` (身体恢复中)

---

### Phase 2: 空中巡航（In-flight Monitoring）

**目标**: 监控飞行仪表，识别异常事件

- ✈️ **仪表监控**: 速度（SPD）、高度（ALT）、滑油压力（OIL）
- 🗺️ **航路可视化**: 飞机图标匀速移动，事件点自动标注
- ⚠️ **故障注入**: 系统随机抽取故障场景（3种可能）
  - 滑油压力丧失（Low Oil Pressure）
  - 空中引擎起火（Engine Fire）
  - 电气火灾（Electrical Fire）

**技术亮点**:
- 后端每 0.1 秒推送插值数据，实现平滑进度条
- 前端 CSS transition 配合实现流畅动画
- 事件触发时自动记录时间点和飞行数据

---

### Phase 3: 应急决策（QRH Selection & Execution）

**目标**: 选择正确的 QRH 检查单并执行

1. **QRH 决策**
   - 根据 Phase 2 的故障选择对应 QRH
   - ✅ 选择正确 +20 分
   - ❌ 选择错误 -20 分

2. **检查单执行**
   - 双方协同完成检查单项目
   - 每个项目由不同角色执行
   - 所有项目完成后结算分数

**评分标准**:
- \> 40 分: **Passed** ✅
- ≤ 40 分: **Debrief Required** ⚠️

---

## 操作日志系统

### 自动记录内容

每次训练会自动生成日志文件 `logs/session_<房间>_<时间戳>.jsonl`，记录：

- ✅ 用户加入/退出
- ✅ 阶段切换
- ✅ 威胁标注（成功/失败/重复）
- ✅ 故障场景选择
- ✅ 事件触发时间点
- ✅ QRH 选择（正确/错误）
- ✅ 检查单执行进度
- ✅ 最终分数和结果

### 日志格式（JSONL）

```json
{
  "timestamp": "2025-11-20T10:23:45.123",
  "elapsed_time": 12.5,
  "room": "SimRoom1",
  "username": "Pilot_A",
  "role": "PF",
  "action": "tag_threat_success",
  "details": {"keyword": "24015G25KT", "score_gained": 10},
  "phase": "phase1",
  "score": 10
}
```

### 日志用途

- 📊 **训练复盘**: 分析决策时间、操作序列
- 📈 **绩效评估**: 统计成功率、反应时间
- 🔬 **研究数据**: CRM 研究、TEM 效果分析

---

## 技术架构

### 后端

- **Flask**: Web 框架
- **Flask-SocketIO**: 实时双向通信
- **eventlet**: 异步事件驱动
- **JSONL**: 日志存储格式

### 前端

- **Bootstrap 5**: UI 框架
- **Socket.IO**: WebSocket 客户端
- **CSS3 Animation**: 仪表动画、进度条

### 核心技术点

1. **平滑进度条实现**
   - 后端: 线性插值算法（app_web.py:275-346）
   - 前端: CSS transition 0.15s linear

2. **实时状态同步**
   - SocketIO 房间机制
   - 事件驱动更新

3. **场景随机化**
   - 剧本库设计（app_web.py:27-59）
   - 动态 QRH 匹配

---

## 配置说明

### app_web.py 关键配置

```python
# 服务器配置
host = '0.0.0.0'  # 允许外部访问
port = 5001        # 服务端口

# 更新间隔（影响进度条平滑度）
update_interval = 0.1  # 秒
```

### 剧本库扩展

在 `SCENARIO_LIBRARY` 中添加新场景：

```python
"new_scenario": {
    "name": "场景名称",
    "target_qrh": "对应的QRH key",
    "events": [
        (时间, {飞行数据}, 类型, 描述),
        ...
    ]
}
```

---

## 许可证

MIT License
