"""处理流程：抽音 -> 转写 -> 翻译 -> 输出字幕 ->（可选）内挂。"""

import json
import shutil
import time
from pathlib import Path

from . import asr
from .media import collect_videos, embed, extract_audio
from .srt import write_srt
from .utils import _fmt_eta, log

STATUS_OK, STATUS_SKIP, STATUS_FAIL = "OK", "SKIP", "FAIL"


def process_video(video, cfg, translator, outdir, src=None,
                  glossary=None, model=None):
    """处理单个视频。model 由外层传入以便批量复用"""
    t = cfg["translate"]
    a = cfg["asr"]
    o = cfg["output"]
    stem = video.stem
    cache = outdir / f"{stem}.segs.json"
    meta = outdir / f"{stem}.meta.json"   # 记住识别出的源语言，避免二次跑时被当成英语

    # 断点续跑：已有外挂字幕就跳过
    side = video.with_suffix(".srt")
    if side.exists() and not o.get("force"):
        log(f"已有字幕 {side.name}，跳过（加 --force 强制重做）")
        return STATUS_SKIP

    log(f"处理：{video.name}")

    # 1) 抽音
    wav = outdir / f"{stem}.wav"
    if not wav.exists():
        extract_audio(video, wav)

    # 2) ASR（源语言自动识别，结果记进 meta 供下次复用）
    if cache.exists():
        segs = json.loads(cache.read_text(encoding="utf-8"))
        log(f"复用已有转写缓存：{len(segs)} 条（删掉 {cache.name} 可强制重跑）")
        src_lang = src
        if src_lang is None and meta.exists():
            src_lang = json.loads(meta.read_text(encoding="utf-8")).get("src")
    else:
        segs, info = asr.transcribe(wav, a["model"], src, a["device"],
                                    a["compute"], model=model)
        src_lang = src or getattr(info, "language", None)

    if src_lang is None:
        src_lang, _ = asr.detect_language(wav, a["model"], a["device"],
                                          a["compute"], model=model)

    meta.write_text(json.dumps(
        {"src": src_lang, "tgt": t["tgt"], "asr": a["model"],
         "translator": translator.describe(),
         "ts": time.strftime("%Y-%m-%d %H:%M:%S")},
        ensure_ascii=False, indent=1), encoding="utf-8")

    from .langs import lang_name
    log(f"源语言：{lang_name(src_lang)}（{src_lang}）")

    # 3) 翻译
    translated = False
    if not t.get("tgt"):
        log("跳过翻译（--skip-translate 或未指定目标语言），字幕只含原文")
    elif t["tgt"] != (src_lang or "").split("-")[0]:
        translator.translate_all(segs, t["tgt"], src_lang, glossary,
                                 int(t.get("batch", 25)), int(t.get("jobs", 1)),
                                 cache)
        translated = True
    else:
        log(f"源语言就是{lang_name(src_lang)}，无需翻译")

    # 4) 输出字幕（默认就在视频旁边，播放器靠同名自动加载）
    if Path(outdir).resolve() == video.parent.resolve():
        main_srt = video.with_suffix(".srt")
    else:
        main_srt = Path(outdir) / f"{stem}.{o['mode']}.srt"
    write_srt(segs, main_srt, o["mode"], tgt_first=not o.get("src_first"))
    log(f"字幕已生成: {main_srt}")

    tracks = []
    if translated:
        tgt_srt = Path(outdir) / f"{stem}.{t['tgt']}.srt"
        orig_srt = Path(outdir) / f"{stem}.orig.srt"
        write_srt(segs, tgt_srt, "tgt")
        write_srt(segs, orig_srt, "src")
        log(f"另存：{tgt_srt.name}（译文）/ {orig_srt.name}（原文）")
        tracks = [(tgt_srt, t["tgt"]), (orig_srt, src_lang)]

    # 4.5) sidecar：字幕不在视频旁边时，复制一份同名 srt 过去
    if o.get("sidecar") and side.resolve() != Path(main_srt).resolve():
        if side.exists():
            bak = side.with_suffix(".srt.bak")
            shutil.copyfile(side, bak)      # 绝不覆盖用户原有的字幕
            log(f"发现已有同名字幕，已备份为 {bak.name}")
        shutil.copyfile(main_srt, side)
        log(f"外挂字幕（与视频同名，播放器自动加载）: {side}")
        if translated:
            side_t = video.parent / f"{stem}.{t['tgt']}.srt"
            if side_t.resolve() != tgt_srt.resolve() and not side_t.exists():
                shutil.copyfile(tgt_srt, side_t)
                log(f"外挂字幕（纯译文）: {side_t}")

    # 5) 内挂软字幕（无损可逆，可开关）
    if o.get("embed"):
        out = Path(outdir) / f"{stem}.soft.mkv"
        embed(video, tracks or [(main_srt, t["tgt"])], out)
        log(f"软字幕视频（{len(tracks) or 1} 条字幕轨，播放器可开关/切换）: {out}")

    # 6) 清理中间产物（wav 能还原全部人声，默认清掉）
    if not o.get("keep_temp"):
        for f in (wav, cache, meta):
            try:
                Path(f).unlink()
            except Exception:                               # noqa: BLE001
                pass
        log("已清理中间产物（wav / segs.json / meta.json），只留字幕与成片")

    return STATUS_OK


def run(cfg, paths, src=None, glossary=None):
    """入口：收集视频 -> 加载模型 -> 逐个处理 -> 汇总"""
    from .config import resolve_api_key
    from .translators import get_translator

    t = cfg["translate"]
    o = cfg["output"]
    translator = get_translator(
        t.get("provider"), model=t.get("model"), base_url=t.get("base_url"),
        api_key=resolve_api_key(cfg),
        temperature=float(t.get("temperature", 0.2)),
        timeout=int(t.get("timeout", 600)))
    log(f"翻译后端：{translator.describe()}")

    src_paths = [Path(p) for p in paths]
    missing = [p for p in src_paths if not p.exists()]
    if missing:
        for p in missing:
            log(f"找不到路径: {p}")
        return 1

    # 输出目录：默认不建子目录，字幕直接放视频旁边
    first = src_paths[0]
    base = first if first.is_dir() else first.parent
    if o.get("use_outdir") and base.name.lower() != "output":
        outdir = base / "output"
    else:
        outdir = base
    outdir = Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    # 排除输出目录，避免把上次的产物当输入；但输出目录就是输入目录时不能排
    excl = None if outdir in [ (p if p.is_dir() else p.parent).resolve()
                               for p in src_paths ] else outdir
    videos, seen = [], set()
    for p in src_paths:
        for v in collect_videos(p, o.get("recursive"), exclude=excl):
            if v not in seen:
                seen.add(v)
                videos.append(v)
    if not videos:
        log("没找到视频文件")
        return 1

    # 模型只加载一次，批量共享（每个视频省约 2 秒）
    need_asr = any(not (outdir / f"{v.stem}.segs.json").exists() or o.get("force")
                   for v in videos)
    model = asr.load_model(cfg["asr"]["model"], cfg["asr"]["device"],
                           cfg["asr"]["compute"]) if need_asr else None

    t0 = time.time()
    results = []
    n = len(videos)
    for i, v in enumerate(videos, 1):
        if n > 1:
            eta = _fmt_eta((time.time() - t0) * (n - i + 1) / (i - 1)) if i > 1 else ""
            log(f"\n===== [{i}/{n}] {v.name} ====={eta}")
        try:
            results.append((v.name, process_video(v, cfg, translator, outdir,
                                                  src, glossary, model)))
        except KeyboardInterrupt:
            log("用户中断")
            break
        except Exception as e:                              # noqa: BLE001
            log(f"!! 失败：{type(e).__name__}: {e}")
            results.append((v.name, STATUS_FAIL))

    if n > 1:
        ok = sum(1 for _, r in results if r == STATUS_OK)
        skip = sum(1 for _, r in results if r == STATUS_SKIP)
        fail = sum(1 for _, r in results if r == STATUS_FAIL)
        log("\n===== 汇总 =====")
        log(f"成功 {ok} / 跳过(已有字幕) {skip} / 失败 {fail}，"
            f"共 {len(results)} 个，耗时 {(time.time() - t0) / 60:.1f} 分钟")
        failed = [nm for nm, r in results if r == STATUS_FAIL]
        if failed:
            log("失败的文件：" + "、".join(failed))
    else:
        log("全部完成。")
    return 0
