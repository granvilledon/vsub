# 翻译后端配置对照表

所有云 API 都走 **OpenAI 兼容协议**（`--provider openai`），换服务商只需要改
`--base-url` 和 `--model` 两个值。

```bash
export VSUB_API_KEY=你的key
vsub 视频.mp4 --provider openai \
  --base-url https://api.deepseek.com/v1 \
  --model deepseek-chat
```

先验证再正式跑：`vsub config check --provider openai --base-url ... --model ...`

## OpenAI 兼容（`--provider openai`）

| 服务商 | `--base-url` | `--model` 示例 |
|---|---|---|
| OpenAI | `https://api.openai.com/v1`（默认） | `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 月之暗面 Kimi | `https://api.moonshot.cn/v1` | `moonshot-v1-8k` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 硅基流动 SiliconFlow | `https://api.siliconflow.cn/v1` | `Qwen/Qwen2.5-7B-Instruct` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| 本地 vLLM | `http://localhost:8000/v1` | 你部署的模型名 |
| LM Studio | `http://localhost:1234/v1` | 本地模型名 |
| Ollama（走 /v1） | `http://localhost:11434/v1` | `qwen3:8b` |

> 阿里云百炼、字节火山方舟、腾讯混元等也都提供 OpenAI 兼容端点，
> 照着各自文档填 base_url 即可，代码不用改。

## Ollama（`--provider ollama`，默认，免费）

```bash
ollama pull qwen3:8b
vsub 视频.mp4
```

| 场景 | `--base-url` |
|---|---|
| 本机 | `http://127.0.0.1:11434`（默认） |
| 局域网另一台机器 | `http://<那台机器的内网IP>:11434` |
| 非默认端口 | 按实际改 |

翻译质量优先选 `qwen3:8b` / `qwen2.5:7b`；显存紧张用 `qwen3.5:4b`。

## DeepL（`--provider deepl`）

```bash
export VSUB_API_KEY=你的DeepL key
vsub 视频.mp4 --provider deepl
```

| 账号类型 | `--base-url` |
|---|---|
| Free | `https://api-free.deepl.com/v2`（默认） |
| Pro | `https://api.deepl.com/v2` |

DeepL 是纯翻译 API，不走大模型 prompt，所以**不支持术语表和语气控制**，
但速度快、术语一致性好。

## Gemini（`--provider gemini`）

```bash
export VSUB_API_KEY=你的Google AI Studio key
vsub 视频.mp4 --provider gemini --model gemini-2.0-flash
```

默认 `--base-url https://generativelanguage.googleapis.com/v1beta`。

## 并发与速度

| 后端 | `--jobs` 建议 | 说明 |
|---|---|---|
| 本地 Ollama（≤8GB 显存） | **1** | 并发 2 会同时加载两份模型，直接爆显存 |
| 云 API | 2–4 | 注意各家 RPM 限流 |

## 换后端不用改配置文件的办法

```bash
# 一次性覆盖
vsub 视频.mp4 --provider openai --base-url https://api.deepseek.com/v1 --model deepseek-chat

# 或者写进配置文件的 [translate] 段，之后就不用每次敲了
vsub config init
```
