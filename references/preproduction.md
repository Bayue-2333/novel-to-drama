# 前期、角色与可执行运镜

## shuohao 接力

按各技能现有 schema/seed/assemble/validate/render 使用，不重新发明五份文档格式。角色 ID 从大纲继承到 cast、script、storyboard；同一人物的别名归并，不能把同姓的不同人物合并。所有在成片出现的明确人物都应在资产清单中，缺图统计按剧本实际角色对账。

保持 `storyboard/manifest.json`、报告、`E01-01/` 等投产目录同级，避免移动目录导致图像相对链接失效。H3 的段号与 cut 索引沿用上游，额外的实际生成单元通过旁路表 `generation_map.json` 关联；一段拆成多个任务时记录各自覆盖的 cut，不能改变台词顺序或重复节拍。

原生脚本入口都在 `{skills}/novel-*/scripts/novel-*.mjs`。查看对应 SKILL 和 `--help` 后使用，特别是 storyboard 的 `validate` 必须提供 `--script`。上游时长折算是预算，获得真实音频后按音频实测重排，不能为了通过时长门加速人物对白到不自然。

## 角色三视图模板

先读取用户参考与角色 image 字段，保留已确定的画风。模板中的花括号由角色卡实值替换：

```text
Use case: stylized-concept (or photorealistic-natural, matching the chosen style)
Asset type: production character turnaround reference sheet
One and the same person in all views: {age range, face structure, eye shape,
hair silhouette, body build, height proportions, distinctive features}.
Show full-body FRONT, strict SIDE PROFILE, and BACK views in three equally sized
columns, neutral standing pose, consistent scale and baseline, head and feet fully
visible. All views wear exactly {costume state, fabric, colors, shoes, accessories}.
Keep face identity, anatomy and hairstyle consistent across views. Preserve
anatomical left/right: {e.g. character's left ear only; not screen-left}.
Neutral plain background, soft even studio light, minimal perspective distortion.
Optional separate face portrait if it does not shrink or crop the three body views.
No extra people, duplicate limbs, weapons or accessories absent from the design.
```

参考图中的多视角是同一人的设计资料，不是场景中有三个人。后续生成单镜关键帧时明确说明这一点。可以用 imagegen 以已验收整表为参考生成单人构图，不能通过三次无参考独立出图拼出三张不同的脸。普通文件复制可用脚本；图像内容修改仍走 imagegen，除非用户明确选择其他编辑方法。

角色一致性卡保留：`character_id`、面貌锚点、身体比例、发型轮廓、服装状态 ID、饰物所在解剖侧、人物声线与年龄状态。每次改稿输出新版本，标记旧资产被替换，重生成相关镜头。

## 场景空间与连续性

为每个场景建立简单平面关系：门窗/桌椅/光源固定位置，人物相对位置，摄影机所在轴线侧，进出路径。旁路 `continuity.json` 按每切记录：

- `start_state` / `end_state`：角色位置、身体朝向、视线对象、持物左右手、服装/伤痕、道具开合/损坏状态、时间/天气。
- `camera_side`、`screen_direction`、`eyeline_target`、`transition_reason`。
- 接镜约束：上一镜伸出的手、移动方向和持物必须接到下一镜；翻轴需用可见的跨轴运动或交代空间的中性镜。

用镜头服务戏剧信息，避免每镜都推拉摇移。对话优先清楚建立人物关系；复杂多人交互拆为可验证的小动作、反应与插入镜头。不得为了降低生成难度默默删除关键剧情。

## 运镜文本模板

```text
Segment: E01-01 / Cut: 1 / Intended duration: 4.0s
Start: medium two-shot, C01 screen-left and C02 screen-right, door behind C02.
Action: C01 places the closed red folder on the table using her right hand.
Camera: a slow, short push in, staying on the established side of the dialogue axis.
End: medium close-up of C01; right hand remains beside the closed folder.
Dialogue: exact script line, named speaker ID and voice identity in metadata.
Next-cut constraint: folder stays shut at the same table position; C02 looks left.
```

这只是运镜说明，不是直接可提交的固定节点格式。按 `novel-storyboard/references/h3-prompt.md` 生成上游 `h3Prompt`，保留逐字台词块、镜头起点与 Soundscape。默认英文描述、中文原文台词；用户选择中文提示词时沿用对应规则。声音中的撞击/脚步也会诱发动作，要和画面一致。

## 图像与真实节点的对齐

1. 建立有序参考清单：每个 `Picture k` 对应一个存在且已验收的图片文件、角色/场景版本和 cut 时间点。
2. 区分用途：角色身份参考、首帧、末帧、时间锚点不是同一个输入。原生 R2V 引用身份不等于已绑定某个切点；需要多帧时间锚时核对当前 `MiniMaxH3AddGuide`/相应节点的真实连接。
3. 如工作流只能接首帧，把段内 cuts 各自产生一个 I2V 任务，再由剪辑实现切镜。给这些任务分别改写单切提示词，去掉不存在的 Picture/Shot 指令；保留上游段落原稿与映射。
4. 帧索引根据实际模型 fps 和节点支持换算。当前本机节点可能将时长吸附到特殊帧数网格，读最新 `/object_info`，实际成片以 ffprobe 为准；不要把计划秒数当实际秒数。
5. 生成前校验起点/终点与图一致，生成后重新检查图中承诺是否兑现，不能以“提示词已经写了”代替画面证据。
