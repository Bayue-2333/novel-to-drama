# novel-to-drama

让 Codex 将小说制作成 AI 短剧的总控技能，结合 [OpenMontage](https://github.com/calesthio/OpenMontage)、[shuohao-skills](https://github.com/eternityspring/shuohao-skills)、内置 imagegen 与本地 ComfyUI / MiniMax H3。

```text
小说 → 改编大纲与剧本 → 人物三视图、场景和道具资产
     → 分镜关键帧与运镜提示词 → 本地 H3 视频生成
     → 剪辑 → 音画/口型同步 → 字幕校对与合成
     → 镜间和跨集纠错 → 最终全片检查
```

这是给 Codex 读取的生产编排技能。Python 脚本辅助检查环境、绑定工作流参数和验证交付文件，创作与视听判断由 Codex 执行。

## 功能

- 复用 shuohao 的大纲、角色、美术、剧本、分镜五个技能及原生 JSON 校验。
- 使用 Codex 内置 imagegen 为每个出镜人物生成正面、侧面、背面全身图，锁定角色与服装状态。
- 写出镜头的起始构图、主体动作、运镜、结束状态与接镜约束，并将实际参考图绑定到 H3 工作流。
- 通过 OpenMontage 和本地 ComfyUI 生成视频，保存任务 ID、参数与素材来源，支持中断恢复和局部重做。
- 核对逐句对白、说话人、可见口型、音效时点和剪辑后的累计漂移。
- 校对 SRT / ASS，合成带字幕成片，同时保留干净母版。
- 检查人物、道具、空间、动作、声音与剧情连贯性，最终报告绑定当前文件哈希。

## 前置条件

| 组件 | 用途 |
|---|---|
| 可调用内置 imagegen 的 Codex | 创作、人物与分镜出图、工具调度 |
| [shuohao-skills](https://github.com/eternityspring/shuohao-skills) 的五个 novel 技能 | 前期制作与文档校验 |
| [OpenMontage](https://github.com/calesthio/OpenMontage) | 视频生成接入、剪辑、混音、合成与审查 |
| 本地 ComfyUI、H3 模型栈及 API 格式工作流 | 实际视频推理 |
| Python 3.10+、Node.js 18+、FFmpeg / ffprobe | 辅助脚本与媒体处理 |

本仓库不包含依赖仓库、模型、API 密钥或示例小说。运行前以本机注册表与 `/object_info` 核对真实能力；OpenMontage 必须具备所需的自定义 ComfyUI / H3 接口。旧版缺少字段时先处理兼容性，不能假装存在。

## 安装

先按各上游说明安装依赖技能与本地视频环境，然后将本仓库放入 Codex 的技能目录。

PowerShell：

```powershell
$codexDir = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
$skillsDir = Join-Path $codexDir 'skills'
New-Item -ItemType Directory -Path $skillsDir -Force | Out-Null
git clone https://github.com/Bayue-2333/novel-to-drama.git (Join-Path $skillsDir 'novel-to-drama')
```

macOS / Linux：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
git clone https://github.com/Bayue-2333/novel-to-drama.git "${CODEX_HOME:-$HOME/.codex}/skills/novel-to-drama"
```

目标目录已存在时，先检查现有版本，勿直接覆盖。私有仓库需要对应 GitHub 访问权限。

## 使用

```text
用 $novel-to-drama 把这部小说做成 AI 短剧。
小说文件：填写本地路径。
集数与单集时长：填写目标。
画风与画幅：例如写实、9:16。
用内置 imagegen 生成每个人物三视图，用本地 ComfyUI + MiniMax H3 生成视频，
完成剪辑、音画同步、字幕合成、连贯性纠错及最终全片检查。
```

也可以要求只做前期、只检查环境，或从已有项目继续。正式生产需要小说与明确的制作范围；创建/安装技能本身不会启动生成任务。

默认交付：各集干净母版、烧录字幕版、SRT、ASS、剧本/角色/分镜资料、生成清单、剪辑工程或 EDL、修复记录和最终检查报告。

## 验证

在仓库目录运行标准库测试，不调用模型、不消耗生成额度：

```bash
python -B scripts/selftest.py
```

可选 FFmpeg 集成测试，会在 `work/` 中生成短测试素材、实际烧录 ASS 并验证解码、字幕和审查记录失效机制：

```bash
python -B scripts/selftest.py --ffmpeg /path/to/ffmpeg --ffprobe /path/to/ffprobe
```

只读 ComfyUI 预检：

```bash
python -B scripts/preflight.py --url http://127.0.0.1:8188 --out work/preflight
```

创建版本已通过 16 项单元测试和合成媒体集成测试。尚未以真实小说完成 H3 端到端成片验证；首次制作时先生成并检查代表性样片。

**检查边界：**脚本能检查媒体、字幕与审查记录的结构，不能自动证明人物一致、剧情连贯或嘴型正确。稀疏抽帧、文件可播放或 ASR 结果不等于全片视听检查；未覆盖内容必须标记为 partial。工作流导出图与参考图的真实连接，也不能仅靠提示词声称完成。

## 文件入口

- [SKILL.md](SKILL.md)：Codex 总控入口。
- [前期与运镜](references/preproduction.md)：人物三视图和连续性设计。
- [ComfyUI / H3 接线](references/comfyui-h3.md)：API 工作流、参数绑定与任务恢复。
- [剪辑与全检](references/edit-and-review.md)：声音、口型、字幕、纠错和检查证据。
- [项目与交付契约](references/project-contract.md)：断点状态、哈希失效与终检格式。
- [环境与来源](references/environment-and-sources.md)：依赖发现与上游链接。

## 上游与鸣谢

本仓库新增编排说明和辅助检查脚本，依赖 OpenMontage 与 shuohao-skills 的现有安装，没有捆绑或复制它们的运行时。上游软件、模型和第三方素材分别遵循各自许可证与使用条款。
