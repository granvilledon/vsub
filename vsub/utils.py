"""日志、进度条等通用工具。"""

import subprocess
import sys
import time

BAR_W = 24
_step_seen = {}          # 非交互输出（管道/日志）时按 10% 粒度打点，避免刷屏


def setup_stdio():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _fmt_eta(sec):
    if sec is None or sec < 0:
        return ""
    if sec < 60:
        return f" 剩余 {sec:.0f} 秒"
    if sec < 3600:
        return f" 剩余 {sec / 60:.1f} 分"
    return f" 剩余 {sec / 3600:.1f} 小时"


def progress(done, total, prefix="", suffix="", t0=None):
    """单行刷新进度条。非 tty（重定向到日志/tail）时自动降级为每 10% 一行"""
    if not total or total <= 0:
        return
    pct = min(1.0, max(0.0, done / total))
    filled = int(pct * BAR_W)
    bar = "#" * filled + "-" * (BAR_W - filled)
    eta = ""
    if t0 is not None and done > 0:
        elapsed = time.time() - t0
        eta = _fmt_eta(elapsed * (total - done) / done)
    line = f"{prefix} [{bar}] {pct * 100:5.1f}%  {done:.1f}/{total:.1f}{suffix}{eta}"

    if sys.stdout.isatty():
        sys.stdout.write("\r" + line)
        sys.stdout.flush()
        if done >= total:
            sys.stdout.write("\n")
            sys.stdout.flush()
    else:
        key = prefix or "_"
        step = int(pct * 10)
        if _step_seen.get(key) != step or done >= total:
            _step_seen[key] = step
            log(line)


def check_tool(name):
    """检查 ffmpeg/ffprobe 是否可用"""
    from shutil import which
    return which(name) is not None


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)
