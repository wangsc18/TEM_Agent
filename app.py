#!/usr/bin/env python3
"""
TEM双人推演模拟器 - 主应用入口
整合双模型架构 + 语音交互
"""
import tkinter as tk
from tkinter import messagebox

from config import *
from data.mock_data import MOCK_DATA, DYNAMIC_EVENT
from engines.voice_engine import VoiceInteractionEngine
from ui.panels import LeftPanel, CenterPanel, RightPanel


class TEMSimulatorApp:
    """主应用控制器"""
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_GEOMETRY)

        self.current_phase = "INDIVIDUAL"

        # 初始化语音引擎
        self.voice_engine = None
        self._init_voice_engine()

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

    def _init_voice_engine(self):
        """初始化语音引擎（支持双模型）"""
        try:
            self.voice_engine = VoiceInteractionEngine(
                small_model=SMALL_MODEL,
                big_model=BIG_MODEL,
                tts_engine=TTS_ENGINE,
                enable_dual_model=ENABLE_DUAL_MODEL,
                callback_on_user_text=self._on_user_speech_recognized,
                callback_on_ai_text=self._on_ai_speech_generated,
                callback_on_ai_text_streaming=self._on_ai_speech_streaming,
                callback_on_status=self._on_voice_status_update,
                callback_on_big_model_triggered=self._on_big_model_triggered
            )

            # 设置背景数据（用于大模型）
            self.voice_engine.set_background_data(MOCK_DATA)

            print("[语音引擎] 初始化成功")
            if ENABLE_DUAL_MODEL:
                print(f"[双模型] 小模型: {SMALL_MODEL}, 大模型: {BIG_MODEL}")
        except Exception as e:
            print(f"[语音引擎] 初始化失败: {e}")
            messagebox.showerror("错误", f"语音引擎初始化失败：{str(e)}\n请检查.env中的OPENAI_API_KEY")

    def _on_user_speech_recognized(self, text: str):
        """用户语音识别完成的回调 - 填充到输入框"""
        # 在主线程填充输入框
        self.root.after(0, lambda: self.right_panel.fill_input_from_voice(text))

    def _on_ai_speech_streaming(self, text: str):
        """AI流式生成回调 - 实时更新显示"""
        # 在主线程流式更新对话框
        self.root.after(0, lambda: self.right_panel.append_ai_message_streaming(text))

    def _on_ai_speech_generated(self, _text: str):
        """AI回复生成完成的回调"""
        # 流式模式下不需要这个回调（已通过streaming更新）
        pass

    def _on_big_model_triggered(self):
        """大模型被触发的回调 - 显示专家头像"""
        def show_expert():
            if hasattr(self.right_panel, 'show_expert_avatar'):
                self.right_panel.show_expert_avatar()

        self.root.after(0, show_expert)

    def _on_voice_status_update(self, status_text: str, status_type: str):
        """语音状态更新回调"""
        # 在主线程更新状态显示和头像动画
        def update_ui():
            self.right_panel.update_voice_status(status_text, status_type)

            # 控制头像动画
            if not hasattr(self.right_panel, 'user_avatar'):
                return  # 还在阶段一，没有头像

            if status_type == "recording":
                # 用户正在说话
                self.right_panel.user_avatar.start_speaking()
                self.right_panel.ai_avatar.stop_speaking()
                if hasattr(self.right_panel, 'expert_avatar'):
                    self.right_panel.expert_avatar.stop_speaking()
            elif status_type == "speaking":
                # AI正在说话（小模型）
                self.right_panel.user_avatar.stop_speaking()
                self.right_panel.ai_avatar.start_speaking()
                if hasattr(self.right_panel, 'expert_avatar'):
                    self.right_panel.expert_avatar.stop_speaking()
            elif status_type == "processing" and "专家" in status_text:
                # 大模型正在处理
                self.right_panel.user_avatar.stop_speaking()
                self.right_panel.ai_avatar.stop_speaking()
                if hasattr(self.right_panel, 'expert_avatar'):
                    self.right_panel.expert_avatar.start_speaking()
            elif status_type in ["success", "error"]:
                # 完成或错误，停止所有动画
                self.right_panel.user_avatar.stop_speaking()
                self.right_panel.ai_avatar.stop_speaking()
                if hasattr(self.right_panel, 'expert_avatar'):
                    self.right_panel.expert_avatar.stop_speaking()
                    self.right_panel.hide_expert_avatar()
                # 结束AI流式显示
                if status_type == "success":
                    self.right_panel._end_ai_streaming()

        self.root.after(0, update_ui)

    def on_voice_input_button_click(self):
        """语音输入按钮被点击"""
        if self.voice_engine:
            self.voice_engine.start_recording()
        else:
            messagebox.showwarning("警告", "语音引擎未初始化")

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

            # 2. 将个人威胁备忘录传递给语音引擎（用于大模型分析）
            if self.voice_engine:
                self.voice_engine.set_personal_memo(personal_threats)

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
