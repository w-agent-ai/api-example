# 注册用户 Python 示例

这些示例用于注册用户通过 API Key 调用 W-Agent API。

## 准备环境

```bash
pip install requests
```

如果运行本地视频检测/跟踪示例，还需要：

```bash
pip install opencv-python numpy onnxruntime
```

## 通用配置

打开对应的 `.py` 文件，直接修改顶部配置：

- `API_KEY`：你的 W-Agent API Key。
- `BASE_URL`：API 地址，官网默认是 `https://www.w-agent.cn/api`。
- `IMAGE_PATH`：单张图片路径。
- `SEQ_DIR`：人体序列图片目录。
- `RESULT_DIR`：结果保存目录。

示例代码里已经写了关键注释，用户可以直接看代码理解每一步。

## 示例列表

### 图搜万物

```bash
python3 object_search_api_demo.py
```

输入一张图片和文字描述，调用 `POST /v1/object-search`，返回匹配目标框。

### 人脸识别

```bash
python3 face_feature_demo/face_feature_api_demo.py /path/to/image.jpg
```

本地用 `face_detect.onnx` 检测和矫正人脸，再调用 `POST /v1/features/face` 返回 512 维人脸特征。

### ReID 识别

```bash
python3 reid_feature_demo/reid_feature_api_demo.py /path/to/person.jpg
```

输入一张单个人体目标图，调用 `POST /v1/features/reid` 返回 512 维 ReID 特征。

### 步态识别

```bash
python3 gait_sequence_api_demo.py
```

输入一个已经跟踪好的人体序列目录，批量上传帧图片，调用 `POST /v1/sequences/{task_id}/parse`。

### 人体 2D/3D 关节点

```bash
python3 gait_pose_api_demo.py
```

输入一个已经跟踪好的人体序列目录，批量上传帧图片，调用 `POST /v1/sequences/{task_id}/gait-pose`。

### 本地视频转序列

```bash
python3 local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
python3 local_video_to_sequence_demo/local_video_to_gait_pose_api_demo.py /path/to/video.mp4
```

本地使用 `gait_detect.onnx` 做人体检测和跟踪，导出每个人的序列图片，再上传到 API。
