"""Ollama 后端（本地 / 局域网，免费，不需要 API key）。"""

import json
import urllib.request

from .base import BaseTranslator


class OllamaTranslator(BaseTranslator):
    """Ollama 的 /api/chat。默认 127.0.0.1:11434，可指向局域网任意一台机器。"""

    name = "ollama"
    default_model = "qwen3:8b"
    default_base_url = "http://127.0.0.1:11434"

    def __init__(self, base_url=None, **kwargs):
        super().__init__(**kwargs)
        self.base_url = (base_url or self.default_base_url).rstrip("/")

    def describe(self):
        return f"ollama@{self.base_url} / {self.model}"

    def complete(self, system, user):
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,          # 关掉思考链，否则输出里混一大段推理
            "options": {"temperature": self.temperature, "num_ctx": 8192,
                        "num_predict": 4096, "stop": ["\n\n\n"]},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("message") or {}).get("content", "")
