#!/usr/bin/env python3
"""
主程序入口文件
仅负责初始化系统和启动主循环
"""
import nltk
from voice_chat_system import VoiceChatSystem


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


def main():
    """主函数"""
    print("\n" + "=" * 60)

    # 检查NLTK资源
    check_nltk_resources()
    print("\n" + "=" * 60)

    # 运行主程序
    chat_system = VoiceChatSystem(enable_tts=True)
    chat_system.run()


if __name__ == "__main__":
    main()