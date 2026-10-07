"""faster-whisper 转写。

关键坑（改代码前先看）：
  * 不要依赖 `av` 解码音频。av>=19 删掉了 `av.open(metadata_errors=...)`，
    与 faster-whisper 1.x 不兼容；而 `av<15` 在 Python 3.13 没有预编译 wheel、
    本地编译会失败。所以这里用标准库 `wave` 读 PCM 再转 ndarray 喂给模型。
  * Windows 上 ctranslate2 需要手动 add_dll_directory 才能找到 pip 装的 CUDA 库。
"""

import os
import time
from pathlib import Path

from .langs import lang_name
from .srt import regroup
from .utils import log, progress

# 本地模型目录：仓库根/models，或 ~/.cache/vsub/models
MODEL_DIRS = [
    Path(__file__).resolve().parent.parent / "models",
    Path.home() / ".cache" / "vsub" / "models",
]


def prepare_cuda():
    """Windows 下让 ctranslate2 找到 pip 安装的 CUDA / cuDNN 动态库"""
    if os.name != "nt":
        return
    import importlib.util
    for pkg in ("nvidia.cublas.bin", "nvidia.cudnn.bin", "nvidia.cuda_runtime.bin"):
        try:
            spec = importlib.util.find_spec(pkg)
            for loc in (getattr(spec, "submodule_search_locations", None) or []):
                os.add_dll_directory(loc)
                os.environ["PATH"] = loc + os.pathsep + os.environ["PATH"]
        except Exception:
            pass


def resolve_model(name):
    """优先用本地已下载的模型目录，避免每次联网拉 HF"""
    p = Path(name)
    if p.exists() and (p / "model.bin").exists():
        return str(p)
    for base in MODEL_DIRS:
        local = base / f"faster-whisper-{name}"
        if local.exists() and (local / "model.bin").exists():
            return str(local)
    return name


def load_wav(path):
    """标准库读 16bit PCM wav -> float32 ndarray（绕开 av）"""
    import wave

    import numpy as np
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def load_model(model_size="small", device="cpu", compute_type="int8"):
    """批量处理时复用同一个实例，避免每个视频都重新加载（每次约 2 秒）"""
    from faster_whisper import WhisperModel
    if device == "cuda":
        prepare_cuda()
    resolved = resolve_model(model_size)
    log(f"加载 faster-whisper 模型: {resolved} (device={device}, {compute_type})")
    return WhisperModel(resolved, device=device, compute_type=compute_type)


def transcribe(wav, model_size="small", language=None, device="cpu",
               compute_type="int8", max_chars=72, max_dur=6.5, model=None):
    """返回按字幕规范重新断句后的 segments 列表 + whisper info"""
    if model is None:
        model = load_model(model_size, device, compute_type)

    audio = load_wav(wav)
    log(f"音频载入: {len(audio) / 16000:.1f} 秒")

    segs_gen, info = model.transcribe(
        audio, language=language, vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=350),
        word_timestamps=True, beam_size=5,
        condition_on_previous_text=False,
    )

    raw = []
    total = len(audio) / 16000.0
    t0 = time.time()
    for seg in segs_gen:
        raw.append({
            "start": seg.start, "end": seg.end,
            "text": (seg.text or "").strip(),
            "words": [{"s": w.start, "e": w.end, "w": w.word}
                      for w in (seg.words or []) if w.start is not None],
        })
        progress(seg.end, total, prefix="  转写", suffix=" 秒", t0=t0)
    if raw:
        progress(raw[-1]["end"], total, prefix="  转写", suffix=" 秒", t0=t0)
    el = time.time() - t0
    log(f"转写完成：{len(raw)} 个原始片段，检测语言={info.language} "
        f"(置信度 {getattr(info, 'language_probability', 0):.2f})，"
        f"耗时 {el:.1f} 秒（{total / max(el, 0.1):.1f}x 实时）")

    # CJK / 无空格语言视觉密度高，同样宽度下字数翻倍，断句要收窄
    lang = (getattr(info, "language", "") or "").split("-")[0]
    if lang in ("ja", "ko", "zh", "yue", "th"):
        max_chars, max_dur = min(max_chars, 46), min(max_dur, 5.5)
        log(f"检测到 {lang_name(lang)}，断句宽度收窄到 {max_chars}")

    return regroup(raw, max_chars=max_chars, max_dur=max_dur), info


def detect_language(wav, model_size="small", device="cpu", compute_type="int8",
                    model=None):
    """缓存里没记语言时，用前 30 秒音频单独检测一次"""
    if model is None:
        model = load_model(model_size, device, compute_type)
    audio = load_wav(wav)[:30 * 16000]
    lang, prob, _ = model.detect_language(audio)
    log(f"语言检测：{lang_name(lang)}（{lang}），置信度 {prob:.2f}")
    return lang, prob
