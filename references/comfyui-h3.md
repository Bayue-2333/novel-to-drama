# ComfyUI 与 H3 的实际接线

## 预检与路线

本技能使用用户选择的本地 ComfyUI / H3。运行 `scripts/preflight.py --out <目录>`，它仅 GET `/system_stats` 和 `/object_info`，保存节点快照，不排队、不加载模型。输出的 `h3_nodes_present` 只证明节点存在；模型文件、图连接、显存和生成效果仍须验证。

读取 OpenMontage 的 `.agents/skills/comfyui/SKILL.md`、`.agents/skills/minimax-h3/SKILL.md`，以及实际 `tools/video/comfyui_video.py` 的 schema。工具版本可能变化，当前环境优先。

- 本地生成：`comfyui_video` + `model_family: minimax_h3_local` + API JSON + `output_node`。
- `minimax_h3_api` 和 `MinimaxHailuo03...` Partner Nodes 是托管调用。检查图里每个节点的 `api_node`、模块和用途；仅把外层 model_family 写成本地不能保证图中没有云端节点。
- 默认 WAN 工作流缺模型不能作为 H3 缺模型的结论。不偷偷改用 WAN、其他供应商或静态推拉图片。
- 不因准备技能而下载巨大模型或运行视频。实际生产时先检查当前队列，不中断其他用户的 GPU 任务。

## UI JSON 与 API JSON

API JSON 是 `{node_id: {class_type, inputs}}` 图；编辑器的 `nodes`/`links`/`widgets_values` 布局不是这个格式。优先从现有 ComfyUI 导出 API 格式。UI 子图、bypass、动态控件不能靠把 widgets_values 按顺序硬填得到可靠图；无把握就通过当前前端导出，不提交猜测图。

逐项核对：

1. `/object_info` 中存在所有 class_type；Loader 的模型选项确实含图中模型；H3 的扩散模型、文本编码器、视频 VAE、音频 VAE 对应当前官方/用户工作流。
2. API 图的连接指向真实节点/输出槽，所有必需字段齐全，无环，终点是保存最终带音视频的节点 ID。
3. 选择真实 H3 生成路径，并确认它在保存节点的祖先依赖中；仅图中孤立放一个 H3 节点没有意义。
4. 核对 fps、长度和分辨率节点，保留工作流要求的步长/网格。不要套 WAN 的 16fps 或 `81` 帧默认。生成前读节点说明，生成后用 ffprobe 实测。
5. 如果 H3 是音视频联合生成，确保音频潜变量解码并接到最终视频创建/保存路径；单有音频 VAE 文件不代表已输出音轨。

## 必须将参数写进图

本机核对的 OpenMontage 实现对自定义工作流只做加载；外层 `prompt`、`seed`、`width` 等不会自动注入节点，`reference_image_path` 也不会自动上传和接图。外层的默认 fps/duration 元信息还可能沿用 WAN，不能当测量值。

对每段复制一份 API 模板，识别并记录这些实际字段：正向提示词、负向提示词（如存在）、噪声种子、帧数、宽高/分辨率选择器、参考图加载名、参考音频、时间锚点、保存文件前缀。模型 Loader 与网络连接保持不变，除非本次确需修正并已校验。

`scripts/bind_workflow.py` 用显式绑定表替换已有的字面量输入。它要求写出旧值 `expected`，图有变化时停止，避免写错节点。节点 ID 必须从这次导出的图读取，下面只是格式示例：

```json
{
  "output_node": "实际保存节点ID",
  "bindings": [
    {"node": "实际提示词节点ID", "input": "prompt", "expected": "模板旧文", "value": "本段完整提示词"},
    {"node": "实际种子节点ID", "input": "noise_seed", "expected": 1, "value": 1729},
    {"node": "实际LoadImage节点ID", "input": "image", "expected": "旧图.png", "value": "上传后服务端名称.png"}
  ]
}
```

```text
python scripts/bind_workflow.py --workflow template.api.json --bindings segment.bindings.json --object-info preflight/object_info.json --out segment.api.json
```

该脚本不负责导出 UI 子图、不上传图片、不生成视频、不证明任意第三方节点都离线。它拦截声明为 API/Partner 的节点，做基本字段、模型选项与连接检查；更复杂的 V3 动态字段仍依赖 ComfyUI 服务端最终校验。已连接的输入应沿线找到上游字面量再绑定，不能强行断开连接。

上传图片通过真实 ComfyUI client 的 `upload_image` 或 `/upload/image`；使用返回的服务端名称/子目录填 `LoadImage`，不能把 Windows 绝对路径当远端文件名。创建版本化输入名称，避免覆盖别的任务。上传后刷新 `/object_info` 快照，使 LoadImage 的文件选项包含新图，再运行绑定校验。多图逐张上传，并把顺序、时间锚、角色版本写进 `generation_map.json`。

## OpenMontage 执行

通过注册表 `discover()`、`get('comfyui_video')` 得到实际工具，读取 get_info 后使用其当前 execute 合同。不把内部类名当公开 CLI。Windows 用现有 `openmontage/run.ps1` 调隔离 Python；外部 JSON 参数写文件后读取，不插进 shell 字符串。概念参数：

```json
{
  "prompt": "与已绑定图中相同的本段提示词",
  "model_family": "minimax_h3_local",
  "operation": "image_to_video",
  "workflow_path": "本段已绑定API文件的绝对路径",
  "output_node": "实际最终保存节点ID",
  "workflow_model": "实际模型版本与量化标签",
  "workflow_model_stack": [],
  "output_path": "项目内版本化视频绝对路径",
  "timeout_seconds": 3600
}
```

工作流决定 I2V/R2V 的真实行为；schema 未列 R2V enum 时不凭空写 `operation: reference_to_video`。用支持的值传入自定义图，并额外记录图的真实生成模式。

每次排队马上记录 `prompt_id`（可从当前 client、事件或返回错误取得）、提交时间与输入哈希。长任务以宿主可恢复会话运行，定期回报实际进度；不把一个长阻塞轮询当作 agent 消失的理由。超时用同一 ID 恢复等待，只有确认已失败/已取消才创建新任务。不能用 `/interrupt` 杀掉无关任务。

## OpenMontage 状态与项目目录

使用 `cinematic` 的阶段职责与 canonical artifact schema；五份 shuohao 文档是创作真相，映射到 research/proposal/script/scene_plan/assets/edit/compose，并在映射表保留源 ID。不要直接将 shuohao script.json 传入 OpenMontage 的异构 schema。

调用 checkpoint 时核对当前函数签名。本机 `init_project(project_id, title=..., pipeline_type='cinematic', pipeline_dir=Path(...))` 支持工作区内的外部项目父目录；其余 checkpoint 操作传同一目录，所有输出用绝对路径。不要写回全局 runtime/projects。Backlot 对外部目录未配置时可能不显示，不能以 UI 未显示推断文件丢失。

流水线的预算、阶段默认审批和画风习惯结合真实用户授权使用。已授权全流程就记录该授权覆盖的选择；不能虚构 `human_approved` 或改全局规则绕过门。已有用户选择优先于上游建议，不为了预告片模板删对白，不为了“发布”阶段自动上传成片。
