"""配置：命令行 > 环境变量 > 配置文件 > 内置默认。

API key 只从环境变量或配置文件读，**故意不提供 --api-key 命令行参数**——
命令行参数会进 shell history，容易泄露。
"""

import os
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:             # pragma: no cover
    try:
        import tomli as tomllib  # 3.9 / 3.10：由 pyproject 的 tomli 依赖提供
    except ModuleNotFoundError:
        tomllib = None

APP_DIR = Path(os.environ.get("VSUB_HOME", Path.home() / ".vsub"))
CONFIG_NAME = "config.toml"

DEFAULTS = {
    "translate": {
        "provider": "ollama",
        "model": None,
        "base_url": None,
        "api_key": None,
        "api_key_env": "VSUB_API_KEY",
        "temperature": 0.2,
        "batch": 25,
        "jobs": 1,
        "tgt": "zh",
    },
    "asr": {
        "model": "small",
        "device": "cpu",
        "compute": "int8",
    },
    "output": {
        "mode": "bilingual",
        "src_first": False,
        "embed": False,
        "sidecar": True,
        "use_outdir": False,
        "keep_temp": False,
        "recursive": False,
        "force": False,
    },
}

TEMPLATE = """# vsub 配置（TOML）。命令行参数优先级高于本文件。
# 生成：vsub config init      验证：vsub config check

[translate]
# 后端：ollama（本地免费） / openai（兼容各家） / deepl / gemini
provider = "ollama"
model = "qwen3:8b"
# base_url 留空则用该后端的默认值；换服务商只改这一行
# base_url = "https://api.deepseek.com/v1"
# API key 建议放环境变量，不要写进文件
api_key_env = "VSUB_API_KEY"
tgt = "zh"
# jobs 是并发数：本地小显存保持 1，云 API 可以开到 4
jobs = 1

[asr]
model = "small"        # tiny / base / small / medium / large-v3
device = "cpu"         # 有 NVIDIA 卡改 cuda
compute = "int8"       # cuda 时可用 float16

[output]
mode = "bilingual"     # bilingual（译文在上）/ tgt / src
# src_first = true     # 双语改成原文在上
# embed = true         # 额外输出可开关的软字幕 mkv
# use_outdir = true    # 字幕收进 output 子目录
# keep_temp = true     # 保留 wav/segs.json 等中间产物
"""

# 环境变量 -> (section, key)
ENV_MAP = {
    "VSUB_PROVIDER": ("translate", "provider"),
    "VSUB_MODEL": ("translate", "model"),
    "VSUB_BASE_URL": ("translate", "base_url"),
    "VSUB_TGT": ("translate", "tgt"),
    "VSUB_JOBS": ("translate", "jobs"),
    "VSUB_ASR_MODEL": ("asr", "model"),
    "VSUB_DEVICE": ("asr", "device"),
    "VSUB_COMPUTE": ("asr", "compute"),
    "VSUB_MODE": ("output", "mode"),
}
# 老版本兼容：VSUB_OLLAMA 指向 Ollama 地址
LEGACY_ENV = {"VSUB_OLLAMA": ("translate", "base_url")}


def config_path(explicit=None):
    if explicit:
        return Path(explicit)
    env = os.environ.get("VSUB_CONFIG")
    if env:
        return Path(env)
    local = Path.cwd() / CONFIG_NAME
    if local.exists():
        return local
    return APP_DIR / CONFIG_NAME


def _deep_merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = dict(base.get(k, {}), **v) if isinstance(v, dict) else v
    return out


def load(path=None):
    """读配置文件并与默认值合并"""
    cfg = {s: dict(v) for s, v in DEFAULTS.items()}
    p = config_path(path)
    if p.exists():
        if tomllib is None:
            # 配置文件写了、却解析不了 —— 必须说出来，否则用户以为改的配置生效了
            print(f"[warn] 找到配置文件 {p}，但当前 Python 缺少 TOML 解析器"
                  f"（3.10 及以下需 pip install tomli），本次按默认值运行")
        else:
            try:
                data = tomllib.loads(p.read_text(encoding="utf-8"))
                cfg = _deep_merge(cfg, {k: v for k, v in data.items()
                                        if isinstance(v, dict)})
            except Exception as e:                              # noqa: BLE001
                print(f"[warn] 配置文件解析失败（{p}）：{e}，改用默认值")
    # 环境变量覆盖
    for env, (sec, key) in {**ENV_MAP, **LEGACY_ENV}.items():
        val = os.environ.get(env)
        if val:
            cfg[sec][key] = val
    return cfg


def resolve_api_key(cfg):
    """API key：配置文件明文 -> 环境变量（由 api_key_env 指定）"""
    t = cfg["translate"]
    if t.get("api_key"):
        return t["api_key"]
    env_name = t.get("api_key_env") or "VSUB_API_KEY"
    return os.environ.get(env_name, "")


def init_config(path=None, force=False):
    """写一份带注释的模板配置"""
    p = config_path(path)
    if p.exists() and not force:
        return p, False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(TEMPLATE, encoding="utf-8")
    return p, True


def effective(cfg, cli=None):
    """把命令行里显式给出的值盖到配置上"""
    if not cli:
        return cfg
    out = {s: dict(v) for s, v in cfg.items()}
    pairs = [
        ("provider", "translate", "provider"),
        ("model", "translate", "model"),
        ("base_url", "translate", "base_url"),
        ("tgt", "translate", "tgt"),
        ("batch", "translate", "batch"),
        ("jobs", "translate", "jobs"),
        ("temperature", "translate", "temperature"),
        ("asr_model", "asr", "model"),
        ("device", "asr", "device"),
        ("compute", "asr", "compute"),
        ("mode", "output", "mode"),
    ]
    for attr, sec, key in pairs:
        val = getattr(cli, attr, None)
        if val is not None:
            out[sec][key] = val
    for attr, key in (("src_first", "src_first"), ("embed", "embed"),
                      ("no_sidecar", "sidecar"), ("use_outdir", "use_outdir"),
                      ("keep_temp", "keep_temp"), ("recursive", "recursive"),
                      ("force", "force")):
        val = getattr(cli, attr, None)
        if val:
            out["output"][key] = False if key == "sidecar" else True
    return out
