"""OpenAI 兼容后端。

一个 base_url 覆盖 OpenAI / DeepSeek / 月之暗面 / 通义千问 / 硅基流动 /
Groq / 本地 vLLM / LM Studio / Ollama 自己的 /v1 端点。
"""

import json
import urllib.error
import urllib.request

from .base import BaseTranslator


class OpenAICompatTranslator(BaseTranslator):
    name = "openai"
    needs_api_key = True
    default_model = "gpt-4o-mini"
    default_base_url = "https://api.openai.com/v1"

    def __init__(self, base_url=None, api_key=None, **kwargs):
        super().__init__(**kwargs)
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.api_key = api_key or ""

    def describe(self):
        return f"openai-compat@{self.base_url} / {self.model}"

    def complete(self, system, user):
        if not self.api_key:
            raise RuntimeError(
                "缺少 API key：设置环境变量 VSUB_API_KEY，或写进配置文件 [translate] api_key")
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "ignore")[:300]
            except Exception:                               # noqa: BLE001
                pass
            raise RuntimeError(f"API 返回 {e.code}: {body}") from None
        try:
            return data["choices"][0]["message"]["content"] or ""
        except Exception:                                   # noqa: BLE001
            raise RuntimeError(f"无法解析响应: {str(data)[:300]}") from None
