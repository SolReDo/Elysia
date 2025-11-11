import warnings
import whisper
import sounddevice as sd
import numpy as np
import wave
import os
import keyboard
import time
import requests
import json
from threading import Thread, Lock
import pygame
import re

# 忽略Whisper的FP16警告
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")


class RealTimeSpeechRecognition:
    def __init__(self, model_size="turbo"):
        """初始化实时语音识别"""
        print("初始化Whisper模型...")

        # 抑制Whisper的警告
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.model = whisper.load_model(model_size)

        print(f" Whisper {model_size} 模型加载完成")

        # 音频参数
        self.sample_rate = 16000
        self.is_recording = False
        self.audio_data = []
        self.temp_file = "temp_audio.wav"

        # Ollama配置
        self.ollama_url = "http://localhost:11434/api/chat"
        self.model_name = "deepseek-r1:8b"
        self.conversation_history = []
        self.history_lock = Lock()

        # TTS配置
        self.tts_url = "http://127.0.0.1:9880"
        self.tts_enabled = True
        self.tts_lock = Lock()

        # 初始化pygame混音器
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            print(" 音频输出系统初始化完成")
        except Exception as e:
            print(f" 音频输出系统初始化失败: {e}")
            self.tts_enabled = False

    def clean_text_for_tts(self, text):
        """
        清理文本，确保只包含中文和基本标点
        """
        if not text:
            return "抱歉，这段内容无法转换为语音"

        # 确保输入是字符串
        cleaned_text = str(text)

        # 只保留中文、英文、数字和基本中文标点
        pattern = r'[^\u4e00-\u9fa5a-zA-Z0-9\s。，！？；："\'\（）《》【】…]'
        cleaned_text = re.sub(pattern, '', cleaned_text)

        # 处理多余的空白字符
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()

        # 如果清理后文本为空，返回默认提示
        if not cleaned_text.strip():
            return "抱歉，这段内容无法转换为语音"

        # 限制文本长度
        if len(cleaned_text) > 150:
            cleaned_text = cleaned_text[:150] + "。"

        return cleaned_text

    def text_to_speech(self, text, max_retries=2):
        """TTS函数，带线程锁防止并发冲突"""
        if not self.tts_enabled or not text:
            return False

        # 使用锁防止多个线程同时访问TTS
        with self.tts_lock:
            return self._text_to_speech_impl(text, max_retries)

    def _text_to_speech_impl(self, text, max_retries=2):
        """TTS实现"""
        try:
            # 基础文本清理
            cleaned_text = self.clean_text_for_tts(text)
            if not cleaned_text or cleaned_text == "抱歉，这段内容无法转换为语音":
                print(" 文本清理后为空，跳过TTS")
                return False

            print(f" TTS文本: {cleaned_text}")

            for attempt in range(max_retries):
                try:
                    # 使用GET请求，参数尽量简单
                    params = {
                        "text": cleaned_text,
                        "text_language": "zh"
                    }

                    print(f" 尝试生成语音 (第 {attempt + 1} 次)...")

                    response = requests.get(
                        self.tts_url,
                        params=params,
                        timeout=45,  # 延长超时时间
                        stream=True
                    )

                    if response.status_code == 200:
                        # 收集音频数据
                        audio_content = b""
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                audio_content += chunk

                        # 检查响应内容是否有效
                        if len(audio_content) < 2048:  # 提高最小长度要求
                            print(f" 响应内容过短: {len(audio_content)} 字节")
                            continue

                        # 保存到临时文件
                        temp_audio_file = f"temp_tts_{int(time.time())}.wav"
                        try:
                            with open(temp_audio_file, 'wb') as f:
                                f.write(audio_content)

                            # 验证文件是否可读
                            if os.path.getsize(temp_audio_file) < 2048:
                                print(" 音频文件过小")
                                continue

                            # 播放音频
                            if not pygame.mixer.get_init():
                                pygame.mixer.init()

                            pygame.mixer.music.load(temp_audio_file)
                            pygame.mixer.music.play()

                            print(" 播放音频中...")

                            # 等待播放完成
                            start_time = time.time()
                            while pygame.mixer.music.get_busy():
                                if time.time() - start_time > 60:  # 延长超时
                                    print(" 音频播放超时")
                                    pygame.mixer.music.stop()
                                    break
                                time.sleep(0.1)

                            print(" 音频播放完成")
                            return True

                        except Exception as e:
                            print(f" 文件操作失败: {e}")
                        finally:
                            # 清理临时文件
                            try:
                                if os.path.exists(temp_audio_file):
                                    os.remove(temp_audio_file)
                            except:
                                pass

                    else:
                        print(f" TTS请求失败，状态码: {response.status_code}")

                except requests.exceptions.ConnectionError:
                    print(f" 无法连接到TTS服务 (第 {attempt + 1} 次尝试)")
                except requests.exceptions.Timeout:
                    print(f" TTS请求超时 (第 {attempt + 1} 次尝试)")
                except Exception as e:
                    print(f" TTS错误 (第 {attempt + 1} 次): {e}")

                # 重试前等待
                if attempt < max_retries - 1:
                    time.sleep(3)  # 增加等待时间

            print(" 所有重试均失败")
            return False

        except Exception as e:
            print(f" TTS处理过程中发生错误: {e}")
            return False

    def start_recording(self):
        """开始录音"""
        if self.is_recording:
            return

        print(" 开始录音...（松开空格键停止）")
        self.is_recording = True
        self.audio_data = []

        def audio_callback(indata, frames, time, status):
            if self.is_recording:
                self.audio_data.append(indata.copy())

        try:
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                callback=audio_callback,
                blocksize=1024,
                dtype=np.int16
            )
            self.stream.start()
        except Exception as e:
            print(f" 录音设备初始化失败: {e}")
            self.is_recording = False

    def stop_recording_and_recognize(self):
        """停止录音并进行识别"""
        if not self.is_recording:
            return None

        print(" 停止录音，正在识别...")
        self.is_recording = False

        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        except:
            pass

        if len(self.audio_data) > 0:
            try:
                full_audio = np.concatenate(self.audio_data, axis=0)
                self._save_audio_to_file(full_audio)

                # 使用Whisper识别
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    result = self.model.transcribe(self.temp_file)
                text = result["text"].strip()

                # 清理临时文件
                if os.path.exists(self.temp_file):
                    os.remove(self.temp_file)

                return text
            except Exception as e:
                print(f" 语音识别失败: {e}")
                return None
        return None

    def _save_audio_to_file(self, audio_data):
        """保存音频数据到文件"""
        try:
            with wave.open(self.temp_file, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_data.tobytes())
        except Exception as e:
            print(f" 保存音频文件失败: {e}")

    def get_ai_response_stream(self, user_input, response_callback=None, enable_tts=True):
        """流式获取AI回复"""
        if not user_input or len(user_input.strip()) == 0:
            error_msg = "我没有听清楚您说的话，请再说一遍。"
            if response_callback:
                response_callback(error_msg, done=True)
            if enable_tts:
                Thread(target=lambda: self.text_to_speech(error_msg), daemon=True).start()
            return error_msg

        try:
            # 添加用户消息到历史
            with self.history_lock:
                self.conversation_history.append({"role": "user", "content": user_input})

            request_data = {
                "model": self.model_name,
                "messages": self.conversation_history,
                "stream": True
            }

            print(" AI正在思考: ", end="", flush=True)

            full_response = ""

            response = requests.post(
                self.ollama_url,
                json=request_data,
                stream=True,
                timeout=120  # 延长超时时间
            )

            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        try:
                            json_data = json.loads(line.decode('utf-8'))
                            if 'message' in json_data and 'content' in json_data['message']:
                                content = json_data['message']['content']
                                full_response += content
                                print(content, end="", flush=True)
                                if response_callback:
                                    response_callback(content, done=False)
                            if json_data.get('done', False):
                                break
                        except json.JSONDecodeError:
                            continue

                # 添加AI回复到历史
                if full_response:
                    with self.history_lock:
                        self.conversation_history.append({"role": "assistant", "content": full_response})
                        # 限制历史长度
                        if len(self.conversation_history) > 8:
                            self.conversation_history = self.conversation_history[-8:]

                print()  # 换行

                if response_callback:
                    response_callback(full_response, done=True)

                # 播放语音回复
                if enable_tts and full_response:
                    print(" 正在生成语音回复...")
                    Thread(target=lambda: self.text_to_speech(full_response), daemon=True).start()

                return full_response
            else:
                error_msg = f"API请求失败，状态码: {response.status_code}"
                print(f"\n{error_msg}")
                if response_callback:
                    response_callback(error_msg, done=True)
                if enable_tts:
                    Thread(target=lambda: self.text_to_speech("抱歉，AI服务暂时不可用。"), daemon=True).start()
                return error_msg

        except Exception as e:
            error_msg = f"AI回复错误: {e}"
            print(f"\n{error_msg}")
            if response_callback:
                response_callback(error_msg, done=True)
            if enable_tts:
                Thread(target=lambda: self.text_to_speech("处理请求时出现错误。"), daemon=True).start()
            return error_msg


class VoiceChatSystem:
    def __init__(self, enable_tts=True):
        """初始化语音聊天系统"""
        self.speech_recognizer = RealTimeSpeechRecognition("base")
        self.is_processing = False
        self.current_response = ""
        self.enable_tts = enable_tts
        self.processing_lock = Lock()

    def stream_response_callback(self, content, done=False):
        """流式回复回调函数"""
        if done:
            print(f"\n{'=' * 60}")
            self.current_response = ""
            print(" 可以继续提问（按住空格键录音）")
        else:
            self.current_response += content

    def process_ai_response(self, user_text):
        """在单独线程中处理AI回复"""

        def get_response():
            try:
                self.speech_recognizer.get_ai_response_stream(
                    user_text,
                    response_callback=self.stream_response_callback,
                    enable_tts=self.enable_tts
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

    def check_ollama_connection(self):
        """检查Ollama连接"""
        try:
            test_response = requests.get("http://localhost:11434/api/tags", timeout=10)
            if test_response.status_code == 200:
                print(" Ollama服务连接正常")
                return True
            else:
                print(" Ollama服务异常")
                return False
        except Exception as e:
            print(f" 无法连接到Ollama: {e}")
            return False

    def check_tts_connection(self):
        """检查TTS服务连接"""
        if not self.enable_tts:
            return True

        try:
            test_text = "测试"
            params = {
                "text": test_text,
                "text_language": "zh"
            }
            response = requests.get(self.speech_recognizer.tts_url, params=params, timeout=15)
            if response.status_code == 200:
                print(" TTS服务连接正常")
                return True
            else:
                print(" TTS服务异常")
                return False
        except Exception as e:
            print(f" 无法连接到TTS服务: {e}")
            return False

    def run(self):
        """运行语音聊天系统"""
        print("=" * 60)
        print("智能语音聊天机器人")
        print("=" * 60)

        # 检查服务连接
        if not self.check_ollama_connection():
            print(" 请先启动Ollama服务: ollama serve")
            return

        if self.enable_tts:
            if not self.check_tts_connection():
                print(" TTS服务不可用，将仅显示文字回复")
                self.enable_tts = False
            else:
                print(" 语音输出功能已启用")

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
                        not self.speech_recognizer.is_recording and
                        not self.is_processing):
                    self.speech_recognizer.start_recording()

                # 检测空格键释放
                if (not keyboard.is_pressed('space') and
                        self.speech_recognizer.is_recording):
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


if __name__ == "__main__":
    # 检查NLTK资源
    try:
        import nltk

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

    print("\n" + "=" * 60)

    # 运行主程序
    chat_system = VoiceChatSystem(enable_tts=True)
    chat_system.run()