import keyboard
import time
from threading import Thread, Lock
from speech_recognizer import SpeechRecognizer
from tts_service import TTSService
from ai_client import AIClient


class VoiceChatSystem:
    def __init__(self, enable_tts=True):
        """初始化语音聊天系统"""
        self.speech_recognizer = SpeechRecognizer("base")
        self.tts_service = TTSService() if enable_tts else None
        self.ai_client = AIClient()
        self.is_processing = False
        self.current_response = ""
        self.enable_tts = enable_tts
        self.processing_lock = Lock()
        self.response_callback = None  # 响应回调函数

    def set_response_callback(self, callback):
        """设置响应回调函数"""
        self.response_callback = callback

    def stream_response_callback(self, content, done=False):
        """流式回复回调函数"""
        if done:
            print(f"\n{'=' * 60}")
            self.current_response = ""
            print(" 可以继续提问（按住空格键录音）")

            # 调用GUI回调
            if self.response_callback:
                self.response_callback("", done=True)
        else:
            self.current_response += content
            # 调用GUI回调
            if self.response_callback:
                self.response_callback(content, done=False)

    def process_ai_response(self, user_text):
        """在单独线程中处理AI回复"""

        def get_response():
            try:
                self.ai_client.get_ai_response_stream(
                    user_text,
                    response_callback=self.stream_response_callback,
                    enable_tts=self.enable_tts,
                    tts_service=self.tts_service
                )
            except Exception as e:
                print(f"\n 处理错误: {e}")
            finally:
                with self.processing_lock:
                    self.is_processing = False

        with self.processing_lock:
            if not self.is_processing:
                self.is_processing = True
                Thread(target=get_response, daemon=True).start()
            else:
                print("  正在处理上一个请求，请稍候...")

    def check_services_connection(self):
        """检查所有服务连接"""
        # 检查Ollama服务
        if not self.ai_client.check_connection():
            print(" 请先启动Ollama服务: ollama serve")
            return False

        # 检查TTS服务
        if self.enable_tts and self.tts_service:
            if not self.tts_service.check_connection():
                print(" TTS服务不可用，将仅显示文字回复")
                self.enable_tts = False
            else:
                print(" 语音输出功能已启用")

        return True

    def run_cli(self):
        """运行命令行版本的语音聊天系统"""
        print("=" * 60)
        print("智能语音聊天机器人")
        print("=" * 60)

        # 检查服务连接
        if not self.check_services_connection():
            return

        print("\n  使用说明:")
        print("  • 按住空格键开始录音")
        print("  • 松开空格键停止录音并识别")
        print("  • AI会流式显示回复内容" + ("并语音播报" if self.enable_tts else ""))
        print("  • 按ESC键退出程序")
        print("=" * 60)
        print(" 可以开始对话了...")

        try:
            while True:
                # 检测空格键按下
                if (keyboard.is_pressed('space') and
                        not self.speech_recognizer.recording_status and
                        not self.is_processing):
                    self.speech_recognizer.start_recording()

                # 检测空格键释放
                if (not keyboard.is_pressed('space') and
                        self.speech_recognizer.recording_status):
                    user_text = self.speech_recognizer.stop_recording_and_recognize()
                    if user_text and len(user_text.strip()) > 0:
                        print(f"\n 您的提问: {user_text}")
                        print("-" * 40)
                        self.process_ai_response(user_text)
                    elif user_text == "":
                        print(" 没有识别到内容，请重新说话")

                # 检测ESC键退出
                if keyboard.is_pressed('esc'):
                    print("\n 退出程序")
                    break

                time.sleep(0.05)  # 降低CPU使用率

        except KeyboardInterrupt:
            print("\n\n 程序被用户中断")
        except Exception as e:
            print(f"\n程序错误: {e}")