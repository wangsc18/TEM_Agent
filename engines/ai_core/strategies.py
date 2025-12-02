#!/usr/bin/env python3
"""
策略层 - Slow Engine (System 2)

深度推理引擎，生成策略建议（思考+评估+建议）
"""
import asyncio
from typing import Dict
from .models import Observation, Strategy
from .utils import random_delay, parse_json_response


class StrategyGenerator:
    """策略生成器 - Slow Engine的核心逻辑"""

    def __init__(self, slow_engine, role: str, config: Dict):
        """
        初始化策略生成器

        Args:
            slow_engine: Slow LLM引擎
            role: AI角色 (PF or PM)
            config: 配置参数
        """
        self.slow_engine = slow_engine
        self.role = role
        self.slow_thinking_time = config.get('slow_thinking_time', (3, 6))
        self.strategic_context = {}  # 策略上下文

    async def strategize_pm_verify(self, observation: Observation, pf_decision_data: Dict) -> Strategy:
        """
        PM验证PF决策的策略思考

        Args:
            observation: 当前观察结果
            pf_decision_data: PF的决策数据

        Returns:
            Strategy: 策略建议
        """
        print(f"[SlowEngine] PM验证策略思考...")

        sop_text = "\n".join(pf_decision_data['sop_data']['content'])

        # 提取聊天历史
        chat_history = observation.context.get('chat_history', [])
        chat_context = ""
        if chat_history:
            chat_lines = []
            for msg in chat_history[-5:]:  # 只用最近5条消息
                chat_lines.append(f"{msg['sender']}: {msg['message']}")
            chat_context = "\n".join(chat_lines)

        prompt = f"""你是严谨的PM，需要深入分析PF的决策。

【当前情况】
PF识别的威胁: {pf_decision_data['keyword']}
PF提出的方案: {pf_decision_data['pf_decision']}

【SOP标准】
{pf_decision_data['sop_data']['title']}
{sop_text}

【机组通信记录】
{chat_context if chat_context else "(暂无通信记录)"}

【你的任务】
评估"PF选择的应对方案是否合理"。注意：不是评估"是否应该继续飞行"，而是评估"PF的应对方案本身"。

【分析框架】
1. PF是否识别出了威胁？
2. PF选择的方案是"积极应对"还是"忽视威胁"？
3. 该方案是否符合SOP？
4. 综合机组通信内容进行判断

【判断逻辑】
✅ 应该同意：PF选择"使用XX标准程序"、"执行XX检查单"、"咨询XX" → 说明在积极应对
❌ 应该驳回：PF选择"忽略威胁"、"不采取行动"、违反SOP的操作

返回JSON格式（必须严格遵守格式）：
{{
    "thinking": "你的详细思考过程",
    "assessment": {{
        "threat_recognized": true/false,
        "pf_approach": "积极应对/忽视威胁/不确定",
        "sop_compliance": "符合/不符合/部分符合"
    }},
    "recommendation": {{
        "action": "approve/reject",
        "confidence": "high/medium/low",
        "reasoning": "推荐理由"
    }},
    "next_focus": "下一步关注点",
    "explanation": "向机组成员解释你决策的简短消息（20-50字，口语化，像真正的PM说话）"
}}
"""

        await asyncio.sleep(random_delay(*self.slow_thinking_time))

        try:
            response = await self.slow_engine.chat(prompt, stream=False)
            analysis = parse_json_response(response)

            # 构建 Strategy 对象
            strategy = Strategy(
                thinking=analysis.get('thinking', ''),
                assessment=analysis.get('assessment', {}),
                recommendation=analysis.get('recommendation', {}),
                next_focus=analysis.get('next_focus', ''),
                explanation=analysis.get('explanation', '')
            )

            print(f"[SlowEngine] 策略建议: {strategy.recommendation.get('action', 'N/A')}")
            print(f"[SlowEngine] 思考: {strategy.thinking[:50]}...")
            print(f"[SlowEngine] 解释: {strategy.explanation}")

            # 保存到上下文
            self.strategic_context['pm_verify_strategy'] = strategy.to_dict()

            return strategy

        except Exception as e:
            print(f"[SlowEngine] 错误: {e}")
            # 返回默认策略（同意）
            return Strategy(
                thinking="分析出错，采用默认策略",
                assessment={"error": True},
                recommendation={"action": "approve", "confidence": "low", "reasoning": "默认同意"},
                next_focus="",
                explanation="方案分析完成，同意执行"
            )

    async def strategize_pf_decision(self, observation: Observation, threat_data: Dict) -> Strategy:
        """
        PF决策威胁应对方案的策略思考

        Args:
            observation: 当前观察结果
            threat_data: 威胁详细数据（包含选项列表）

        Returns:
            Strategy: 策略建议（包含推荐选项ID）
        """
        print(f"[SlowEngine] PF决策策略思考...")

        # 提取威胁信息
        keyword = threat_data.get('keyword', 'Unknown')
        description = threat_data.get('description', '')
        options = threat_data.get('options', [])
        sop_data = threat_data.get('sop_data', {})

        # 从实际数据中提取选项ID列表（关键修复）
        actual_option_ids = [opt['id'] for opt in options]
        option_ids_hint = " / ".join(actual_option_ids)

        # 构建选项文本
        options_text = "\n".join([
            f"{opt['id']}: {opt['text']}"
            for opt in options
        ])

        # 提取SOP参考
        sop_text = ""
        if sop_data:
            sop_text = f"{sop_data.get('title', '')}\n"
            sop_text += "\n".join(sop_data.get('content', []))

        # 提取聊天历史
        chat_history = observation.context.get('chat_history', [])
        chat_context = ""
        if chat_history:
            chat_lines = []
            for msg in chat_history[-5:]:  # 最近5条
                chat_lines.append(f"{msg['sender']}: {msg['message']}")
            chat_context = "\n".join(chat_lines)

        prompt = f"""你是经验丰富的PF，面对威胁需要做出决策。

【威胁识别】
威胁关键词: {keyword}
威胁描述: {description}

【可选方案】
{options_text}

【SOP参考】
{sop_text if sop_text else "(无具体SOP参考)"}

【机组通信记录】
{chat_context if chat_context else "(暂无通信记录)"}

【你的任务】
深度分析每个应对方案，选择最合适的选项。

【分析框架】
1. **安全性**: 哪个方案最安全？
2. **SOP合规性**: 哪个方案符合标准操作程序？
3. **执行可行性**: 哪个方案在当前情况下可行？
4. **风险评估**: 每个方案的潜在风险是什么？

【决策原则】
✅ 优先选择符合SOP的积极应对方案
✅ 避免选择"忽略威胁"或"不采取行动"的选项
✅ 考虑当前环境和机组状态

【重要】你必须从以下实际选项ID中选择一个：{option_ids_hint}

返回JSON格式（必须严格遵守格式）：
{{
    "thinking": "详细分析每个选项的优劣",
    "assessment": {{
        "threat_severity": "high/medium/low",
        "time_pressure": "urgent/moderate/low",
        "best_option_id": "推荐的选项ID（从 {option_ids_hint} 中选择）"
    }},
    "recommendation": {{
        "action": "推荐的选项ID（从 {option_ids_hint} 中精确选择，不要自己编造）",
        "confidence": "high/medium/low",
        "reasoning": "选择该方案的理由"
    }},
    "next_focus": "执行该方案后需要关注的事项",
    "explanation": "向机组成员简短解释你的决策（20-50字，口语化）"
}}
"""

        await asyncio.sleep(random_delay(*self.slow_thinking_time))

        try:
            response = await self.slow_engine.chat(prompt, stream=False)
            analysis = parse_json_response(response)

            # 构建 Strategy 对象
            strategy = Strategy(
                thinking=analysis.get('thinking', ''),
                assessment=analysis.get('assessment', {}),
                recommendation=analysis.get('recommendation', {}),
                next_focus=analysis.get('next_focus', ''),
                explanation=analysis.get('explanation', '')
            )

            recommended_option = strategy.recommendation.get('action', '')

            # 验证返回的选项ID是否有效
            if recommended_option not in actual_option_ids:
                print(f"[SlowEngine] 警告: LLM返回的选项ID '{recommended_option}' 不在有效列表中 {actual_option_ids}")
                # 降级处理：选择第一个选项
                recommended_option = actual_option_ids[0]
                strategy.recommendation['action'] = recommended_option
                print(f"[SlowEngine] 降级为第一个选项: {recommended_option}")

            print(f"[SlowEngine] 推荐方案: {recommended_option}")
            print(f"[SlowEngine] 思考: {strategy.thinking[:50]}...")
            print(f"[SlowEngine] 解释: {strategy.explanation}")

            # 保存到上下文
            self.strategic_context['pf_decision_strategy'] = strategy.to_dict()

            return strategy

        except Exception as e:
            print(f"[SlowEngine] 错误: {e}")
            import traceback
            traceback.print_exc()

            # 返回默认策略（选择第一个选项）
            default_option = options[0]['id'] if options else 'option_a'
            return Strategy(
                thinking="分析出错，采用默认策略",
                assessment={"error": True},
                recommendation={"action": default_option, "confidence": "low", "reasoning": "默认选择"},
                next_focus="",
                explanation="已做出决策，请PM验证"
            )

    # TODO: 添加更多策略方法
    # - strategize_qrh_selection: QRH选择策略
    # - strategize_gauge_monitoring: 仪表监控策略

    async def strategize_gauge_analysis(self, gauge_info: Dict) -> Strategy:
        """
        Phase 2: 仪表点击分析策略（使用Slow Engine）

        Args:
            gauge_info: 仪表信息（包含知识库）

        Returns:
            Strategy: 分析结果
        """
        print(f"[SlowEngine] 仪表分析策略思考...")

        gauge_name = gauge_info.get('gauge_name', '未知仪表')
        current_value = gauge_info.get('current_value', 0)
        knowledge = gauge_info.get('knowledge', {})

        prompt = f"""你是一名经验丰富的C172飞行教员，学员刚刚点击了"{knowledge.get('full_name', gauge_name)}"仪表。

【当前状态】
- 仪表: {knowledge.get('full_name', gauge_name)}
- 当前数值: {current_value} {knowledge.get('unit', '')}
- 正常范围: {knowledge.get('normal_range', '未知')}

【任务】
用80字以内，简洁专业地回答：
1. 当前数值是否正常
2. 如果出现异常，典型征兆是什么样的
3. 可能对应的威胁类型
4. 给出监控建议

风格要求：简洁、专业、像真正的飞行教员，不要啰嗦。"""

        await asyncio.sleep(random_delay(*self.slow_thinking_time))

        try:
            response = await self.slow_engine.chat(prompt, stream=False)

            # 构建Strategy对象
            strategy = Strategy(
                thinking="仪表分析完成",
                assessment={},
                recommendation={"analysis": response},
                next_focus="",
                explanation=response  # 分析结果直接作为explanation
            )

            print(f"[SlowEngine] 仪表分析完成: {response[:50]}...")
            return strategy

        except Exception as e:
            print(f"[SlowEngine] 仪表分析错误: {e}")
            return Strategy(
                thinking="分析失败",
                assessment={},
                recommendation={},
                next_focus="",
                explanation=f"{gauge_name}已标记。如发现异常，请及时报告。"
            )

    async def strategize_qrh_explanation(self, qrh_key: str, alert_desc: str, qrh_knowledge: Dict) -> Strategy:
        """
        Phase 2: QRH选择解释策略（使用Slow Engine）

        Args:
            qrh_key: QRH键名
            alert_desc: 警报描述
            qrh_knowledge: QRH知识库

        Returns:
            Strategy: 解释结果
        """
        print(f"[SlowEngine] QRH解释策略思考...")

        prompt = f"""你是C172飞行教员，刚选择了"{qrh_knowledge.get('title', qrh_key)}"应急程序。

【情况】
- 警报: {alert_desc}
- 选择的QRH: {qrh_knowledge.get('title', qrh_key)}
- 程序目标: {qrh_knowledge.get('goal', '未知')}
- 核心步骤: {qrh_knowledge.get('key_steps', '未知')}

【任务】
用60字以内，像真正的教员一样，简要解释：
1. 为什么这是正确的选择
2. 这个程序的核心目标是什么

要求：简洁、专业、教学性强。"""

        await asyncio.sleep(random_delay(2, 4))

        try:
            response = await self.slow_engine.chat(prompt, stream=False)

            strategy = Strategy(
                thinking="QRH解释完成",
                assessment={},
                recommendation={"explanation": response},
                next_focus="",
                explanation=response
            )

            print(f"[SlowEngine] QRH解释完成: {response[:50]}...")
            return strategy

        except Exception as e:
            print(f"[SlowEngine] QRH解释错误: {e}")
            return Strategy(
                thinking="解释失败",
                assessment={},
                recommendation={},
                next_focus="",
                explanation=""
            )
