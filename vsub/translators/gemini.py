"""Google Gemini 后端（原生 generateContent API）。"""

import json
import urllib.error
import urllib.parse
import urllib.request

from .base import BaseTranslator


class GeminiTranslator(BaseTranslator):
    name = "gemini"
    needs_api_key = True
    default_model = "gemini-2.0-flash"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, base_url=None, api_key=None, **kwargs):
        super().__init__(**kwargs)
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.api_key = api_key or ""

    def describe(self):
        return f"gemini / {self.model}"

    def complete(self, system, user):
        if not self.api_key:
            raise RuntimeError("缺少 Gemini key：设置 VSUB_API_KEY 或配置文件 [translate] api_key")
        url = (f"{self.base_url}/models/{self.model}:generateContent"
               f"?key={urllib.parse.quote(self.api_key)}")
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": self.temperature},
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "ignore")[:300]
            except Exception:                               # noqa: BLE001
                pass
            raise RuntimeError(f"Gemini 返回 {e.code}: {body}") from None
        try:
            return "".join(p.get("text", "")
                           for p in data["candidates"][0]["content"]["parts"])
        except Exception:                                   # noqa: BLE001
            raise RuntimeError(f"无法解析响应: {str(data)[:300]}") from None
