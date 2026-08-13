# Python 步态识别 API 示例

这个下载包只演示步态识别。支持两类输入：

1. 已有人体序列图片，直接调用步态识别 API。
2. 输入本地视频，先在本地检测、跟踪并生成序列，再调用步态识别 API。

## 准备环境

```bash
pip install requests
```

如果运行本地视频示例，还需要：

```bash
pip install opencv-python numpy onnxruntime
```

## 已有序列图片

把同一个人的连续抓拍图片放到 `./images` 目录，然后修改 `gait_sequence_api_demo.py` 顶部的 `API_KEY`。

```bash
python3 gait_sequence_api_demo.py
```

程序会创建序列任务、批量上传图片，并调用 `POST /v1/sequences/{task_id}/parse`。

## 输入视频

修改 `gait_sequence_api_demo.py` 顶部的 `API_KEY`，然后运行：

```bash
python3 local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
```

程序会使用包内 `gait_detect.onnx` 在本地检测人体、跟踪并生成序列，再逐个序列调用步态识别 API。
