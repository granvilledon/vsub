"""不涉及模型/网络的单元测试。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vsub.srt import regroup, srt_time, write_srt  # noqa: E402
from vsub.translators import get_translator, normalize  # noqa: E402
from vsub.translators.base import fix_ids, parse_translation  # noqa: E402


def test_srt_time():
    assert srt_time(0) == "00:00:00,000"
    assert srt_time(3661.5) == "01:01:01,500"
    assert srt_time(-5) == "00:00:00,000"
    assert srt_time(None) == "00:00:00,000"


def test_srt_time_carries_instead_of_overflowing():
    """毫秒进位必须继续往分、时走，否则会产出 00:00:60,000 这种非法时间戳。"""
    assert srt_time(59.9996) == "00:01:00,000"
    assert srt_time(3599.9996) == "01:00:00,000"
    assert srt_time(59.999) == "00:00:59,999"


def test_write_srt_translation_on_top(tmp_path):
    segs = [{"start": 0, "end": 1, "text": "Hello", "tgt": "你好"}]
    p = tmp_path / "a.srt"
    write_srt(segs, p, "bilingual")
    body = p.read_text(encoding="utf-8")
    assert "你好" in body and "Hello" in body
    lines = [ln for ln in body.splitlines() if ln.strip()]
    assert lines.index("你好") < lines.index("Hello")     # 译文在上

    write_srt(segs, p, "bilingual", tgt_first=False)
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines.index("Hello") < lines.index("你好")     # 原文在上


def test_write_srt_single_mode(tmp_path):
    segs = [{"start": 0, "end": 1, "text": "Hello", "tgt": "你好"}]
    p = tmp_path / "b.srt"
    write_srt(segs, p, "tgt")
    assert "你好" in p.read_text(encoding="utf-8")
    assert "Hello" not in p.read_text(encoding="utf-8")


def test_regroup_merges_tiny_fragments():
    raw = [{
        "start": 0.0, "end": 2.0, "text": "这是一个测试方法",
        "words": [{"s": 0.0, "e": 0.5, "w": "这是一个"},
                  {"s": 0.6, "e": 1.0, "w": "测试方法"}],
    }]
    out = regroup(raw)
    assert len(out) == 1
    assert out[0]["end"] >= out[0]["start"]


def test_parse_line_protocol():
    items = [{"i": 0, "t": "a"}, {"i": 1, "t": "b"}]
    got = parse_translation("0|||甲\n1|||乙", items)
    assert got == [(0, "甲"), (1, "乙")]


def test_parse_json_fallback():
    items = [{"i": 0, "t": "a"}, {"i": 1, "t": "b"}]
    got = parse_translation('[{"i":0,"t":"甲"},{"i":1,"t":"乙"}]', items)
    assert got == [(0, "甲"), (1, "乙")]


def test_parse_bare_lines():
    items = [{"i": 0, "t": "a"}, {"i": 1, "t": "b"}]
    got = parse_translation("甲\n乙", items)
    assert got == [(0, "甲"), (1, "乙")]


def test_fix_ids_realigns():
    items = [{"i": 3, "t": "a"}, {"i": 4, "t": "b"}]
    # 模型把编号写成了 3,3 —— 条数一致但集合对不上，应按顺序重排
    assert fix_ids([(3, "甲"), (3, "乙")], items) == [(3, "甲"), (4, "乙")]
    # 集合一致时不动
    assert fix_ids([(3, "甲"), (4, "乙")], items) == [(3, "甲"), (4, "乙")]


def test_provider_registry():
    assert normalize("deepseek") == "openai"
    assert normalize("google") == "gemini"
    t = get_translator("ollama")
    assert t.base_url == "http://127.0.0.1:11434"      # 默认本机，不写死内网地址
    t2 = get_translator("openai", base_url="https://example.invalid/v1", api_key="k")
    assert t2.base_url == "https://example.invalid/v1"
    assert t2.api_key == "k"


def test_unknown_provider_exits():
    import pytest
    with pytest.raises(SystemExit):
        get_translator("nonexistent-provider")


def test_config_warns_when_toml_parser_missing(tmp_path, monkeypatch, capsys):
    """3.10 及以下没有 tomllib 时，配置文件不能静默失效 —— 必须告警。"""
    from vsub import config

    p = tmp_path / "config.toml"
    p.write_text('[translate]\nprovider = "deepl"\n', encoding="utf-8")
    monkeypatch.setattr(config, "tomllib", None)

    cfg = config.load(p)
    out = capsys.readouterr().out
    assert cfg["translate"]["provider"] == "ollama"     # 降级到默认值
    assert "TOML" in out                                 # 但不能一声不吭
