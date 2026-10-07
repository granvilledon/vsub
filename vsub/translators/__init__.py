"""翻译后端注册表。新增后端：写个子类，然后注册到这里。"""

from .base import BaseTranslator  # noqa: F401
from .deepl import DeepLTranslator
from .gemini import GeminiTranslator
from .ollama import OllamaTranslator
from .openai_compat import OpenAICompatTranslator

PROVIDERS = {
    "ollama": OllamaTranslator,
    "openai": OpenAICompatTranslator,
    "deepl": DeepLTranslator,
    "gemini": GeminiTranslator,
}

# 别名，方便命令行里随手写
ALIASES = {
    "local": "ollama",
    "lmstudio": "openai",
    "vllm": "openai",
    "deepseek": "openai",
    "moonshot": "openai",
    "kimi": "openai",
    "qwen": "openai",
    "siliconflow": "openai",
    "groq": "openai",
    "google": "gemini",
}


def normalize(name):
    key = (name or "ollama").lower().strip()
    return ALIASES.get(key, key)


def get_translator(name="ollama", model=None, base_url=None, api_key=None,
                   temperature=0.2, timeout=600, **kwargs):
    """按名字构造翻译后端"""
    key = normalize(name)
    if key not in PROVIDERS:
        raise SystemExit(
            f"未知翻译后端 {name!r}。可选：{', '.join(sorted(PROVIDERS))}")
    cls = PROVIDERS[key]
    kw = dict(model=model, temperature=temperature, timeout=timeout, **kwargs)
    if base_url is not None:
        kw["base_url"] = base_url
    if hasattr(cls, "api_key") or cls.needs_api_key:
        kw["api_key"] = api_key
    return cls(**kw)
