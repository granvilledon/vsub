"""语言代码 / 名称映射。"""

# Whisper 语言代码 -> 中文名（用于日志与字幕轨标题）
LANG_NAME = {
    "zh": "简体中文", "zh-cn": "简体中文", "en": "英语", "ja": "日语",
    "ko": "韩语", "fr": "法语", "de": "德语", "es": "西班牙语",
    "ru": "俄语", "pt": "葡萄牙语", "it": "意大利语", "ar": "阿拉伯语",
    "th": "泰语", "vi": "越南语", "yue": "粤语",
}

# MKV 字幕轨元数据要 ISO 639-2 三字母码
LANG_ISO3 = {
    "zh": "chi", "zh-cn": "chi", "en": "eng", "ja": "jpn", "ko": "kor",
    "fr": "fre", "de": "ger", "es": "spa", "ru": "rus", "pt": "por",
    "it": "ita", "ar": "ara", "th": "tha", "vi": "vie", "yue": "chi",
}

# DeepL 用大写语言码，且部分目标语言需要变体后缀
DEEPL_LANG = {
    "zh": "ZH", "en": "EN", "en-us": "EN-US", "en-gb": "EN-GB",
    "ja": "JA", "ko": "KO", "fr": "FR", "de": "DE", "es": "ES",
    "ru": "RU", "pt": "PT", "it": "IT", "ar": "AR",
    "nl": "NL", "pl": "PL", "sv": "SV", "tr": "TR", "id": "ID",
    "uk": "UK", "cs": "CS", "da": "DA", "fi": "FI", "el": "EL",
    "no": "NB", "ro": "RO", "hu": "HU",
}


def lang_name(code):
    return LANG_NAME.get((code or "").lower(), code or "")


def iso3(code):
    return LANG_ISO3.get((code or "").lower().split("-")[0], "und")
