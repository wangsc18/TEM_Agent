# TEM双人推演模拟器 - 双模型语音交互版

基于双模型架构的航空TEM训练系统，整合实时语音交互、小模型快速响应和大模型深度分析。

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置API密钥
echo "OPENAI_API_KEY=sk-xxxxxxxxxxxxx" > .env

# 3. 运行应用
python app.py
```

---

## 项目结构

```
TEM_Agent/
├── app.py                          # 主应用入口，控制整体流程和UI布局
├── tem_simulator.py                # 无语音版本（备用）
├── TEM_simulator_voice.py          # 语音版本（备用）
├── realtime_voice_agent.py         # 实时语音代理（独立测试用）
├── realtime_voice_agent_streaming.py # 流式语音代理（独立测试用）
│
├── config.py                       # 配置文件：模型选择、TTS引擎、窗口设置
├── requirements.txt                # Python依赖清单
├── .env.example                    # 环境变量示例
│
├── engines/                        # 核心引擎模块
│   ├── voice_engine.py            # 语音交互引擎：STT→LLM→TTS完整流程
│   └── dual_model_manager.py      # 双模型管理器：协调小模型快速响应+大模型深度分析
│
├── ui/                            # 用户界面模块
│   └── panels.py                  # 三面板布局：左侧信息源、中间显示区、右侧协作区
│
├── components/                    # 可视化组件
│   └── avatar.py                  # 动态头像组件：3种角色头像及说话动画效果
│
├── data/                          # 数据层
│   ├── mock_data.py              # 模拟场景数据：OFP、天气、技术日志、NOTAM
│   └── knowledge_base.py         # 知识库管理器：加载和查询专业文档
│
└── knowledge_base/                # 专业知识文档
    ├── MEL_APU.md                # MEL条款：APU启动发电机保留
    └── Performance_Runway.md     # 起飞性能：跑道缩短影响分析
```

---

## 核心文件说明

### 主入口
- **app.py** - 主应用控制器，初始化三面板布局，管理语音引擎，处理两阶段工作流切换

### 引擎模块
- **engines/voice_engine.py** - 语音交互引擎，包含录音、语音识别(Whisper)、LLM调用(流式)、语音合成(TTS)
- **engines/dual_model_manager.py** - 双模型协调器，小模型快速响应，检测触发词后调用大模型深度分析并优化策略

### UI组件
- **ui/panels.py** - 三面板UI组件：LeftPanel(信息源按钮)、CenterPanel(信息显示)、RightPanel(威胁记录+对话区)
- **components/avatar.py** - 动态头像组件，支持3种角色(用户/AI伙伴/专家)，带说话动画效果

### 数据层
- **data/mock_data.py** - TEM训练场景模拟数据，包含飞行计划、天气、技术日志、NOTAM和动态事件
- **data/knowledge_base.py** - 知识库管理器，加载knowledge_base/目录下的专业文档，支持关键词搜索

### 知识库
- **knowledge_base/MEL_APU.md** - APU启动发电机MEL保留条款及运行限制说明
- **knowledge_base/Performance_Runway.md** - 跑道缩短情况下的起飞性能计算和威胁分析

---

## 配置说明 (config.py)

```python
SMALL_MODEL = "gpt-4o-mini"  # 快速响应模型
BIG_MODEL = "gpt-4o"          # 深度分析模型
TTS_ENGINE = "edge"           # TTS引擎：local/edge/openai
ENABLE_DUAL_MODEL = True      # 双模型开关
```

---

## 核心功能

### 双模型架构
- 小模型(gpt-4o-mini)快速响应(1-2秒)
- 检测到触发词("让我查找一下"等)后自动调用大模型
- 大模型返回专家答案并优化小模型策略

### 两阶段交互
1. **阶段一(INDIVIDUAL)**: 查看信息源→记录个人威胁→与AI伙伴对话
2. **阶段二(COLLABORATIVE)**: 显示个人威胁总结→注入动态事件→团队讨论决策

### 语音交互
- 支持语音输入(最长10秒，自动检测停顿)
- 流式显示AI回复
- 3种TTS引擎可选

---

## 许可证

MIT License
