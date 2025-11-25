import warnings
import whisper
import sounddevice as sd
import numpy as np
import wave
import os
import time
from threading import Lock


class SpeechRecognizer:
    def __init__(self, model_size="base"):
        """初始化语音识别器"""
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
        self.recording_lock = Lock()

    def start_recording(self):
        """开始录音"""
        with self.recording_lock:
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
        with self.recording_lock:
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

    @property
    def recording_status(self):
        """获取录音状态"""
        return self.is_recording