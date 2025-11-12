#!/usr/bin/env python3
"""
UI面板组件 - 左侧、中间、右侧面板
"""
import tkinter as tk
from tkinter import scrolledtext

from components.avatar import AvatarWidget


class LeftPanel(tk.Frame):
    """左侧导航栏"""
    def __init__(self, master, controller):
        super().__init__(master, bd=2, relief=tk.SUNKEN)
        self.controller = controller

        tk.Label(self, text="信息源", font=("Helvetica", 14, "bold")).pack(pady=10)

        self.buttons = {}
        info_types = {"OFP": "飞行计划", "WEATHER": "天气", "TECH_LOG": "技术日志", "NOTAMS": "航行通告"}
        for key, text in info_types.items():
            btn = tk.Button(self, text=text, command=lambda k=key: self.controller.on_info_button_click(k))
            btn.pack(fill=tk.X, padx=10, pady=5)
            self.buttons[key] = btn

    def disable_buttons(self):
        for btn in self.buttons.values():
            btn.config(state=tk.DISABLED)


class CenterPanel(tk.Frame):
    """中间信息显示区"""
    def __init__(self, master, controller):
        super().__init__(master, bd=2, relief=tk.SUNKEN)
        self.controller = controller

        self.title_label = tk.Label(self, text="请从左侧选择信息源", font=("Helvetica", 14, "bold"))
        self.title_label.pack(pady=10)

        self.text_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, font=("Helvetica", 12))
        self.text_area.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        self.text_area.config(state=tk.DISABLED)

    def display_info(self, title, content):
        self.title_label.config(text=title)
        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete('1.0', tk.END)
        self.text_area.insert(tk.END, content)
        self.text_area.config(state=tk.DISABLED)

    def display_personal_threats(self, threats_content: str):
        """显示个人威胁总结（阶段二）"""
        self.title_label.config(text="📋 个人威胁总结", fg="#FF5722")
        self.text_area.config(state=tk.NORMAL)
        self.text_area.delete('1.0', tk.END)

        if threats_content.strip():
            self.text_area.insert(tk.END, "以下是你在个人信息收集阶段总结的潜在威胁：\n\n")
            self.text_area.insert(tk.END, "="*50 + "\n\n")
            self.text_area.insert(tk.END, threats_content)
        else:
            self.text_area.insert(tk.END, "（你在阶段一没有记录任何威胁）\n\n")
            self.text_area.insert(tk.END, "建议：在团队讨论中，可以回顾左侧信息源，识别新的威胁。")

        self.text_area.config(state=tk.DISABLED)


class RightPanel(tk.Frame):
    """右侧协作与决策区"""
    def __init__(self, master, controller):
        super().__init__(master, bd=2, relief=tk.SUNKEN)
        self.controller = controller
        self.setup_individual_view()

    def clear_panel(self):
        for widget in self.winfo_children():
            widget.destroy()

    def get_personal_threats(self) -> str:
        """获取个人威胁备忘录内容（在切换阶段前调用）"""
        if hasattr(self, 'memo_area'):
            return self.memo_area.get('1.0', tk.END).strip()
        return ""

    def setup_individual_view(self):
        """设置个人信息收集阶段的界面"""
        self.clear_panel()
        tk.Label(self, text="个人威胁备忘录", font=("Helvetica", 14, "bold")).pack(pady=10)

        self.memo_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, height=10)
        self.memo_area.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)

        tk.Button(self, text="进入团队讨论 >>", command=self.controller.start_team_discussion).pack(pady=10)

    def setup_collaborative_view(self):
        """设置双人讨论阶段的界面（带语音交互）"""
        self.clear_panel()

        # 头像显示区
        avatar_frame = tk.Frame(self, bg="white")
        avatar_frame.pack(fill=tk.X, padx=10, pady=10)

        # 用户头像（左侧）
        self.user_avatar = AvatarWidget(
            avatar_frame,
            name="你",
            emoji="👨‍✈️",
            color="#2196F3"  # 蓝色
        )
        self.user_avatar.pack(side=tk.LEFT, padx=10)

        # AI头像（右侧）
        self.ai_avatar = AvatarWidget(
            avatar_frame,
            name="AI伙伴",
            emoji="🤖",
            color="#4CAF50"  # 绿色
        )
        self.ai_avatar.pack(side=tk.RIGHT, padx=10)

        # 大模型专家头像（中间，初始隐藏）
        self.expert_avatar = AvatarWidget(
            avatar_frame,
            name="专家",
            emoji="🎓",
            color="#FF9800"  # 橙色
        )
        # 初始不显示，仅在触发大模型时显示

        # 分隔线
        tk.Frame(self, height=2, bg="#e0e0e0").pack(fill=tk.X, padx=10, pady=5)

        # 威胁日志（缩小）
        tk.Label(self, text="团队威胁日志", font=("Helvetica", 11, "bold")).pack(pady=3)
        self.threat_log = tk.Listbox(self, height=4)
        self.threat_log.pack(fill=tk.X, padx=10, pady=3)

        # 对话区（缩小高度）
        tk.Label(self, text="团队通讯", font=("Helvetica", 11, "bold")).pack(pady=3)
        self.chat_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, height=6)
        self.chat_area.pack(fill=tk.BOTH, padx=10, pady=3)
        self.chat_area.config(state=tk.DISABLED)

        # 语音交互控制区
        voice_frame = tk.LabelFrame(self, text="🎤 语音交互", font=("Helvetica", 11, "bold"))
        voice_frame.pack(fill=tk.X, padx=10, pady=10)

        # 语音输入按钮
        self.voice_button = tk.Button(
            voice_frame,
            text="🎤 语音输入",
            font=("Helvetica", 12, "bold"),
            bg="#4CAF50",
            fg="white",
            height=2,
            command=self.controller.on_voice_input_button_click
        )
        self.voice_button.pack(fill=tk.X, padx=10, pady=5)

        # 状态显示
        self.status_label = tk.Label(
            voice_frame,
            text="点击上方按钮开始语音输入",
            font=("Helvetica", 10),
            fg="gray"
        )
        self.status_label.pack(pady=5)

        # 文字输入区
        text_input_frame = tk.Frame(voice_frame)
        text_input_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(text_input_frame, text="消息输入:", font=("Helvetica", 9)).pack(anchor=tk.W)

        entry_frame = tk.Frame(text_input_frame)
        entry_frame.pack(fill=tk.X)

        self.chat_entry = tk.Entry(entry_frame, font=("Helvetica", 10))
        self.chat_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.chat_entry.bind("<Return>", lambda _event: self.send_text_message())

        tk.Button(entry_frame, text="发送", command=self.send_text_message).pack(side=tk.RIGHT, padx=(5, 0))

    def show_expert_avatar(self):
        """显示专家头像（当大模型被触发时）"""
        if hasattr(self, 'expert_avatar'):
            self.expert_avatar.pack(padx=10)
            self.expert_avatar.start_speaking()

    def hide_expert_avatar(self):
        """隐藏专家头像"""
        if hasattr(self, 'expert_avatar'):
            self.expert_avatar.stop_speaking()
            self.expert_avatar.pack_forget()

    def fill_input_from_voice(self, text: str):
        """从语音识别结果填充输入框"""
        self.chat_entry.delete(0, tk.END)
        self.chat_entry.insert(0, text)
        self.chat_entry.focus_set()  # 聚焦到输入框，方便用户修改

    def send_text_message(self):
        """发送文字消息 - 触发LLM对话"""
        message = self.chat_entry.get()
        if message.strip():
            # 1. 添加用户消息到对话框
            self.add_chat_message("你", message)
            self.chat_entry.delete(0, tk.END)

            # 2. 准备接收AI流式回复
            self._start_ai_streaming()

            # 3. 触发语音引擎处理（LLM + TTS）
            if self.controller.voice_engine:
                self.controller.voice_engine.process_user_message(message)

    def _start_ai_streaming(self):
        """开始AI流式回复（初始化状态）"""
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, "AI伙伴: ")
        self.chat_area.yview(tk.END)
        self.chat_area.config(state=tk.DISABLED)
        self._ai_streaming_active = True

    def append_ai_message_streaming(self, text: str):
        """流式追加AI消息内容"""
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, text)
        self.chat_area.yview(tk.END)
        self.chat_area.config(state=tk.DISABLED)

    def _end_ai_streaming(self):
        """结束AI流式回复"""
        if hasattr(self, '_ai_streaming_active') and self._ai_streaming_active:
            self.chat_area.config(state=tk.NORMAL)
            self.chat_area.insert(tk.END, "\n")
            self.chat_area.yview(tk.END)
            self.chat_area.config(state=tk.DISABLED)
            self._ai_streaming_active = False

    def add_chat_message(self, author, message):
        """添加聊天消息"""
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, f"{author}: {message}\n")
        self.chat_area.yview(tk.END)
        self.chat_area.config(state=tk.DISABLED)

    def update_voice_status(self, status_text: str, status_type: str):
        """更新语音状态显示"""
        color_map = {
            "recording": "#FF5722",  # 红色-录音中
            "processing": "#2196F3",  # 蓝色-处理中
            "speaking": "#4CAF50",    # 绿色-播放中
            "success": "#4CAF50",     # 绿色-成功
            "error": "#F44336",       # 红色-错误
            "info": "gray"            # 灰色-信息
        }

        self.status_label.config(
            text=status_text,
            fg=color_map.get(status_type, "gray")
        )
