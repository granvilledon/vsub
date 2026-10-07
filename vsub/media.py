"""ffmpeg / ffprobe 相关：抽音、内挂软字幕、视频收集。"""

import subprocess
import time
from pathlib import Path

from .langs import iso3, lang_name
from .utils import log, progress

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".flv", ".wmv", ".webm",
             ".m4v", ".ts", ".mpg", ".mpeg", ".rmvb", ".vob", ".3gp"}


def probe_duration(video):
    """ffprobe 读视频时长（秒）；失败返回 0"""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(video)],
        capture_output=True, text=True, errors="ignore")
    try:
        return float((r.stdout or "").strip().splitlines()[0])
    except Exception:
        return 0.0


def extract_audio(video, out_wav):
    """抽 16k 单声道 PCM。带进度；progress 模式异常时回退普通模式"""
    cmd = ["ffmpeg", "-y", "-i", str(video), "-vn",
           "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_wav)]

    dur = probe_duration(video)
    if dur > 0:
        p = subprocess.Popen(cmd + ["-progress", "pipe:1", "-nostats"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             text=True, errors="ignore")
        t0 = time.time()
        for line in p.stdout:
            if line.startswith("out_time_ms="):
                try:
                    progress(int(line.split("=", 1)[1].strip()) / 1e6, dur,
                             prefix="  抽音", suffix=" 秒", t0=t0)
                except Exception:
                    pass
        p.stdout.close()
        p.wait()
        if p.returncode == 0 and Path(out_wav).exists():
            return out_wav
        log("  抽音进度模式异常，回退普通模式重试")

    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg 抽音失败:\n" + r.stderr.decode("utf-8", "ignore")[-800:])
    return out_wav


def embed(video, tracks, out):
    """内挂软字幕到 MKV：支持多轨，播放器可自由开关 / 切换语言。

    tracks: [(srt路径, 语言代码), ...]，第一条成为默认轨。
    注意：mp4 不支持 srt codec（只有 mov_text），所以软字幕必须走 mkv。
    """
    tracks = [(Path(s).resolve(), lang) for s, lang in tracks if Path(s).exists()]
    if not tracks:
        raise RuntimeError("没有可挂载的字幕文件")

    cmd = ["ffmpeg", "-y", "-i", str(video)]
    for s, _ in tracks:
        cmd += ["-i", str(s)]
    cmd += ["-map", "0:v", "-map", "0:a?"]          # a?：无音轨的视频也不报错
    for k in range(len(tracks)):
        cmd += ["-map", str(k + 1)]
    cmd += ["-c", "copy", "-c:s", "srt"]
    for k, (_, lang) in enumerate(tracks):
        cmd += [f"-metadata:s:s:{k}", f"language={iso3(lang)}",
                f"-metadata:s:s:{k}", f"title={lang_name(lang)}"]
    cmd += [str(out)]

    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("内挂字幕失败:\n" + r.stderr.decode("utf-8", "ignore")[-800:])
    return out


def collect_videos(path, recursive=False, exclude=None):
    """传入文件就返回它一个，传入目录就收集目录里的视频"""
    p = Path(path)
    if p.is_file():
        return [p.resolve()]
    it = p.rglob("*") if recursive else p.glob("*")
    out = []
    for f in sorted(it):
        if f.suffix.lower() not in VIDEO_EXT or f.name.startswith("._"):
            continue
        if exclude:
            try:
                if Path(exclude).resolve() in f.resolve().parents:
                    continue        # 跳过输出目录，避免把上次的产物当输入
            except Exception:
                pass
        out.append(f.resolve())
    return out
