"""SRT 读写与断句重排。"""

import re


def srt_time(t):
    """秒 -> SRT 时间戳。

    先整体换算成毫秒再拆时分秒，进位天然正确。
    旧实现是「秒截断 + 毫秒四舍五入」，ms 凑到 1000 时只给秒 +1，
    于是 59.9996 会输出 00:00:60,000（秒=60），3599.9996 会输出 00:59:60,000，
    都是 SRT 规范不允许的值，ffmpeg 会整条解析失败。
    """
    ms = max(0, int(round(float(t or 0) * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segs, path, mode="bilingual", tgt_first=True):
    """写 SRT。mode: src | tgt | bilingual

    bilingual 默认【译文在上、原文在下】——先看译文，需要时再瞄一眼原文。
    想反过来（原文在上）传 tgt_first=False。
    """
    from pathlib import Path

    lines = []
    for i, s in enumerate(segs, 1):
        src = (s.get("text") or "").strip()
        tgt = (s.get("tgt") or "").strip()
        if mode == "src":
            body = src
        elif mode == "tgt":
            body = tgt if tgt else src
        else:
            if tgt and tgt != src:
                body = f"{tgt}\n{src}" if tgt_first else f"{src}\n{tgt}"
            else:
                body = src
        lines.append(f"{i}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{body}\n")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return path


def _width(s):
    """视觉宽度：CJK 算 2"""
    return sum(2 if ord(c) > 0x2E80 else 1 for c in s)


def regroup(raw, max_chars=72, max_dur=6.5, min_dur=0.7, min_chars=16):
    """按语义重断句：句子结尾(.?!，且够长)优先断，其次逗号，最后才是硬字数/时长截断。

    直接按字数硬切会得到 "Welcome back to the show. Today we're" 这种半句，
    译文会跟着碎掉——这是实测踩过的坑，别改回纯字数切分。
    """
    out = []

    def flush(cur, cur_s, cur_e):
        t = "".join(cur).strip()
        if t:
            out.append({"start": cur_s, "end": max(cur_e, cur_s + min_dur), "text": t})

    for seg in raw:
        words = seg["words"]
        if not words:
            out.append({"start": seg["start"],
                        "end": max(seg["end"], seg["start"] + min_dur),
                        "text": seg["text"]})
            continue

        cur, cur_w, cur_s, cur_e = [], 0, None, None
        for w in words:
            cur.append(w["w"])
            cur_w += _width(w["w"])
            if cur_s is None:
                cur_s = w["s"]
            cur_e = w["e"]

            txt = "".join(cur).strip()
            sent_end = bool(re.search(r"[.!?。！？][\"'\"'”’]?$", txt))
            comma_end = bool(re.search(r"[,;:，；：]$", txt))
            too_long = cur_w >= max_chars or (cur_e - cur_s) > max_dur

            if sent_end and cur_w >= min_chars or too_long or (
                    comma_end and cur_w >= max_chars * 0.6):
                flush(cur, cur_s, cur_e)
                cur, cur_w, cur_s, cur_e = [], 0, None, None
        flush(cur, cur_s, cur_e)

    # 去掉与上一条时间间隔过短的碎片，合并时间戳重叠
    cleaned = []
    for s in out:
        if cleaned and s["start"] < cleaned[-1]["end"] - 0.05:
            if _width(cleaned[-1]["text"]) + _width(s["text"]) <= max_chars:
                cleaned[-1]["text"] = (cleaned[-1]["text"] + " " + s["text"]).strip()
                cleaned[-1]["end"] = max(cleaned[-1]["end"], s["end"])
                continue
            cleaned[-1]["end"] = s["start"]
        cleaned.append(s)

    # 合并过短碎片（日语/中文分词容易切出「方法」这种孤字条）
    merged = []
    for s in cleaned:
        if merged and _width(s["text"]) < 8 and (s["start"] - merged[-1]["end"]) < 1.5:
            prev = merged[-1]["text"]
            gap = "" if (ord(prev[-1]) > 0x2E80 or ord(s["text"][0]) > 0x2E80) else " "
            merged[-1]["text"] = prev + gap + s["text"]
            merged[-1]["end"] = s["end"]
            continue
        merged.append(s)

    return merged
