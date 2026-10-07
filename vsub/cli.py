"""命令行入口。

用法：
  vsub 视频.mp4                 默认：外挂字幕 + 自动识别语言 + 翻译成中文
  vsub D:\\我的视频              整个文件夹批量
  vsub config init              生成配置文件
  vsub config check             发一句话试翻，验证后端连通
"""

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from . import config as cfgmod
from .media import collect_videos
from .utils import log, setup_stdio

USAGE = """
============================================================
  vsub —— 视频字幕生成 + AI 翻译
============================================================

用法一：把【视频文件】或【整个文件夹】拖到 vsub.bat 上
        （也可把 vsub.bat 复制到视频文件夹里双击）

用法二：命令行
        vsub 视频.mp4
        vsub D:\\我的视频 --recursive
        vsub 视频.mp4 --provider openai --model gpt-4o-mini

默认行为：自动识别语言 -> 翻译成中文 -> 字幕放在视频旁边（同名 srt，
播放器自动加载），原视频一个字节都不动；中间产物跑完自动清理。

常用参数：
  --provider ollama|openai|deepl|gemini   翻译后端（默认 ollama）
  --base-url URL                          换服务商只改这个
  --model 名称                            翻译模型
  --asr-model small|medium|large-v3       ASR 模型
  --mode bilingual|tgt|src                默认双语（译文在上/原文在下）
  --embed                                 另出可开关的软字幕 mkv（无损）
  --tgt zh                                目标语言
  vsub config init / show / check         配置管理

注：硬烧录（--burn）不做——它要重新编码，画质有损、字幕关不掉且不可逆。
详见 README.md
"""


def build_parser():
    ap = argparse.ArgumentParser(
        prog="vsub", description="视频字幕生成 + AI 翻译（本地识别 + 可插拔翻译后端）",
        add_help=True)
    ap.add_argument("video", nargs="*",
                    help="视频文件 / 含视频的文件夹，可一次传多个")
    ap.add_argument("--src", default=None, help="源语言代码，默认自动检测")
    ap.add_argument("--tgt", default=None, help="目标语言代码，默认 zh")
    ap.add_argument("--provider", default=None,
                    help="翻译后端：ollama / openai / deepl / gemini")
    ap.add_argument("--model", default=None, help="翻译模型名")
    ap.add_argument("--base-url", default=None, help="翻译服务地址（换服务商用）")
    ap.add_argument("--asr-model", default=None,
                    help="ASR 模型：tiny/base/small/medium/large-v3，或本地目录")
    ap.add_argument("--device", default=None, help="ASR 设备：cpu / cuda")
    ap.add_argument("--compute", default=None, help="ASR 精度：int8 / float16")
    ap.add_argument("--mode", default=None, choices=["src", "tgt", "bilingual"])
    ap.add_argument("--src-first", action="store_true", help="双语字幕原文在上")
    ap.add_argument("--batch", type=int, default=None, help="每批发给模型的字幕条数")
    ap.add_argument("--jobs", type=int, default=None,
                    help="翻译并发数（本地小显存保持 1）")
    ap.add_argument("--temperature", type=float, default=None, help="翻译温度")
    ap.add_argument("--glossary", default=None, help="术语表 JSON 文件")
    ap.add_argument("--embed", action="store_true", help="额外输出软字幕 mkv")
    ap.add_argument("--no-sidecar", action="store_true", help="不输出视频旁的同名 srt")
    ap.add_argument("--use-outdir", action="store_true", help="字幕收进 output 子目录")
    ap.add_argument("--keep-temp", action="store_true", help="保留中间产物")
    ap.add_argument("--recursive", action="store_true", help="连子文件夹一起扫")
    ap.add_argument("--force", action="store_true", help="已有字幕也重做")
    ap.add_argument("--config", default=None, help="指定配置文件路径")
    ap.add_argument("--skip-translate", action="store_true", help="只识别不翻译")
    ap.add_argument("--version", action="store_true", help="打印版本号")
    # 旧参数保留但隐藏，避免历史命令报错
    ap.add_argument("--burn", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--clean", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-outdir", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--outdir", default=None, help=argparse.SUPPRESS)
    return ap


def cmd_run(argv):
    ap = build_parser()
    args = ap.parse_args(argv)

    if args.version:
        print(f"vsub {__version__}")
        return 0

    if args.burn:
        log("=" * 58)
        log("--burn（硬烧录）不做：它会重新编码，画质有损、字幕关不掉且不可逆。")
        log("替代：默认外挂 .srt（原视频不动），或 --embed 出无损可开关的软字幕 mkv。")
        log("=" * 58)
        return 1

    # 便携用法：bat 复制到视频文件夹后双击，没传路径就处理当前目录
    if not args.video:
        here = Path.cwd().resolve()
        home = Path(__file__).resolve().parent.parent
        found = [] if here == home else collect_videos(here, False,
                                                       exclude=here / "output")
        if found:
            log(f"未指定输入 → 检测到本文件夹内有 {len(found)} 个视频，"
                f"直接处理：{here}")
            log("默认只出外挂字幕，原视频一个字节都不动；不想跑现在按 Ctrl+C 中止")
            args.video = [str(here)]
        else:
            print(USAGE.strip())
            return 2

    cfg = cfgmod.load(args.config)
    cfg = cfgmod.effective(cfg, args)
    if args.skip_translate:
        cfg["translate"]["tgt"] = None

    glossary = None
    if args.glossary and Path(args.glossary).exists():
        glossary = json.loads(Path(args.glossary).read_text(encoding="utf-8"))
        log(f"载入术语表 {len(glossary)} 条")

    from .pipeline import run
    return run(cfg, args.video, args.src, glossary)


_CHECK_OVERRIDE = {}        # `config check --provider/--model/--base-url` 的临时覆盖


def cmd_config(argv):
    ap = argparse.ArgumentParser(prog="vsub config")
    ap.add_argument("action", choices=["init", "show", "path", "check"])
    ap.add_argument("--config", default=None)
    ap.add_argument("--force", action="store_true")
    # check 时可以临时覆盖，先试通再写进配置
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--tgt", default=None)
    a = ap.parse_args(argv)

    if a.action == "check":
        for attr, key in (("provider", "provider"), ("model", "model"),
                          ("base_url", "base_url"), ("tgt", "tgt")):
            val = getattr(a, attr, None)
            if val:
                _CHECK_OVERRIDE[key] = val

    if a.action == "init":
        p, created = cfgmod.init_config(a.config, a.force)
        print(f"{'已生成' if created else '已存在'}：{p}")
        if created:
            print("改完记得跑：vsub config check")
        return 0
    if a.action == "path":
        print(cfgmod.config_path(a.config))
        return 0
    if a.action == "show":
        cfg = cfgmod.load(a.config)
        print(f"# 配置文件：{cfgmod.config_path(a.config)}")
        for sec, kv in cfg.items():
            print(f"\n[{sec}]")
            for k, v in kv.items():
                if k == "api_key" and v:
                    v = "***"      # 不回显明文
                print(f"{k} = {v!r}")
        return 0

    # check：发一句话试翻，验证后端连通与鉴权
    cfg = cfgmod.load(a.config)
    cfg["translate"].update(_CHECK_OVERRIDE)
    from .config import resolve_api_key
    from .translators import get_translator
    t = cfg["translate"]
    tr = get_translator(
        t.get("provider"), model=t.get("model"), base_url=t.get("base_url"),
        api_key=resolve_api_key(cfg), temperature=float(t.get("temperature", 0.2)))
    log(f"后端：{tr.describe()}")
    log(f"目标语言：{t.get('tgt')}")
    items = [{"i": 0, "t": "Hello, this is a connectivity test."},
             {"i": 1, "t": "If you can read this, everything works."}]
    t0 = time.time()
    try:
        # 直接调 complete，让 HTTP/鉴权异常原样抛出来（translate_batch 会吞掉重试）
        system, user = tr.build_messages(items, t.get("tgt") or "zh", "en")
        raw = tr.complete(system, user)
    except Exception as e:                                  # noqa: BLE001
        log(f"!! 连通失败：{type(e).__name__}: {e}")
        log("   检查：base_url 是否正确 / 模型是否已拉取 / API key 是否有效")
        return 1
    from .translators.base import parse_translation
    res = parse_translation(raw, items)
    dt = time.time() - t0
    if not res:
        log(f"!! 连通失败：拿到了响应但解析不出译文：{raw[:200]!r}")
        return 1
    for i, txt in res:
        log(f"  [{i}] {txt}")
    log(f"连通正常，拿到 {len(res)}/{len(items)} 条译文，耗时 {dt:.1f} 秒")
    return 0


def main(argv=None):
    setup_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("config", "cfg"):
        return cmd_config(argv[1:])
    return cmd_run(argv)


if __name__ == "__main__":
    sys.exit(main())
