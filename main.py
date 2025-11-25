#!/usr/bin/env python3
"""
主程序入口文件
"""
import nltk
import sys
import os
import time
from voice_chat_system import VoiceChatSystem
from PyQt5.QtWidgets import QApplication


def check_nltk_resources():
    """检查NLTK资源"""
    try:
        print(" 检查NLTK资源...")
        try:
            nltk.data.find('taggers/averaged_perceptron_tagger')
        except LookupError:
            print("下载NLTK资源...")
            nltk.download('averaged_perceptron_tagger', quiet=True)
            nltk.download('punkt', quiet=True)
        print("NLTK资源就绪")
    except Exception as e:
        print(f"NLTK检查失败: {e}")


class VoiceChatApp:
    def __init__(self):
        self.chat_system = None
        self.gui = None
        self.app = None

    def setup_connections(self):
        """设置信号连接"""
        # 连接GUI信号到聊天系统
        self.gui.start_recording_signal.connect(self.chat_system.speech_recognizer.start_recording)
        self.gui.stop_recording_signal.connect(self.stop_recording_and_process)
        self.gui.exit_program_signal.connect(self.exit_program)

        # 设置聊天系统的回调函数到GUI
        # NOTE: 不要直接传入 GUI 的方法（会从工作线程直接调用导致跨线程修改 GUI），
        # 而是使用 GUI 的信号在主线程中更新界面。
        self.chat_system.set_response_callback(lambda text, done=False: self.gui.ai_response_signal.emit(text, done))

    def stop_recording_and_process(self):
        """停止录音并处理"""
        print("停止录音并处理...")
        user_text = self.chat_system.speech_recognizer.stop_recording_and_recognize()
        if user_text and len(user_text.strip()) > 0:
            # 先把用户提问显示到界面（使用信号）
            self.gui.ai_response_signal.emit(f"\n🗣️ 您的提问: {user_text}\n", True)
            self.chat_system.process_ai_response(user_text)
        elif user_text == "":
            self.gui.ai_response_signal.emit("❌ 没有识别到内容，请重新说话", True)
        else:
            self.gui.ai_response_signal.emit("❌ 录音失败，请重试", True)

    def exit_program(self):
        """退出程序"""
        print("\n退出程序")
        if self.app:
            self.app.quit()

    def run(self):
        """运行应用程序"""
        print("\n" + "=" * 60)

        # 检查NLTK资源
        check_nltk_resources()

        print("\n" + "=" * 60)

        # 创建语音聊天系统
        self.chat_system = VoiceChatSystem(enable_tts=True)

        # 检查服务连接
        if not self.chat_system.check_services_connection():
            print("服务连接失败，程序退出")
            return

        print("启动图形界面...")

        # 启动GUI
        self.app = QApplication(sys.argv)

        # 导入GUI类（放在这里避免循环导入）
        from gui import VoiceChatGUI

        # 创建GUI实例
        self.gui = VoiceChatGUI(self.chat_system)
        self.gui.show()

        # 设置信号连接
        self.setup_connections()

        print("程序启动完成！")
        print("使用说明：")
        print("  • 点击麦克风按钮或按住空格键开始录音")
        print("  • 松开按钮或空格键停止录音")
        print("  • AI会流式显示回复内容")
        print("  • 点击关闭按钮或按ESC键退出程序")

        sys.exit(self.app.exec_())


def main():
    """主函数"""
    app = VoiceChatApp()
    app.run()


if __name__ == "__main__":
    main()