# 环境发现与来源

## 查找本地安装

用户指定目录和当前会话的技能列表优先。否则，Codex 技能根目录取 `$CODEX_HOME/skills`；未配置时取 `~/.codex/skills`。

| 组件 | 查找位置 |
|---|---|
| imagegen | 当前会话技能路径；常见为技能根目录下 `.system/imagegen/SKILL.md` |
| shuohao 前期技能 | 技能根目录下 `novel-outline`、`novel-characters`、`novel-art`、`novel-script`、`novel-storyboard` |
| OpenMontage | 用户安装路径；本地入口封装可能将仓库存于 `openmontage/runtime/` |
| Windows Python 环境入口 | 现有 `openmontage/run.ps1`，如该封装确实已安装 |
| ComfyUI | 用户指定安装位置和服务器地址 |
| 默认服务地址 | `http://127.0.0.1:8188`，运行时重检 |
| H3 工作流 | 用户的 ComfyUI 工作流目录或官方模板；生成前导出为 API 格式 |

路径只用于发现，不应要求别人使用创建者的用户名、磁盘路径或本地 checkout。未安装 Windows 入口封装时，直接使用用户的 OpenMontage 环境，先读其启动和依赖说明。

## 环境预检

Python 辅助脚本只用标准库。FFmpeg/ffprobe 不在 PATH 时，preflight 会尝试 OpenMontage `.tools` 目录；其他安装方式可直接指定工具绝对路径。

```text
python -B scripts/preflight.py --url http://127.0.0.1:8188 --out work/preflight
```

节点存在不等于模型文件、显存或工作流可用。读取 `/system_stats`、`/object_info` 和所选工作流，先核对 Loader 文件和音视频输出路径，再用已授权的样片验证真实效果。不要输出 `.env` 内容或将本机健康报告提交到公共仓库。

OpenMontage 注册表检查，在其正确 Python 环境及工作目录执行：

```python
from tools.tool_registry import registry
import json
registry.discover()
print(json.dumps(registry.provider_menu_summary(), ensure_ascii=False, indent=2))
```

以实际版本的 schema 为准。此技能开发时核对过本地自定义工作流接入的行为，但不承诺所有历史版本都包含 `minimax_h3_local`、`resume_prompt_id` 等字段。接口变化后重读对应源码，调整接线并重新测试。

运行 Node 校验脚本时把 cwd 放在当前作品的工作区，确保日志也留在作品目录。用参数数组或 JSON 文件传提示词，避免 shell 解释反引号、引号或美元符号。作品不要写进全局技能目录。

## 来源

核对日期：2026-09-09。以下链接用于运行时追查当前定义，本仓库不包含依赖的源码、模型或凭据。

- [OpenMontage](https://github.com/calesthio/OpenMontage)：工具注册表、阶段产物、视频接入、剪辑、混音、合成和审查。重点读取所选 pipeline 与 `tools/video/comfyui_video.py`。
- [shuohao-skills](https://github.com/eternityspring/shuohao-skills)：小说改编、角色、美术、剧本、分镜及各自确定性校验。
- [ComfyUI MiniMax H3 官方指南](https://docs.comfy.org/tutorials/video/minimax/minimax-h3)：本地权重路线、音视频生成、I2V/R2V 与多帧参考。
- 当前 Codex `imagegen` SKILL 和工具签名：内置生成优先，按实际工具参数传参考图，并将项目资产保存到作品目录。

若作品用于商业发布，结合实际用途核对相关模型与素材的使用条款。发布技能代码本身不包含对作品、原著或模型的授权。
