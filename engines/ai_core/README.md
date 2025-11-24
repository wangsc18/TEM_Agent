# AI核心模块架构文档

## 📐 设计理念

基于**双过程理论 (Dual Process Theory)**，将AI决策分为三个清晰的层次：

```
观察层 (Observation)  →  策略层 (Strategy)  →  执行层 (Action)
   ↓                      ↓                     ↓
不用LLM，纯数据提取    Slow Engine深度推理    Fast Engine快速响应
```

---

## 📁 文件结构

```
engines/ai_core/
├── __init__.py          # 模块导出接口
├── models.py            # 数据结构（Observation, Strategy, Action）
├── observer.py          # 观察层：StateObserver
├── strategies.py        # 策略层：StrategyGenerator (Slow Engine)
├── executors.py         # 执行层：ActionExecutor (Fast Engine)
├── utils.py             # 工具函数
└── README.md            # 本文档
```

---

## 🧩 核心组件

### 1. **models.py** - 数据结构

定义三个标准化数据模型：

#### `Observation` - 观察结果
```python
Observation(
    phase: str,          # 当前阶段 (phase1/phase2/phase3)
    role: str,           # AI角色 (PF/PM)
    context: Dict        # 上下文信息
)
```

#### `Strategy` - 策略输出
```python
Strategy(
    thinking: str,              # 思考过程
    assessment: Dict,           # 情况评估
    recommendation: Dict,       # 策略建议
    next_focus: str             # 下一步关注点
)
```

#### `Action` - 动作输出
```python
Action(
    action_type: str,           # 动作类型
    params: Dict,               # 动作参数
    execute_immediately: bool   # 是否立即执行
)
```

---

### 2. **observer.py** - 观察层

**特点**：**不使用LLM**，纯数据提取

```python
class StateObserver:
    def observe(self, room_state: Dict) -> Observation:
        """根据当前阶段提取关键信息"""
        pass
    
    def _observe_phase1(self, room_state: Dict) -> Dict:
        """Phase 1: 威胁识别状态"""
        pass
    
    def _observe_phase2(self, room_state: Dict) -> Dict:
        """Phase 2: 仪表监控状态"""
        pass
    
    def _observe_phase3(self, room_state: Dict) -> Dict:
        """Phase 3: QRH检查单状态"""
        pass
```

**职责**：
- 提取当前阶段信息
- 提取已处理的威胁
- 提取仪表状态
- 提取检查单进度

---

### 3. **strategies.py** - 策略层 (Slow Engine)

**特点**：使用**大模型深度推理**，生成策略建议

```python
class StrategyGenerator:
    def __init__(self, slow_engine, role, config):
        """初始化Slow Engine"""
        pass
    
    async def strategize_pm_verify(
        self, 
        observation: Observation,
        pf_decision_data: Dict
    ) -> Strategy:
        """PM验证策略思考"""
        pass
    
    # TODO: 添加更多策略方法
    # - strategize_pf_decision: PF决策策略
    # - strategize_qrh_selection: QRH选择策略
```

**职责**：
- 深度分析当前情况
- 评估风险和优先级
- 生成策略建议和理由
- 返回结构化Strategy对象

**特征**：
- 响应时间：3-6秒
- 模型：gpt-4o (大模型)
- 输出：JSON格式的Strategy

---

### 4. **executors.py** - 执行层 (Fast Engine)

**特点**：快速将策略转化为具体动作

```python
class ActionExecutor:
    def __init__(self, fast_engine, role, config):
        """初始化Fast Engine"""
        pass
    
    def execute_pm_verify(self, strategy: Strategy) -> Action:
        """根据策略生成PM验证动作"""
        pass
    
    # TODO: 添加更多执行方法
    # - execute_pf_decision: PF决策动作
    # - execute_qrh_selection: QRH选择动作
```

**职责**：
- 解析策略建议
- 转换为具体参数
- 生成Action对象

**特征**：
- 响应时间：1-3秒
- 模型：gpt-4o-mini (小模型)
- 输出：Action对象

---

### 5. **utils.py** - 工具函数

提供辅助功能：

```python
# LLM响应解析
- extract_threat_keyword()
- extract_option_id()
- extract_quiz_answer()
- extract_qrh_key()
- parse_approval()
- parse_json_response()

# 其他工具
- random_delay()
- detect_abnormal_gauges()  # 规则检测异常仪表
```

---

## 🔄 工作流程示例

### PM验证PF决策流程

```python
# 1. 观察当前状态（不用LLM）
observation = observer.observe(room_state)
# → Observation(phase="phase1", role="PM", context={...})

# 2. Slow Engine 生成策略（深度推理）
strategy = await strategy_gen.strategize_pm_verify(observation, pf_data)
# → Strategy(
#       thinking="PF选择了使用侧风起飞标准程序...",
#       assessment={"pf_approach": "积极应对", "sop_compliance": "符合"},
#       recommendation={"action": "approve", "confidence": "high"}
#    )

# 3. Fast Engine 生成动作（快速转换）
action = executor.execute_pm_verify(strategy)
# → Action(action_type="pm_verify_decision", params={"approve": True})

# 4. 执行动作（调用game_logic）
game_logic.pm_verify_decision(room, action.params['approve'], actor)
```

---

## ✨ 优势

### 🎯 清晰的职责分离
- **观察层**：只提取数据，不推理
- **策略层**：只生成策略，不执行
- **执行层**：只转换动作，不思考

### 🐛 易于调试
- 每层独立测试
- 中间结果可视化
- 错误定位精确

### 🔧 易于扩展
- 新增策略：在`strategies.py`添加方法
- 新增动作：在`executors.py`添加方法
- 新增阶段：在`observer.py`添加观察方法

### 📦 模块化
- 可单独导入使用
- 可替换不同LLM引擎
- 可复用工具函数

---

## 🚀 后续扩展计划

### Phase 1（已实现）
- ✅ PM验证PF决策（新架构）

### Phase 2（待实现）
- ⬜ PF决策威胁应对（迁移到新架构）
- ⬜ PM测试题答题（迁移到新架构）

### Phase 3（待实现）
- ⬜ 仪表监控与异常检测
- ⬜ QRH选择与检查单执行

---

## 📝 使用示例

```python
from engines.ai_core import (
    Observation, Strategy, Action,
    StateObserver, StrategyGenerator, ActionExecutor
)

# 初始化组件
observer = StateObserver(role="PM")
strategy_gen = StrategyGenerator(slow_engine, role="PM", config)
executor = ActionExecutor(fast_engine, role="PM", config)

# 完整流程
observation = observer.observe(room_state)
strategy = await strategy_gen.strategize_pm_verify(observation, data)
action = executor.execute_pm_verify(strategy)
```

---

## 🔗 相关文件

- **主入口**: `engines/ai_agent.py`
- **业务逻辑**: `game_logic.py`
- **Web后端**: `app_web.py`
- **配置文件**: `config.py`
