import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QWidget, QLabel, QFrame, QScrollArea, QSizePolicy)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QPalette, QColor, QFontMetrics
import keyboard
import time


class VoiceChatGUI(QMainWindow):
    # 定义信号
    start_recording_signal = pyqtSignal()
    stop_recording_signal = pyqtSignal()
    exit_program_signal = pyqtSignal()
    # 用于从工作线程安全地传递AI响应到GUI主线程
    ai_response_signal = pyqtSignal(str, bool)

    def __init__(self, voice_chat_system):
        super().__init__()
        self.voice_chat_system = voice_chat_system
        self.current_response = ""
        self.is_processing = False
        self.space_pressed = False
        # 将后台线程发来的AI响应信号连接到GUI更新方法（保证在主线程执行）
        self.ai_response_signal.connect(self.append_ai_response)
        # 常态高度（闲置时显示为圆角长方形）与展开最大高度
        self.idle_height = 120
        self.expanded_max_height = 420
        self.collapse_delay_ms = 3000  # 完成后等待多少毫秒收缩
        self._collapse_timer = None
        self.init_ui()
        self.setup_keyboard_listener()

    def init_ui(self):
        """初始化UI"""
        # 设置窗口属性
        self.setWindowTitle("Elysia - 智能语音助手")
        self.setMinimumWidth(350)  # 最小宽度
        self.setMaximumWidth(900)  # 最大宽度
        # 常态为一根长条半透明界面
        self.setMinimumHeight(self.idle_height)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 设置布局
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 创建主框架（浅粉色，高透明度）
        main_frame = QFrame()
        main_frame.setObjectName("mainFrame")
        main_frame.setStyleSheet("""
            QFrame#mainFrame {
                /* 淡紫色背景，圆角长方形 */
                background-color: rgba(230, 210, 255, 0.35);
                border-radius: 16px;
                /* 淡紫/紫色外边框 */
                border: 3px solid rgba(153, 102, 204, 0.9);
            }
        """)

        frame_layout = QVBoxLayout(main_frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(6)

        # 状态显示栏（不再使用单独图标，使用同一文本区域显示所有信息）
        status_layout = QHBoxLayout()
        status_layout.setSpacing(6)

        # 状态文本（用于显示待机、录音提示及流式AI回复）
        self.status_label = QLabel("等待中...")
        # 使用更大的字体以提高可读性
        font = QFont()
        font.setPointSize(14)
        self.status_label.setFont(font)
        self.status_label.setStyleSheet("""
            QLabel {
                color: #8B008B;
                background: transparent;
            }
        """)
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # 使用 QScrollArea 包裹状态文本，当内容过高时显示垂直滚动条
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(self.status_label)
        # 让 scroll_area 在水平方向填满可用空间，避免右端不对齐
        self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.status_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        # 清除内边距，确保文本右端贴合滚动区域边界
        try:
            self.scroll_area.setContentsMargins(0, 0, 0, 0)
            self.status_label.setContentsMargins(0, 0, 0, 0)
        except:
            pass
        try:
            # QLabel 有时会有内部 margin，确保为 0
            self.status_label.setMargin(0)
        except:
            pass
        # 确保文本没有背景：让 scroll area 的 viewport 和 label 都透明
        try:
            self.scroll_area.setStyleSheet("background: transparent;")
            self.scroll_area.viewport().setStyleSheet("background: transparent;")
        except:
            pass
        try:
            self.status_label.setAttribute(Qt.WA_TranslucentBackground, True)
            self.status_label.setAutoFillBackground(False)
        except:
            pass
        # 确保文本左上对齐，便于计算并且右端能对齐边框
        try:
            self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        except:
            pass

        # 录音指示器（保留，仅文本图标）
        self.recording_indicator = QLabel("●")
        self.recording_indicator.setStyleSheet("""
            QLabel {
                color: rgba(255, 0, 0, 0.8);
                font-size: 12px;
                font-weight: bold;
                background: transparent;
            }
        """)
        self.recording_indicator.hide()

        status_layout.addWidget(self.scroll_area)
        status_layout.addWidget(self.recording_indicator)

        frame_layout.addLayout(status_layout)

        # 去掉分隔线与独立输出框，使用状态文本区域显示流式响应
        # frame_layout 保持现有内边距，状态文本在顶部区域显示多行内容

        layout.addWidget(main_frame)

        # 设置初始状态
        self.update_status("ready", "我在的哟，是不是想我啦？")

        # 启动状态更新定时器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_system_status)
        self.status_timer.start(100)

        # 初始为圆角矩形（闲置），设置大小
        QTimer.singleShot(100, lambda: self.resize(self.width() or 600, self.idle_height))

    def setup_keyboard_listener(self):
        """设置键盘监听"""
        self.keyboard_timer = QTimer()
        self.keyboard_timer.timeout.connect(self.check_keyboard)
        self.keyboard_timer.start(50)

    def expand_for_content(self):
        """展开窗口以显示内容"""
        # 先取消可能存在的收缩定时器
        try:
            if self._collapse_timer:
                self._collapse_timer.stop()
                self._collapse_timer = None
        except:
            pass

        # 根据文本内容调整高度
        self.adjust_window_size()

    def collapse_to_strip(self):
        """收缩回长条界面并清理显示内容"""
        # 清空当前响应并隐藏输出框
        self.current_response = ""
        # 将状态文本恢复为待机提示并收缩为闲置高度
        try:
            self.status_label.setText("我在的哟，是不是想我啦？")
        except:
            pass
        self.resize(self.width(), self.idle_height)

    def check_keyboard(self):
        """检查键盘输入"""
        try:
            # 检查空格键按下
            if keyboard.is_pressed('space') and not self.space_pressed:
                self.space_pressed = True
                if (not self.voice_chat_system.speech_recognizer.recording_status and
                        not self.voice_chat_system.is_processing):
                    print("空格键按下 - 开始录音")
                    self.start_recording_signal.emit()

            # 检查空格键释放
            elif not keyboard.is_pressed('space') and self.space_pressed:
                self.space_pressed = False
                if self.voice_chat_system.speech_recognizer.recording_status:
                    print("空格键释放 - 停止录音")
                    self.stop_recording_signal.emit()

            # 检查ESC键
            if keyboard.is_pressed('esc'):
                self.exit_program_signal.emit()

        except Exception as e:
            print(f"键盘监听错误: {e}")

    def update_system_status(self):
        """更新系统状态显示"""
        if self.voice_chat_system.speech_recognizer.recording_status:
            # 若正在录音且无正在显示的AI内容，显示录音提示
            if not self.current_response:
                self.update_status("recording", "我在听哦")
            self.recording_indicator.show()
        elif self.voice_chat_system.is_processing:
            # 若正在处理且无流式回复，则显示处理提示；否则保留正在显示的流式内容
            if not self.current_response:
                self.update_status("processing", "我在处理你的问题啦")
            self.recording_indicator.hide()
            try:
                self.recording_indicator.setFixedWidth(18)
                self.recording_indicator.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            except:
                pass
            # 正在处理时保持展开状态
            self.expand_for_content()
        else:
            if not self.current_response:
                self.update_status("ready", "我在的哟，是不是想我啦？")
            self.recording_indicator.hide()
            # 空闲且无内容时收缩为长条
            if not self.current_response:
                self.collapse_to_strip()

    def update_status(self, status_type, message):
        """更新状态显示"""
        icons = {
            "ready": "🌸",
            "recording": "🎤",
            "processing": "🤔",
            "error": "❌"
        }
        # 不再使用单独图标，直接在状态文本中显示信息
        self.status_label.setText(message)

    def append_ai_response(self, text, done=False):
        """添加AI回复到输出框并打印到终端"""
        # 统一在终端打印（用户输入与 AI 输出）
        try:
            if text:
                if not done:
                    # 流式输出：直接追加到状态文本
                    self.current_response += text
                    # 确保窗口扩展以显示内容
                    self.status_label.setText(self.current_response)
                    self.expand_for_content()

                    # 同步打印到终端（不换行，流式显示）
                    print(text, end="", flush=True)
                else:
                    # 完成输出块
                    if text.strip():
                        print(text, flush=True)
                    else:
                        print(flush=True)

                    # 生成结束时自动滚动到底部，然后在延迟后收缩并清空当前响应
                    try:
                        sb = self.scroll_area.verticalScrollBar()
                        sb.setValue(sb.maximum())
                    except:
                        pass
                    QTimer.singleShot(self.collapse_delay_ms, self.collapse_to_strip)

            else:
                # 空文本但 done=True 表示结束，换行
                if done:
                    print(flush=True)

            # 调整窗口大小（每次收到新内容都动态调整）
            self.adjust_window_size()
        except Exception as e:
            # 确保 GUI 不会因为打印问题崩溃
            print(f"append_ai_response 错误: {e}")

    def adjust_window_size(self):
        """根据内容动态调整窗口高度（仅在输出框可见时）"""
        # 根据状态文本内容动态调整窗口大小
        text = self.current_response if self.current_response else self.status_label.text()

        # 优先使用 scroll_area 的 viewport 宽度来计算换行宽度，避免与实际显示宽度不一致
        max_w = self.maximumWidth()
        try:
            vp = self.scroll_area.viewport()
            vpw = vp.width() if vp is not None else 0
        except:
            vpw = 0

        if vpw and vpw > 50:
            wrap_width = max(100, vpw - 8)  # 留一点内间距
        else:
            # 回退到窗口宽度计算（减去外边距和内边距）
            wrap_width = max(200, self.width() - 60)

        # 使用字体度量计算包装后的文本矩形
        fm = QFontMetrics(self.status_label.font())
        rect = fm.boundingRect(0, 0, wrap_width, 10000, Qt.TextWordWrap, text)

        # 计算理想宽度与高度（加上内边距）
        content_height = rect.height() + 20
        ideal_width = min(max(rect.width() + 60, 350), max_w)

        # 如果内容高度超出 expanded_max_height，则启用滚动并将窗口高度限制为 expanded_max_height
        if content_height + 40 > self.expanded_max_height:
            ideal_height = self.expanded_max_height
            # 启用垂直滚动条
            try:
                self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                # 将滚动区域高度设置为窗口内部可用高度
                self.scroll_area.setMaximumHeight(ideal_height - 40)
            except:
                pass
        else:
            ideal_height = min(max(content_height + 40, self.idle_height), self.expanded_max_height)
            try:
                self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                self.scroll_area.setMaximumHeight(ideal_height - 40)
            except:
                pass

        # 设置 label 的最大宽度为实际 wrap_width（加上少量内边距），保证右端贴合
        try:
            self.status_label.setMaximumWidth(wrap_width + 4)
        except:
            pass

        self.resize(ideal_width, ideal_height)

        # 确保窗口不会超出屏幕
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        current_geometry = self.geometry()

        if current_geometry.right() > screen_geometry.right():
            self.move(screen_geometry.right() - current_geometry.width(), current_geometry.y())
        if current_geometry.bottom() > screen_geometry.bottom():
            self.move(current_geometry.x(), screen_geometry.bottom() - current_geometry.height())

    def mousePressEvent(self, event):
        """鼠标按下事件，用于拖动窗口"""
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """鼠标移动事件，用于拖动窗口"""
        if event.buttons() == Qt.LeftButton and hasattr(self, 'drag_start_position'):
            self.move(event.globalPos() - self.drag_start_position)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        """双击事件 - 退出程序"""
        if event.button() == Qt.LeftButton:
            self.exit_program_signal.emit()

    def closeEvent(self, event):
        """关闭事件"""
        self.exit_program_signal.emit()
        event.accept()