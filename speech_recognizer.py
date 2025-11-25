import warnings
import whisper
import sounddevice as sd
import numpy as np
import wave
import os
import time
from threading import Lock
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SpeechRecognizer:
    def __init__(self, model_size="base"):
        """初始化语音识别器"""
        logger.info("初始化Whisper模型...")

        # 抑制Whisper的警告
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.model = whisper.load_model(model_size)

        logger.info(f"Whisper {model_size} 模型加载完成")

        # 音频参数
        self.sample_rate = 16000
        self.is_recording = False
        self.audio_data = []
        self.temp_file = "temp_audio.wav"
        self.recording_lock = Lock()
        self.last_recognition_time = 0  # 防止频繁识别

    def start_recording(self):
        """开始录音"""
        with self.recording_lock:
            if self.is_recording:
                logger.warning("已经在录音中")
                return

            # 检查是否过于频繁
            current_time = time.time()
            if current_time - self.last_recognition_time < 2:  # 2秒内不能再次开始
                logger.warning("操作过于频繁，请稍后再试")
                return

            logger.info("开始录音...（松开空格键停止）")
            self.is_recording = True
            self.audio_data = []

            def audio_callback(indata, frames, time, status):
                if self.is_recording and status:
                    logger.warning(f"音频流状态: {status}")
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
                logger.info("录音开始成功")
            except Exception as e:
                logger.error(f"录音设备初始化失败: {e}")
                self.is_recording = False

    def stop_recording_and_recognize(self):
        """停止录音并进行识别"""
        with self.recording_lock:
            if not self.is_recording:
                logger.warning("当前没有在录音")
                return None

            # 检查录音时长
            if len(self.audio_data) < 10:  # 至少10个数据块（约0.5秒）
                logger.warning("录音时间太短")
                self.is_recording = False
                return None

            logger.info("停止录音，正在识别...")
            self.is_recording = False

            try:
                if self.stream:
                    self.stream.stop()
                    self.stream.close()
            except Exception as e:
                logger.error(f"停止流时出错: {e}")

            try:
                full_audio = np.concatenate(self.audio_data, axis=0)

                # 检查音频数据是否有效
                if len(full_audio) < self.sample_rate * 0.5:  # 至少0.5秒
                    logger.warning("音频数据过短")
                    return None

                self._save_audio_to_file(full_audio)

                # 使用Whisper识别
                logger.info("开始语音识别...")
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    result = self.model.transcribe(self.temp_file)
                text = result["text"].strip()

                logger.info(f"识别结果: {text}")

                # 更新最后识别时间
                self.last_recognition_time = time.time()

                # 清理临时文件
                if os.path.exists(self.temp_file):
                    os.remove(self.temp_file)

                return text
            except Exception as e:
                logger.error(f"语音识别失败: {e}")
                return None

    def _save_audio_to_file(self, audio_data):
        """保存音频数据到文件"""
        try:
            with wave.open(self.temp_file, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_data.tobytes())
            logger.info(f"音频文件保存成功，大小: {len(audio_data)} 采样点")
        except Exception as e:
            logger.error(f"保存音频文件失败: {e}")

    @property
    def recording_status(self):
        """获取录音状态"""
        return self.is_recording