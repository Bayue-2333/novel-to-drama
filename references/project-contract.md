# 项目状态、依赖与交付门

## 目录与状态

生产目录放当前工作区的 `work/<project-id>/`（用户指定位置优先）：

```text
source/                  原文副本、来源与覆盖范围
outline/ characters/ art/ script/ storyboard/   五份原生 JSON/报告/图片
generation/              API 图、绑定表、prompt_id 与生成日志
assets/video/ assets/audio/                    原始版本化媒体
audio/                   声线表、逐句对齐表、混音 stems
edit/                    EDL/剪辑工程和渲染配置
qa/                      证据、问题单、最终检查记录
project.json             本技能的计划和续作状态
generation_map.json      上游段/cut 到实际任务/素材的映射
continuity.json          每镜状态与接镜约束
openmontage/             使用其 schema 的阶段产物与 checkpoints
```

最终交付集中放 `outputs/<project-id>/`，包含母版、字幕版、SRT/ASS、前期资料、剪辑文件、生成清单和检查报告。项目若必须带图片报告一起迁移，保留相对目录结构；交付 manifest 的相对路径以它所在目录为基准，不能指向另一个人的计算机目录。

`project.json` 从模板复制，null 代表尚未确定，不是已完成。阶段状态限定为 `pending / in_progress / pass / failed / blocked / partial / stale`。每个 artifact 记录 `id, path, sha256, input_hashes, stage, status`。用户授权记录写真实范围与原话摘要，不能预填成“全部批准”。

依赖失效按引用传播：原文/大纲改 → 受影响剧本/角色/场景；角色图改 → 引用它的关键帧与视频；对白/镜长改 → 分镜、视频、音轨对齐、EDL、字幕；剪辑/混音/字幕改 → 母版或字幕版与终检。未受影响的文件可复用。文件存在不足以判定可以跳过，输入哈希与验收状态也必须匹配。

`generation_map.json` 每任务至少记录：`job_id, segment_id, cut_indices, script_beats, picture_order, workflow_path, workflow_sha256, model_stack, seed, prompt_id, status, output_path, output_sha256, measured_duration, measured_fps, review`。没有返回 job ID 或实测数据时写 null 和原因，不填推测值。

## 交付清单格式

`scripts/verify_delivery.py` 使用本技能自己的清单，不是 OpenMontage 的 final_review schema。用户要求的所有集写到 `required_episode_ids`；每集对应一条。以下示例尚未审查，不能直接变为 pass：

```json
{
  "schema_version": 1,
  "required_episode_ids": ["E01"],
  "episodes": [{
    "id": "E01",
    "video": "E01-subtitled.mp4",
    "master": "E01-master.mp4",
    "srt": "E01.srt",
    "ass": "E01.ass",
    "expected": {"width": 1080, "height": 1920, "fps": 24, "audio_sample_rate": 48000, "track_tolerance_seconds": 0.15},
    "reviews": {},
    "issues": []
  }]
}
```

分辨率/fps 按项目真实交付要求填写，不把示例 1080×1920 当 H3 原生生成规格。技术校验会执行两份 MP4 的全流解码，检查音视频轨、期望规格、SRT/ASS 对时与文本一致。默认字幕校验只支持按时间排序、无重叠的对白轨；用户要求多层重叠字幕时应按各层扩展校验并增加真实版式复核，不静默删字幕绕过检查。

运行示例：

```text
python scripts/verify_delivery.py /absolute/path/delivery_manifest.json --ffprobe /absolute/path/ffprobe --ffmpeg /absolute/path/ffmpeg --out /absolute/path/qa/delivery-check.json
```

第一次执行即使缺 review，也会在报告逐集输出 `hashes` 与 `bundle_sha256`。bundle 是 video/master/srt/ass 四份文件哈希的规范 JSON（键排序、无空白）的 SHA-256，任何一个文件变化都会失效。也可通过脚本的 `sha256` 和 `bundle_digest` 函数计算，计算哈希本身不代表完成检查。

## 记录实际检查

每集的 `reviews` 必须包含 `visual, audio, sync, subtitles, continuity` 五类。每类结构如下，只有真正检查后才能写 pass：

```json
{
  "status": "partial",
  "bundle_sha256": "使用真实bundle哈希",
  "method": "实际使用的播放/连续片段分析/听辨方法与工具",
  "reviewer": "实际执行者或模型",
  "reviewed_at": "实际ISO时间",
  "ranges": [[0, 12.0]],
  "evidence": ["qa/E01-sync-review.md"]
}
```

`ranges` 是已经检查的最终时间线区间，可有多个，pass 时其并集必须覆盖整片，不能把抽样的 0/中/末三帧记录成 `[0,全长]`。`sync` 与 `subtitles` 可以将无对白区间记为“已检查、此段无对白/字幕”，附依据；不能漏掉区间。检查所有相邻集的结尾/开场，把跨集证据链接到 continuity。

证据文档应含具体时间码、观察到的内容、台词与字幕核对结果、检查方法及限制。同一文档可以支持多个类别，但内容需真实覆盖。`visual` 同时检查母版与字幕版画面，`subtitles` 包含实际烧录和位置，不能只解析 ASS 文件。

问题示例：`{"id":"Q01","severity":"major","status":"resolved","verified_on_bundle_sha256":"真实bundle哈希"}`，完整问题单包含 SKILL 中的定位、修复和证据。blocker/major 未解决或修复验证对应旧 bundle 会阻止完成。minor 可以保留 open，在交付说明列出；不要以“通过”隐瞒已知问题。

脚本只验证记录结构、范围与当前文件的关联，无法识别虚构证据、假口型同步或任意乱码形状。最后仍需 Codex 按用户需求独立复读清单和真实视频、音频、字幕。未完成全部模态检查时如实交付 `partial`，告知剩余具体工作。
