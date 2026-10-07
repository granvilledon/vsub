"""翻译后端抽象。

所有 LLM 类后端只需要实现 `complete(system, user) -> str`，
分批、并发、缺译补翻、编号对齐、脏格式容错这些通用逻辑都在基类里。

这里的代码是实测踩出来的，改之前先想清楚：
  * 行协议 `编号|||译文` 而不是 JSON：Ollama 在 `format:"json"` 模式下
    生成完第一条就自己 EOS（28 条只译出 2 条），qwen 系列尤其明显。
  * `_fix_ids()`：断句碎时 LLM 会把第 6/7 条的内容写反，条数一致但编号
    集合对不上，必须按输出顺序重排。
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..langs import lang_name
from ..utils import log, progress


class BaseTranslator:
    """翻译后端基类。子类实现 complete()，或整个覆写 translate_batch()。"""

    name = "base"
    needs_api_key = False
    default_model = ""
    default_base_url = ""

    def __init__(self, model=None, temperature=0.2, timeout=600, **kwargs):
        self.model = model or self.default_model
        self.temperature = temperature
        self.timeout = timeout
        self.kwargs = kwargs

    # ---------------------------------------------------------- 子类实现
    def complete(self, system, user):
        """调用大模型，返回原始文本"""
        raise NotImplementedError

    def describe(self):
        return f"{self.name} / {self.model}"

    # ---------------------------------------------------------- 通用逻辑
    def build_messages(self, items, tgt_lang, src_lang, glossary=None):
        tgt_name = lang_name(tgt_lang)
        src_name = lang_name(src_lang)
        gl = ""
        if glossary:
            gl = "；".join(f"{k}->{v}" for k, v in glossary.items())
            gl = f"\n术语表（必须严格遵守）：{gl}"

        system = (
            f"你是专业字幕翻译引擎，擅长影视、访谈、教学类视频的字幕本地化。\n"
            f"任务：把{src_name}字幕翻译成{tgt_name}。\n"
            f"要求：\n"
            f"1. 口语化、自然、简洁，单条译文控制在 22 个{tgt_name}字以内，"
            f"与原文信息量对等，不增译不漏译\n"
            f"2. 保留说话人语气（疑问、感叹、口头禅），不要书面腔\n"
            f"3. 严格逐条对应：输入 N 条就必须输出 N 条，编号必须与输入完全一致，"
            f"绝不合并、绝不拆分、绝不省略、绝不调换顺序\n"
            f"   注意：这些字幕是按时间顺序排列的连续片段，某些条可能是半句话，"
            f"请按它在上下文里的含义翻译，不要脑补、不要重复前面的内容\n"
            f"4. 只输出译文文本本身，不要引号、不要任何解释"
            f"{gl}\n"
            f"输出格式（纯文本，禁止 JSON、禁止代码块、禁止多余空话）：\n"
            f"每行一条，严格写成：编号|||译文\n"
            f"例：\n3|||欢迎回到节目\n4|||今天我们要聊一个话题"
        )
        user = "\n".join(f"{it['i']}|||{it['t']}" for it in items)
        return system, f"待翻译（共 {len(items)} 条）：\n{user}"

    def translate_batch(self, items, tgt_lang, src_lang, glossary=None, retries=2):
        """items: [{'i':序号,'t':原文}] -> [(i, 译文)]"""
        system, user = self.build_messages(items, tgt_lang, src_lang, glossary)
        last_err = None
        for attempt in range(retries + 1):
            try:
                return parse_translation(self.complete(system, user), items)
            except Exception as e:                      # noqa: BLE001
                last_err = e
                time.sleep(2 * (attempt + 1))
        log(f"  !! 批次翻译失败（{len(items)} 条）：{last_err}")
        return [(it["i"], "") for it in items]

    def translate_all(self, segs, tgt_lang, src_lang, glossary=None,
                      batch=25, jobs=1, cache=None):
        """把 segs 里缺译文的条批量翻译，写回 segs[i]['tgt']"""
        todo = [i for i, s in enumerate(segs) if not (s.get("tgt") or "").strip()]
        if not todo:
            log("全部已有译文（命中缓存），跳过翻译")
            return

        # 按批次打包（条数 + 字符数双上限）
        batches, cur, cur_len = [], [], 0
        for i in todo:
            t = segs[i]["text"]
            if cur and (len(cur) >= batch or cur_len + len(t) > 1100):
                batches.append(cur)
                cur, cur_len = [], 0
            cur.append({"i": i, "t": t})
            cur_len += len(t)
        if cur:
            batches.append(cur)

        log(f"翻译：{len(todo)} 条 -> {len(batches)} 批，"
            f"并发 {jobs}，目标 {lang_name(tgt_lang)}（{self.describe()}）")
        done = 0
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as exe:
            for res in exe.map(
                    lambda b: self.translate_batch(b, tgt_lang, src_lang, glossary),
                    batches):
                for i, t in res:
                    if 0 <= i < len(segs) and t:
                        segs[i]["tgt"] = t
                done += 1
                progress(done, len(batches), prefix="  翻译", suffix=" 批", t0=t0)
                if cache and (done % 5 == 0 or done == len(batches)):
                    save_cache(cache, segs)

        # 补齐：LLM 偶尔漏条，小批量串行再翻一次
        miss = [i for i, s in enumerate(segs) if not (s.get("tgt") or "").strip()]
        if miss:
            log(f"  {len(miss)} 条缺失，改用小批（4 条）串行补翻…")
            t1 = time.time()
            chunks = [miss[k:k + 4] for k in range(0, len(miss), 4)]
            for ci, m in enumerate(chunks, 1):
                chunk = [{"i": i, "t": segs[i]["text"]} for i in m]
                for i, t in self.translate_batch(chunk, tgt_lang, src_lang, glossary):
                    if 0 <= i < len(segs) and t:
                        segs[i]["tgt"] = t
                progress(ci, len(chunks), prefix="  补翻", suffix=" 批", t0=t1)
            still = sum(1 for s in segs if not (s.get("tgt") or "").strip())
            if still:
                log(f"  !! 仍有 {still} 条未译出（保留原文）")
        if cache:
            save_cache(cache, segs)


# ---------------------------------------------------------------- 解析
def save_cache(path, segs):
    Path(path).write_text(json.dumps(segs, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def fix_ids(out, items):
    """LLM 偶尔把编号标错：条数一致但编号集合对不上时，按输出顺序重新对齐"""
    if len(out) != len(items):
        return out
    if {i for i, _ in out} == {it["i"] for it in items}:
        return out
    log("  (LLM 编号错乱，已按输出顺序重新对齐)")
    return [(it["i"], t) for it, (_, t) in zip(items, out)]


def parse_translation(content, items):
    """主解析行协议 `编号|||译文`，兼容 JSON / 纯编号行 / 裸行"""
    txt = (content or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", txt)
    if m:
        txt = m.group(1).strip()

    # 1) 行协议：编号|||译文
    out = []
    for line in txt.splitlines():
        line = line.strip().strip("`")
        mm = re.match(r"^\[?(\d+)\]?\s*[|｜]{2,3}\s*(.+)$", line)
        if mm:
            t = mm.group(2).strip().strip('"').strip("'")
            if t:
                out.append((int(mm.group(1)), t))
    if out:
        return fix_ids(out, items)

    # 2) JSON（对象或数组）
    s, e = txt.find("["), txt.rfind("]")
    cand = txt[s:e + 1] if (s >= 0 and e > s) else "[" + txt + "]"
    try:
        arr = json.loads(cand)
        if isinstance(arr, dict):
            arr = [arr]
        tmp = []
        for o in arr:
            if isinstance(o, dict):
                tmp.append((int(o.get("i", len(tmp))), str(o.get("t", "")).strip()))
            elif isinstance(o, str):
                tmp.append((len(tmp), o.strip()))
        if tmp:
            return tmp
    except Exception:                                   # noqa: BLE001
        pass

    # 3) 裸行兜底：条数刚好对得上就按顺序吃
    lines = [ln.strip().strip('"') for ln in txt.splitlines()
             if ln.strip() and not ln.strip().startswith(("```", "#", "以下", "好的"))]
    if len(lines) == len(items):
        return [(it["i"], ln) for it, ln in zip(items, lines)]
    return []
