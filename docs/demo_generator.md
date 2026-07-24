  cd /home/watrix/tiandk/agent/gaitAgent
  source algorithms/env.sh

  /opt/gaitagent/bin/portal-demo-generator \
    --pose-video /path/to/pose.mp4 \
    --gait-video1 /path/to/video1.mp4 \
    --gait-video2 /path/to/video2.mp4 \
    --out /opt/gaitagent/portal/examples


  /opt/gaitagent/bin/portal-demo-generator \
    --pose-video examples/video/pose.mp4 \
    --gait-video1 examples/video/gait1.mp4 \
    --gait-video2 examples/video/gait2.mp4 \
    --out /opt/gaitagent/portal/examples \
    --data-dir /opt/gaitagent/portal/demo-generator-work \
    --timeout 20m \
    --poll 2s

批量生成首页人体关节点示例视频：

```bash
cd /home/watrix/tiandk/agent/gaitAgent
source algorithms/env.sh

/opt/gaitagent/bin/portal-demo-generator \
  --pose-video-dir /path/to/pose-videos \
  --frame-extractor /opt/gaitagent/bin/portal-frame-extractor \
  --out /opt/gaitagent/portal/examples \
  --data-dir /opt/gaitagent/portal/demo-generator-work \
  --max-pose-sequences 6 \
  --max-pose-frames 0 \
  --fps 30 \
  --timeout 30m \
  --poll 2s
```

目录模式会直接从源视频抽帧生成关节点示例序列，不走 gait 视频解析，避免健身、站姿等静止动作被“有效步态”过滤掉。`--max-pose-frames 0` 表示全帧抽取，不跳帧；`--fps 30` 表示合成的 2D/3D 关节点视频按 30fps 写出。它会把每个视频写入 `pose-demo/videos/video-xxx/`，并在
`pose-demo/manifest.json` 中写入 `videos` 列表。首页人体关节点 demo 会在左侧提示文字下展示示例视频；右侧按“序列抓拍 -> 2D/3D 结果”两列展示。

批量生成首页步态识别多示例视频：

```bash
cd /home/watrix/tiandk/agent/gaitAgent
source algorithms/env.sh

/opt/gaitagent/bin/portal-demo-generator \
  --gait-video1-dir /path/to/video1-examples \
  --gait-video2-dir /path/to/video2-examples \
  --out /opt/gaitagent/portal/examples \
  --data-dir /opt/gaitagent/portal/demo-generator-work \
  --max-gait-sequences 0 \
  --timeout 30m \
  --poll 2s
```

多示例模式会把视频1写入 `gait-demo/video1-examples/video1-xxx/`，
把视频2写入 `gait-demo/video2-examples/video2-xxx/`，并在
`gait-demo/manifest.json` 中写入 `video1_examples`、`video2_examples`
和带 `left_video_id` / `right_video_id` 的 `comparisons`。首页步态识别
demo 左侧展示视频1、视频2示例；用户各选择一个示例后，右侧展示对应抓拍。
点击比对后，视频2抓拍按与当前视频1序列的相似度排序并显示相似度。

追加新视频到首页步态识别的“视频2”结果列表：

```bash
cd /home/watrix/tiandk/agent/gaitAgent
source algorithms/env.sh

/opt/gaitagent/bin/portal-demo-generator \
  --append-gait-video2 /path/to/new-video-a.mp4 \
  --append-gait-video2 /path/to/new-video-b.mp4 \
  --out /opt/gaitagent/portal/examples \
  --data-dir /opt/gaitagent/portal/demo-generator-work \
  --max-gait-sequences 0 \
  --timeout 30m \
  --poll 2s
```

追加模式会读取已有 `gait-demo/manifest.json`，把新视频解析出的序列编号接在
`video2-sequences` 后面，并补齐现有 video1 序列与新增 video2 序列的相似度。
`--max-gait-sequences 0` 表示追加全部有效序列；设置为正数时，只追加每个视频
前 N 个有效序列。
