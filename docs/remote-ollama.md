# 把翻译放到另一台机器上跑（家里有显卡的台式机 / 服务器）

ASR（语音识别）在你的主力机上跑就行，CPU 也能有 5–7 倍实时速度。
**翻译**这一步可以甩给局域网里带 NVIDIA 显卡的机器，快很多。

## 在那台机器上

```bash
# 1) 装 Ollama 并拉一个模型
ollama pull qwen3:8b

# 2) 让它监听局域网（默认只听 127.0.0.1）
#    Linux:   Environment=OLLAMA_HOST=0.0.0.0:11434
#    Windows: 设置环境变量 OLLAMA_HOST=0.0.0.0
#    macOS:   launchctl setenv OLLAMA_HOST 0.0.0.0

# 3) 确认能通（在主力机上执行）
curl http://<那台机器的内网IP>:11434/api/tags
```

> 只在可信网络（家庭/公司内网，或 WireGuard/Tailscale 组网）里开放，
> 别直接暴露到公网。

## 在你的主力机上

```bash
# 一次性
vsub 视频.mp4 --base-url http://<那台机器的内网IP>:11434

# 或者写进配置，以后不用每次敲
vsub config init
#   改 [translate] 里的 base_url = "http://<那台机器的内网IP>:11434"

vsub config check      # 发一句话验证连通
```

## 性能参考（RTX 4060 8GB + qwen3:8b）

| 项目 | 数值 |
|---|---|
| 生成速度 | 约 46 tok/s |
| 一批 25 条字幕 | 6–12 秒 |
| **并发 `--jobs`** | **必须设为 1**：8GB 显存同时装两份 5.2GB 模型会 OOM |

## 显卡上跑 ASR（可选）

如果你想连识别也放到显卡上：

```bash
pip install -e ".[cuda]"
vsub 视频.mp4 --device cuda --compute float16 --asr-model large-v3
```

Windows 上 ctranslate2 需要手动加载 pip 装的 CUDA 动态库，`vsub` 已经自动处理
（见 `vsub/asr.py: prepare_cuda()`）。
