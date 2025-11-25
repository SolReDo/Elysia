import requests
import json
from threading import Lock


class AIClient:
    def __init__(self, ollama_url="http://localhost:11434/api/chat", model_name="Elysia"):
        """初始化AI客户端"""
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.conversation_history = []
        self.history_lock = Lock()

    def get_ai_response_stream(self, user_input, response_callback=None, enable_tts=True, tts_service=None):
        """流式获取AI回复"""
        if not user_input or len(user_input.strip()) == 0:
            error_msg = "我没有听清楚您说的话，请再说一遍。"
            if response_callback:
                response_callback(error_msg, done=True)
            if enable_tts and tts_service:
                from threading import Thread
                Thread(target=lambda: tts_service.text_to_speech(error_msg), daemon=True).start()
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
                if enable_tts and full_response and tts_service:
                    print(" 正在生成语音回复...")
                    from threading import Thread
                    Thread(target=lambda: tts_service.text_to_speech(full_response), daemon=True).start()

                return full_response
            else:
                error_msg = f"API请求失败，状态码: {response.status_code}"
                print(f"\n{error_msg}")
                if response_callback:
                    response_callback(error_msg, done=True)
                if enable_tts and tts_service:
                    from threading import Thread
                    Thread(target=lambda: tts_service.text_to_speech("抱歉，AI服务暂时不可用。"), daemon=True).start()
                return error_msg

        except Exception as e:
            error_msg = f"AI回复错误: {e}"
            print(f"\n{error_msg}")
            if response_callback:
                response_callback(error_msg, done=True)
            if enable_tts and tts_service:
                from threading import Thread
                Thread(target=lambda: tts_service.text_to_speech("处理请求时出现错误。"), daemon=True).start()
            return error_msg

    def check_connection(self):
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