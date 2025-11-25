import requests
import pygame
import time
import os
import re
from threading import Lock


class TTSService:
    def __init__(self, tts_url="http://127.0.0.1:9880"):
        """初始化TTS服务"""
        self.tts_url = tts_url
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

    def check_connection(self):
        """检查TTS服务连接"""
        if not self.tts_enabled:
            return True

        try:
            test_text = "测试"
            params = {
                "text": test_text,
                "text_language": "zh"
            }
            response = requests.get(self.tts_url, params=params, timeout=15)
            if response.status_code == 200:
                print(" TTS服务连接正常")
                return True
            else:
                print(" TTS服务异常")
                return False
        except Exception as e:
            print(f" 无法连接到TTS服务: {e}")
            return False