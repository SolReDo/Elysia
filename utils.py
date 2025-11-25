"""
工具函数模块
包含通用的辅助函数
"""
import re


def clean_text(text):
    """
    清理文本，移除特殊字符和多余空格
    """
    if not text:
        return ""

    # 移除多余空格和换行
    cleaned = re.sub(r'\s+', ' ', text).strip()
    return cleaned


def validate_audio_settings(sample_rate, channels):
    """
    验证音频设置是否有效
    """
    valid_sample_rates = [8000, 16000, 22050, 44100, 48000]
    valid_channels = [1, 2]

    if sample_rate not in valid_sample_rates:
        raise ValueError(f"不支持采样率: {sample_rate}")
    if channels not in valid_channels:
        raise ValueError(f"不支持声道数: {channels}")

    return True


def format_duration(seconds):
    """
    格式化时间 duration
    """
    if seconds < 60:
        return f"{seconds:.1f}秒"
    else:
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}分{seconds:.1f}秒"