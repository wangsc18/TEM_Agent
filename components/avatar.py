#!/usr/bin/env python3
"""
动态头像组件 - 支持说话动画效果
"""
import tkinter as tk
import math


class AvatarWidget(tk.Canvas):
    """动态头像组件 - 支持说话动画效果"""

    def __init__(self, master, name: str, emoji: str, color: str, **kwargs):
        """
        初始化头像组件

        Args:
            name: 名称（"你" 或 "AI伙伴"）
            emoji: 表情符号（"👨‍✈️" 或 "🤖"）
            color: 主题颜色
        """
        super().__init__(master, width=120, height=140, bg="white", highlightthickness=0, **kwargs)

        self.name = name
        self.emoji = emoji
        self.color = color
        self.is_speaking = False
        self.animation_frame = 0
        self.animation_job = None

        # 绘制静态元素
        self._draw_static()

    def _draw_static(self):
        """绘制静态元素（头像圆圈、名称）"""
        # 清空画布
        self.delete("all")

        # 外圈（用于动画）
        self.outer_circle = self.create_oval(
            20, 20, 100, 100,
            outline=self.color,
            width=2,
            tags="outer"
        )

        # 内圈（头像背景）
        self.inner_circle = self.create_oval(
            30, 30, 90, 90,
            fill="#f0f0f0",
            outline=self.color,
            width=2,
            tags="inner"
        )

        # 表情符号
        self.emoji_text = self.create_text(
            60, 60,
            text=self.emoji,
            font=("Arial", 32),
            tags="emoji"
        )

        # 名称
        self.name_text = self.create_text(
            60, 115,
            text=self.name,
            font=("Helvetica", 11, "bold"),
            fill="#333"
        )

        # 音量波形条（初始隐藏）
        self.wave_bars = []
        for i in range(5):
            bar = self.create_rectangle(
                15 + i * 22, 90,
                30 + i * 22, 95,
                fill=self.color,
                outline="",
                tags="wave",
                state="hidden"
            )
            self.wave_bars.append(bar)

    def start_speaking(self):
        """开始说话动画"""
        if not self.is_speaking:
            self.is_speaking = True
            self.animation_frame = 0
            self._animate()

    def stop_speaking(self):
        """停止说话动画"""
        self.is_speaking = False
        if self.animation_job:
            self.after_cancel(self.animation_job)
            self.animation_job = None

        # 恢复静态状态
        self._draw_static()

    def _animate(self):
        """动画循环"""
        if not self.is_speaking:
            return

        self.animation_frame += 1
        frame = self.animation_frame

        # 1. 外圈脉冲效果（缩放）
        scale = 1.0 + 0.1 * math.sin(frame * 0.3)
        center = 60
        radius_outer = 40 * scale
        self.coords(
            self.outer_circle,
            center - radius_outer, center - radius_outer,
            center + radius_outer, center + radius_outer
        )

        # 2. 外圈颜色变化
        color_rgb = self._hex_to_rgb(self.color)
        animated_color = f'#{color_rgb[0]:02x}{color_rgb[1]:02x}{color_rgb[2]:02x}'
        self.itemconfig(self.outer_circle, outline=animated_color, width=int(2 + 2 * math.sin(frame * 0.3)))

        # 3. 音量波形动画
        for i, bar in enumerate(self.wave_bars):
            # 每个柱子不同相位
            height = 5 + 15 * abs(math.sin(frame * 0.2 + i * 0.5))
            self.coords(
                bar,
                15 + i * 22, 95 - height,
                30 + i * 22, 95
            )
            self.itemconfig(bar, state="normal")

        # 4. 表情符号轻微跳动
        offset_y = 2 * math.sin(frame * 0.25)
        self.coords(self.emoji_text, 60, 60 + offset_y)

        # 继续动画
        self.animation_job = self.after(50, self._animate)  # 20 FPS

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        """将十六进制颜色转为RGB"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
