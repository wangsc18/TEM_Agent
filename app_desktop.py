#!/usr/bin/env python3
"""
TEM双人推演模拟器 - 主应用入口
整合双模型架构 + 语音交互
"""
import tkinter as tk
import threading
import asyncio
from tkinter import messagebox

from config import *
from data.mock_data import MOCK_DATA, DYNAMIC_EVENT
from engines.realtime_voice_engine import RealtimeVoiceEngine
from engines.text_llm_engine import TextLLMEngine
from engines.mini_tts_engine import MiniTTSEngine
from ui.panels import LeftPanel, CenterPanel, RightPanel


class TEMSimulatorApp:
    """主应用控制器"""
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_GEOMETRY)

        self.current_phase = "INDIVIDUAL"

        # 对话历史和背景数据
        self.conversation_history = []
        self.background_data = MOCK_DATA
        self.personal_memo = ""

        # TEM 系统提示词
        self.base_system_prompt = """你是一名航空飞行员AI伙伴，正在与另一名飞行员进行TEM（威胁与差错管理）案例讨论。

【核心原则 - 安全第一】
在航空领域，准确性和安全性高于一切。你必须严格遵守以下规则：

❌ 绝对禁止的行为：
1. 编造或猜测专业数据（如MEL条款、性能数据、法规条款）
2. 对不确定的专业问题给出模糊或猜测性的回答
3. 回答超出你当前信息范围的专业问题

✅ 必须遵守的行为：
1. 如果问题涉及具体的专业知识（MEL、运行手册、法规、性能计算等），你必须立即回复"让我查找一下相关信息"
2. 只讨论你已知的、确定的信息
3. 用口语化、简短的方式交流（10-20字）
4. 适当使用"嗯"、"好的"等口语化表达

【何时必须说"让我查找一下相关信息"】
- 用户问到具体的MEL条款、限制、手册条款
- 涉及性能计算、重量限制等具体数值
- 需要引用法规、运行标准
- 任何你不100%确定的专业问题

【你可以直接回答的】
- 一般性的威胁识别和讨论
- 基于已知信息的观察和总结
- 对话引导和确认性问题"""

        # 初始化双引擎
        self.small_model = None  # Azure Realtime API
        self.big_model = None    # yunwu 平台
        self._init_dual_engines()

        # --- UI 面板初始化 ---
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=3)
        self.root.grid_columnconfigure(2, weight=2)

        self.left_panel = LeftPanel(self.root, self)
        self.center_panel = CenterPanel(self.root, self)
        self.right_panel = RightPanel(self.root, self)

        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.center_panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self.right_panel.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)

    def _init_dual_engines(self):
        """初始化双引擎（小模型 + 大模型）"""
        try:
            # 1. 初始化小模型（根据配置和可用性自动选择）
            self.small_model = None

            # 获取引擎优先级列表
            fallback_order = ENGINE_FALLBACK_ORDER if 'ENGINE_FALLBACK_ORDER' in globals() else ["realtime", "mini_tts"]

            # 如果 VOICE_MODE 明确指定，优先尝试该模式
            if VOICE_MODE and VOICE_MODE not in fallback_order:
                fallback_order = [VOICE_MODE] + fallback_order
            elif VOICE_MODE and VOICE_MODE in fallback_order:
                # 将指定模式移到最前面
                fallback_order = [VOICE_MODE] + [m for m in fallback_order if m != VOICE_MODE]

            print(f"[小模型] 尝试初始化引擎，优先级: {fallback_order}")

            for engine_type in fallback_order:
                if engine_type == "realtime":
                    # 尝试 Azure Realtime API
                    if AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY:
                        try:
                            self.small_model = RealtimeVoiceEngine(
                                azure_endpoint=AZURE_OPENAI_ENDPOINT,
                                azure_api_key=AZURE_OPENAI_API_KEY,
                                deployment_name=AZURE_REALTIME_DEPLOYMENT,
                                voice=AUDIO_VOICE,
                                system_prompt=self.base_system_prompt,
                                callback_on_response_start=self._on_small_model_start,
                                callback_on_transcript_delta=self._on_small_model_delta,
                                callback_on_response_done=self._on_small_model_done,
                                callback_on_error=self._on_small_model_error
                            )
                            print(f"[小模型] ✓ Azure Realtime API 初始化成功")
                            break
                        except Exception as e:
                            print(f"[小模型] ⚠️ Azure Realtime API 初始化失败: {e}")
                    else:
                        print(f"[小模型] ⚠️ 缺少 Azure 配置，跳过 Realtime API")

                elif engine_type == "mini_tts":
                    # 尝试 Mini+TTS 引擎
                    if OPENAI_API_KEY:
                        try:
                            self.small_model = MiniTTSEngine(
                                api_key=OPENAI_API_KEY,
                                base_url=CUSTOM_BASE_URL,
                                model=MINI_MODEL if 'MINI_MODEL' in globals() else "gpt-4o-mini",
                                voice=MINI_TTS_VOICE if 'MINI_TTS_VOICE' in globals() else "zh-CN-XiaoxiaoNeural",
                                system_prompt=self.base_system_prompt,
                                temperature=0.7,
                                max_tokens=MINI_TTS_MAX_TOKENS if 'MINI_TTS_MAX_TOKENS' in globals() else 1000,
                                callback_on_response_start=self._on_small_model_start,
                                callback_on_text_delta=self._on_small_model_delta,
                                callback_on_tts_sentence=self._on_tts_sentence,
                                callback_on_response_done=self._on_small_model_done,
                                callback_on_error=self._on_small_model_error
                            )
                            print(f"[小模型] ✓ Mini+TTS 引擎初始化成功")
                            break
                        except Exception as e:
                            print(f"[小模型] ⚠️ Mini+TTS 引擎初始化失败: {e}")
                    else:
                        print(f"[小模型] ⚠️ 缺少 OPENAI_API_KEY，跳过 Mini+TTS")

            if not self.small_model:
                print("[小模型] ⚠️ 所有小模型引擎初始化失败")

            # 2. 初始化大模型（yunwu 平台）
            if OPENAI_API_KEY:
                big_model_prompt = """你是航空领域的专业技术顾问，擅长TEM（威胁与差错管理）分析。
当被问到具体的专业问题时，你需要：
1. 引用相关的MEL条款、手册规定
2. 提供详细的分析和建议
3. 考虑安全因素和备用方案
4. 给出具体的操作步骤"""

                self.big_model = TextLLMEngine(
                    api_key=OPENAI_API_KEY,
                    base_url=CUSTOM_BASE_URL,
                    model=BIG_MODEL,
                    system_prompt=big_model_prompt,
                    temperature=0.7,
                    max_tokens=2000,
                    callback_on_response_start=self._on_big_model_start,
                    callback_on_text_delta=self._on_big_model_delta,
                    callback_on_response_done=self._on_big_model_done,
                    callback_on_error=self._on_big_model_error
                )
                print("[大模型] yunwu 平台初始化成功")
            else:
                print("[大模型] ⚠️ 缺少 OPENAI_API_KEY，大模型不可用")

            if not self.small_model and not self.big_model:
                raise ValueError("小模型和大模型都未初始化，请检查配置")

            print("[双引擎] 初始化完成")

        except Exception as e:
            print(f"[双引擎] 初始化失败: {e}")
            messagebox.showerror("错误", f"引擎初始化失败：{str(e)}\n请检查.env中的API配置")

    # === 小模型回调 ===
    def _on_small_model_start(self):
        """小模型开始响应"""
        self._update_status("🔊 AI回复中...", "speaking")

    def _on_small_model_delta(self, delta_text: str):
        """小模型文本增量"""
        self.root.after(0, lambda: self.right_panel.append_ai_message_streaming(delta_text))

    def _on_tts_sentence(self, sentence: str, index: int, status: str):
        """Mini+TTS 句子转换回调"""
        self.root.after(0, lambda: self.right_panel.update_tts_progress(sentence, index, status))

    def _on_small_model_done(self, full_response: str):
        """小模型响应完成"""
        # 添加到对话历史
        self.conversation_history.append({
            "role": "assistant",
            "content": full_response
        })

        # 检查是否触发大模型
        trigger_keywords = ["查找", "查阅", "查询", "搜索", "让我"]
        if any(keyword in full_response for keyword in trigger_keywords):
            print("[触发检测] 检测到触发词，启动大模型")
            self._trigger_big_model(self.conversation_history[-2]["content"])  # 用户最后的问题
        else:
            self._update_status("✓ 完成", "success")

    def _on_small_model_error(self, error_msg: str):
        """小模型错误"""
        self._update_status(f"❌ 小模型错误: {error_msg}", "error")

    # === 大模型回调 ===
    def _on_big_model_start(self):
        """大模型开始响应"""
        self._update_status("🧠 专家分析中...", "processing")
        self.root.after(0, lambda: self.right_panel.show_expert_avatar())

    def _on_big_model_delta(self, delta_text: str):
        """大模型文本增量"""
        self.root.after(0, lambda: self.right_panel.append_ai_message_streaming(delta_text))

    def _on_big_model_done(self, full_response: str):
        """大模型响应完成"""
        # 添加到对话历史
        self.conversation_history.append({
            "role": "assistant",
            "content": "根据详细分析，" + full_response
        })
        self._update_status("✓ 专家分析完成", "success")

    def _on_big_model_error(self, error_msg: str):
        """大模型错误"""
        self._update_status(f"❌ 大模型错误: {error_msg}", "error")

    # === 统一接口方法 ===
    def process_user_message(self, user_message: str):
        """处理用户消息（统一入口）"""
        # 添加用户消息到历史
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # 调用小模型
        if self.small_model:
            def run_small_model():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # 获取对话历史（排除最后一条，因为已在 chat 中添加）
                    history = self.conversation_history[:-1]
                    loop.run_until_complete(
                        self.small_model.chat(user_message, conversation_history=history)
                    )
                except Exception as e:
                    print(f"[小模型线程] 错误: {e}")
                finally:
                    loop.close()

            thread = threading.Thread(target=run_small_model, daemon=True)
            thread.start()
        else:
            messagebox.showwarning("警告", "小模型未初始化")

    def _trigger_big_model(self, user_question: str):
        """触发大模型深度分析"""
        if not self.big_model:
            print("[大模型] 未初始化，跳过")
            return

        def run_big_model():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # 使用深度分析方法
                loop.run_until_complete(
                    self.big_model.analyze_with_context(
                        user_question=user_question,
                        conversation_history=self.conversation_history[:-1],
                        background_data=self.background_data,
                        personal_memo=self.personal_memo
                    )
                )
            except Exception as e:
                print(f"[大模型线程] 错误: {e}")
            finally:
                loop.close()

        thread = threading.Thread(target=run_big_model, daemon=True)
        thread.start()

    def set_personal_memo(self, memo: str):
        """设置个人备忘录"""
        self.personal_memo = memo

    def _update_status(self, text: str, status_type: str):
        """更新状态"""
        def update():
            self.right_panel.update_voice_status(text, status_type)

            # 控制头像动画
            if not hasattr(self.right_panel, 'user_avatar'):
                return

            if status_type == "speaking":
                self.right_panel.ai_avatar.start_speaking()
                self.right_panel.user_avatar.stop_speaking()
                if hasattr(self.right_panel, 'expert_avatar'):
                    self.right_panel.expert_avatar.stop_speaking()
            elif status_type == "processing" and "专家" in text:
                if hasattr(self.right_panel, 'expert_avatar'):
                    self.right_panel.expert_avatar.start_speaking()
                self.right_panel.ai_avatar.stop_speaking()
                self.right_panel.user_avatar.stop_speaking()
            elif status_type in ["success", "error"]:
                self.right_panel.ai_avatar.stop_speaking()
                self.right_panel.user_avatar.stop_speaking()
                if hasattr(self.right_panel, 'expert_avatar'):
                    self.right_panel.expert_avatar.stop_speaking()
                    self.right_panel.hide_expert_avatar()
                if status_type == "success":
                    self.right_panel._end_ai_streaming()

        self.root.after(0, update)

    def on_voice_input_button_click(self):
        """语音输入按钮被点击"""
        # TODO: 语音输入功能暂未迁移到新引擎
        messagebox.showinfo("提示", "语音输入功能暂未实现，请使用文本输入")

    def on_info_button_click(self, info_type):
        """当左侧信息按钮被点击时"""
        print(f"[事件] 用户请求查看 '{info_type}'")
        data_to_display = MOCK_DATA.get(info_type, "未找到信息。")
        self.center_panel.display_info(info_type, data_to_display)

    def start_team_discussion(self):
        """切换到双人协作阶段"""
        if self.current_phase == "INDIVIDUAL":
            print("[事件] 切换到协作讨论阶段。")

            # 1. 保存个人威胁备忘录内容
            personal_threats = self.right_panel.get_personal_threats()

            # 2. 将个人威胁备忘录传递给大模型（用于深度分析）
            self.set_personal_memo(personal_threats)

            # 3. 切换到协作阶段
            self.current_phase = "COLLABORATIVE"
            self.right_panel.setup_collaborative_view()
            self.left_panel.disable_buttons()

            # 4. 在中间面板显示个人威胁总结
            self.center_panel.display_personal_threats(personal_threats)

            # 5. 3秒后注入动态事件
            self.root.after(3000, self.inject_dynamic_event)

    def inject_dynamic_event(self):
        """注入动态事件"""
        print("[事件] 注入动态事件！")
        messagebox.showwarning(DYNAMIC_EVENT["title"], DYNAMIC_EVENT["message"])


def main():
    """主程序入口"""
    root = tk.Tk()
    app = TEMSimulatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
