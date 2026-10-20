# vsub —— 给视频加字幕并翻译

[English](README.en.md) · 中文文档 · [翻译后端配置](docs/providers.md) · [隐私说明](docs/privacy.md)

本地识别语音（faster-whisper）+ 任意翻译后端（Ollama / OpenAI 兼容 / DeepL / Gemini），
给视频生成字幕并翻译。**默认只输出外挂 `.srt`，原视频一个字节都不动。**

```
视频 -> ffmpeg 抽音 -> faster-whisper 转写 -> 翻译后端 -> 字幕（视频旁边）
                                                    └─> 可选：内挂软字幕 mkv（--embed）
```

## 特性

- **原视频零改动**：默认外挂 srt（与视频同名，播放器自动加载）；`--embed` 出内挂软字幕 mkv，用 `-c copy` 流拷贝，**无损且可逆**
- **不做硬烧录**：烧录要重新编码，画质有损、字幕关不掉、不可逆。传 `--burn` 只会打印提示并退出
- **自动识别语言**：不用指定源语言；中日韩这类无空格语言会自动收窄断句
- **翻译后端可插拔**：本地 Ollama 免费跑，也能一行切换到 DeepSeek / 通义 / OpenAI / DeepL / Gemini
- **双语字幕默认译文在上、原文在下**（`--src-first` 可反过来）
- **批量 + 断点续跑**：传文件夹即可，已处理过的自动跳过；ASR 模型只加载一次
- **隐私**：音频和视频不出本机，只有字幕文本会发给翻译后端

## 安装

```bash
# 需要 ffmpeg / ffprobe 在 PATH 里

# 从源码安装（当前可用）
git clone https://github.com/granvilledon/vsub.git && cd vsub
pip install -e .
```

PyPI 包名是 **`vsub-cli`**（命令行仍然是 `vsub`），发布后可以：

```bash
pipx install vsub-cli      # 推荐
# 或
pip install -U vsub-cli
```

> ⚠️ PyPI 上的 `vsub` 是一个**同名但无关**的 C 库封装（作者 Michael Makukha），不是本项目，别装错。

## 30 秒上手

```bash
# 1) 用本地 Ollama（免费，不需要 key）—— 需先装 Ollama 并拉模型
ollama pull qwen3:8b
vsub 视频.mp4

# 2) 用云 API
export VSUB_API_KEY=sk-xxxxxx
vsub 视频.mp4 --provider openai --base-url https://api.deepseek.com/v1 --model deepseek-chat
```

产物：

```
视频.mp4
视频.srt        ← 双语（译文在上/原文在下），播放器自动加载
视频.zh.srt     ← 纯中文
视频.orig.srt   ← 原文
```

> 跑完自动清理中间产物（尤其是能还原人声的 `wav`）。
> 要保留以便换语言重翻，加 `--keep-temp`。

## 配置

配置优先级：**命令行 > 环境变量 > 配置文件 > 默认值**

```bash
vsub config init      # 生成 ~/.vsub/config.toml（带注释的模板）
vsub config show      # 查看当前生效配置（key 打码）
vsub config check     # 发一句话试翻，验证连通与鉴权
vsub config path      # 打印配置文件路径
```

```toml
[translate]
provider = "ollama"        # ollama / openai / deepl / gemini
model = "qwen3:8b"
# base_url = "https://api.deepseek.com/v1"
api_key_env = "VSUB_API_KEY"   # key 放环境变量，不要写进文件

[asr]
model = "small"            # tiny/base/small/medium/large-v3
device = "cpu"             # 有 NVIDIA 卡改 cuda

[output]
mode = "bilingual"
```

环境变量：`VSUB_PROVIDER` `VSUB_MODEL` `VSUB_BASE_URL` `VSUB_API_KEY` `VSUB_TGT`
`VSUB_ASR_MODEL` `VSUB_DEVICE` `VSUB_MODE` `VSUB_CONFIG`

> **故意不提供 `--api-key` 命令行参数**——它会留在 shell history 里。

各家的 `base_url` / 模型名对照见 **[docs/providers.md](docs/providers.md)**。

## 常用参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--provider` | `ollama` | 翻译后端：`ollama` / `openai` / `deepl` / `gemini` |
| `--base-url` | 后端默认 | 换服务商只改这个 |
| `--model` | 后端默认 | 翻译模型名 |
| `--tgt` | `zh` | 目标语言 |
| `--src` | 自动识别 | 源语言 |
| `--asr-model` | `small` | ASR 模型，也可填本地模型目录 |
| `--mode` | `bilingual` | `bilingual`（译文在上）/ `tgt` / `src` |
| `--src-first` | 关 | 双语改成原文在上 |
| `--embed` | 关 | 额外输出可开关的软字幕 mkv（无损） |
| `--use-outdir` | 关 | 字幕收进 `output/` 子目录 |
| `--keep-temp` | 关 | 保留 `wav`/`segs.json` 等中间产物 |
| `--force` | 关 | 已有字幕也重做（默认跳过，用于断点续跑） |
| `--recursive` | 关 | 连子文件夹一起扫 |
| `--batch` / `--jobs` | `25` / `1` | 每批条数 / 并发（本地小显存保持 1） |
| `--glossary` | 无 | 术语表 JSON：`{"Docker":"Docker"}` |
| `--burn` | **不支持** | 有损且不可逆，传了只打印说明 |

传文件夹即批量：`vsub D:\我的视频 --recursive`

## 字幕三种形态

| 形态 | 命令 | 动原视频？ | 能关掉吗 | 画质 |
|---|---|---|---|---|
| **外挂 srt**（默认） | `vsub in.mp4` | **碰都不碰** | ✅ | 无损 |
| **内挂 mkv** | `--embed` | 生成新文件，原片不动 | ✅ 可切轨 | 无损（`-c copy`） |
| 硬烧录 | — | — | ❌ | **有损**，不做 |

内挂可逆验证（流哈希一致）：

```bash
ffmpeg -i x.mp4 -map 0:v -c copy -f md5 -     # 原片与内挂后完全相同
ffmpeg -i x.soft.mkv -map 0:v -map 0:a -c copy 还原.mp4
```

## 隐私

- 视频/音频**不出本机**，发给翻译后端的只有字幕文本（每批 ≤25 条、≤1100 字符）
- 中间产物（`wav` 能还原全部人声、`segs.json` 是原文译文明文）**默认跑完删除**
- 用云 API 时字幕文本会经过第三方；敏感内容建议用本地 Ollama
- 详见 [docs/privacy.md](docs/privacy.md)

## 开发

```bash
pip install -e ".[dev]"
pytest -q                     # 单元测试（不需要模型）
ruff check .
python scripts/preflight.py   # 发布前扫描敏感信息
```

## 许可

MIT。核心依赖 faster-whisper 同为 MIT。
