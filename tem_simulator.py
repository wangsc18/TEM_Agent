import tkinter as tk
from tkinter import messagebox, scrolledtext

# --- 模拟的后台数据 ---
# 在真实应用中，这些数据将从您的场景引擎加载
MOCK_DATA = {
    "OFP": "飞行计划 (OFP):\n\n航线: ZSSS -> ZBAA\n预计油耗: 15.2吨\n备降场: ZBTJ\n巡航高度: FL350\n备注: 乘客中有医疗急救人员，需尽快抵达。",
    "WEATHER": "气象报告 (METAR & TAF):\n\nZSSS (出发地): 24015KT 9999 FEW030 25/18 Q1012 NOSIG\n\nZBAA (目的地): 20005KT 3000 BR SCT010 BKN020\nTAF ZBAA: ... TEMPO 0406 0500 FG BKN002\n(威胁: 目的地机场有雾，能见度可能在预计抵达时急剧下降至500米)",
    "TECH_LOG": "飞机技术日志:\n\n日期: 2025-10-26\n项目: APU（辅助动力单元）启动发电机故障\n状态: 已根据MEL 49-11-01保留\n影响: 地面无法使用APU供电和引气，必须依赖地面设备。",
    "NOTAMS": "航行通告 (NOTAMs):\n\nB3454/25 NOTAMN\nQ) ZSHA/QMRHW/IV/NBO/A/000/999/3114N12147E005\nA) ZSSS B) 2510250800 C) 2510251100\nE) RWY 17L/35R 因施工，可用起飞距离缩短400米。\n(威胁: 跑道长度缩短，需重新计算起飞性能)",
}

# --- 动态事件定义 ---
DYNAMIC_EVENT = {
    "title": "!! 紧急通知: 来自签派 !!",
    "message": "最新消息: 机上将增加一名需要担架的医疗旅客及陪同家属，总重210公斤。请立即重新计算重心和载重，并评估对起飞性能的影响。",
}

class TEMSimulatorApp:
    """主应用控制器"""
    def __init__(self, root):
        self.root = root
        self.root.title("双人TEM桌面推演模拟器 (原型)")
        self.root.geometry("1200x800")

        self.current_phase = "INDIVIDUAL" # 初始阶段为 'INDIVIDUAL' 或 'COLLABORATIVE'

        # --- UI 面板初始化 ---
        # 使用grid布局管理器
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1) # 左侧栏
        self.root.grid_columnconfigure(1, weight=3) # 中间主区
        self.root.grid_columnconfigure(2, weight=2) # 右侧协作区

        self.left_panel = LeftPanel(self.root, self)
        self.center_panel = CenterPanel(self.root, self)
        self.right_panel = RightPanel(self.root, self)

        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.center_panel.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self.right_panel.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        
        # ------------------------------------------------------------------
        # ### LLM 语音交互接口钩子 (LLM VOICE INTERFACE HOOKS) ###
        # ------------------------------------------------------------------
        self.initialize_llm_voice_interface()
        # ------------------------------------------------------------------

    def initialize_llm_voice_interface(self):
        """
        【接口】在这里初始化你的语音识别和TTS引擎。
        例如，启动一个后台线程来监听麦克风。
        """
        print("[接口] 语音交互接口已初始化 (占位符)。")
        # 示例: voice_recognizer.start_listening(self.process_voice_command)

    def process_voice_command(self, command_text):
        """
        【接口】当语音识别引擎识别到用户的命令时，调用此函数。
        你需要在这里实现命令的解析和分发逻辑。
        """
        print(f"[接口] 接收到语音命令: '{command_text}'")
        # 示例逻辑:
        # if "打开天气" in command_text:
        #     self.on_info_button_click("WEATHER")
        # elif "记录威胁" in command_text:
        #     selected_text = self.center_panel.get_selected_text()
        #     self.right_panel.log_threat(selected_text)
        # else:
        #     # 如果不是特定命令，则视为聊天内容
        #     self.on_human_chat_message(command_text)
        pass
        
    def send_ai_speech(self, text):
        """
        【接口】当AI需要“说话”时，调用此函数。
        """
        print(f"[接口] AI 准备说: '{text}'")
        # 1. 更新GUI上的聊天记录
        self.right_panel.add_chat_message("AI伙伴", text)
        # 2. 调用TTS引擎播放语音
        # 示例: tts_engine.speak(text)

    # --- 应用逻辑 ---
    
    def on_info_button_click(self, info_type):
        """当左侧信息按钮被点击时"""
        print(f"[事件] 用户请求查看 '{info_type}'")
        data_to_display = MOCK_DATA.get(info_type, "未找到信息。")
        self.center_panel.display_info(info_type, data_to_display)

    def start_team_discussion(self):
        """切换到双人协作阶段"""
        if self.current_phase == "INDIVIDUAL":
            print("[事件] 切换到协作讨论阶段。")
            self.current_phase = "COLLABORATIVE"
            self.right_panel.setup_collaborative_view()
            self.left_panel.disable_buttons() # 讨论开始后，禁止再获取新信息，聚焦讨论
            
            # 在切换到协作模式3秒后，注入一个动态事件
            self.root.after(3000, self.inject_dynamic_event)

    def inject_dynamic_event(self):
        """注入动态事件"""
        print("[事件] 注入动态事件！")
        messagebox.showwarning(DYNAMIC_EVENT["title"], DYNAMIC_EVENT["message"])

    def on_human_chat_message(self, message):
        """当人类玩家发送聊天信息时"""
        if not message.strip():
            return
            
        self.right_panel.add_chat_message("你", message)
        
        # ------------------------------------------------------------------
        # ### LLM 决策接口钩子 (LLM DECISION INTERFACE HOOK) ###
        # ------------------------------------------------------------------
        # 将人类的消息传递给LLM进行处理
        self.get_llm_response(message)
        # ------------------------------------------------------------------

    def get_llm_response(self, human_message):
        """
        【接口】在这里构建完整的Prompt，并异步调用你的LLM。
        """
        print(f"[接口] 正在为人类消息 '{human_message}' 生成LLM响应...")
        
        # --- 构建Prompt (示例) ---
        # world_state = self.get_world_state_as_text()
        # prompt = f"{world_state}\n\nHuman says: '{human_message}'.\n\nWhat is your response?"
        # llm_response = my_llm_api_call(prompt) 
        
        # --- 模拟LLM的延迟和响应 ---
        simulated_delay = 2000 # 模拟2秒延迟
        mock_response = "收到。关于跑道缩短的威胁，我建议我们重新计算起飞重量，看是否需要减少油量。"
        self.root.after(simulated_delay, lambda: self._on_llm_response_received(mock_response))

    def _on_llm_response_received(self, response_text):
        """当从LLM收到响应时的回调函数"""
        self.send_ai_speech(response_text)


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

class RightPanel(tk.Frame):
    """右侧协作与决策区"""
    def __init__(self, master, controller):
        super().__init__(master, bd=2, relief=tk.SUNKEN)
        self.controller = controller
        self.setup_individual_view()

    def clear_panel(self):
        for widget in self.winfo_children():
            widget.destroy()

    def setup_individual_view(self):
        """设置个人信息收集阶段的界面"""
        self.clear_panel()
        tk.Label(self, text="个人威胁备忘录", font=("Helvetica", 14, "bold")).pack(pady=10)
        
        self.memo_area = scrolledtext.ScrolledText(self, wrap=tk.WORD, height=10)
        self.memo_area.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)
        
        tk.Button(self, text="进入团队讨论 >>", command=self.controller.start_team_discussion).pack(pady=10)

    def setup_collaborative_view(self):
        """设置双人讨论阶段的界面"""
        self.clear_panel()
        tk.Label(self, text="团队威胁日志", font=("Helvetica", 14, "bold")).pack(pady=10)
        self.threat_log = tk.Listbox(self, height=8)
        self.threat_log.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(self, text="团队通讯", font=("Helvetica", 14, "bold")).pack(pady=10)
        self.chat_area = scrolledtext.ScrolledText(self, wrap=tk.WORD)
        self.chat_area.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)
        self.chat_area.config(state=tk.DISABLED)

        chat_input_frame = tk.Frame(self)
        chat_input_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.chat_entry = tk.Entry(chat_input_frame, font=("Helvetica", 11))
        self.chat_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.chat_entry.bind("<Return>", lambda event: self.send_chat_message())

        tk.Button(chat_input_frame, text="发送", command=self.send_chat_message).pack(side=tk.RIGHT)

    def send_chat_message(self):
        message = self.chat_entry.get()
        self.controller.on_human_chat_message(message)
        self.chat_entry.delete(0, tk.END)

    def add_chat_message(self, author, message):
        self.chat_area.config(state=tk.NORMAL)
        self.chat_area.insert(tk.END, f"{author}: {message}\n")
        self.chat_area.yview(tk.END) # 自动滚动到底部
        self.chat_area.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    app = TEMSimulatorApp(root)
    root.mainloop()