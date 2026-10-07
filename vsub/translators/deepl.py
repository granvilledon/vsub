"""DeepL 后端（机器翻译 API，不走大模型 prompt）。

免费版 https://api-free.deepl.com/v2，专业版 https://api.deepl.com/v2
"""

import json
import urllib.parse
import urllib.request

from ..langs import DEEPL_LANG
from .base import BaseTranslator


class DeepLTranslator(BaseTranslator):
    """DeepL 是纯翻译 API，没有 system prompt，所以直接覆写 translate_batch。"""

    name = "deepl"
    needs_api_key = True
    default_model = "deepl"
    default_base_url = "https://api-free.deepl.com/v2"

    def __init__(self, base_url=None, api_key=None, **kwargs):
        super().__init__(**kwargs)
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.api_key = api_key or ""

    def describe(self):
        return f"deepl@{self.base_url}"

    @staticmethod
    def _code(lang):
        key = (lang or "").lower()
        if key in DEEPL_LANG:
            return DEEPL_LANG[key]
        return key.split("-")[0].upper()      # 兜底：直接大写

    def translate_batch(self, items, tgt_lang, src_lang, glossary=None, retries=2):
        if not self.api_key:
            raise RuntimeError("缺少 DeepL key：设置 VSUB_API_KEY 或配置文件 [translate] api_key")

        data = urllib.parse.urlencode({
            "target_lang": self._code(tgt_lang),
            "source_lang": self._code(src_lang),
            "tag_handling": "",
        }, doseq=True).encode("utf-8")
        for it in items:
            data += b"&" + urllib.parse.urlencode({"text": it["t"]}).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/translate", data=data,
            headers={"Authorization": f"DeepL-Auth-Key {self.api_key}",
                     "Content-Type": "application/x-www-form-urlencoded"},
        )
        last_err = None
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    out = json.loads(resp.read().decode("utf-8"))
                trs = out.get("translations") or []
                if len(trs) != len(items):
                    raise RuntimeError(f"返回条数 {len(trs)} != 请求条数 {len(items)}")
                return [(it["i"], (t.get("text") or "").strip())
                        for it, t in zip(items, trs)]
            except Exception as e:                          # noqa: BLE001
                last_err = e
        raise RuntimeError(f"DeepL 翻译失败: {last_err}")
