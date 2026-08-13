# Python 本地视频转序列示例

输入是一个本地视频文件。示例会：

1. 使用 ONNX Runtime CPU 和 `gait_detect.onnx` 在本地做人检测和跟踪。
2. 为每个检测到的人体轨迹写出一个序列目录。
3. 把生成的序列上传到对应的注册用户 API。

步态识别：

```bash
pip install requests opencv-python numpy onnxruntime
编辑 examples/registered/python/gait_sequence_api_demo.py 顶部的 API_KEY。
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
```

人体 2D/3D 关节点：

```bash
pip install requests opencv-python numpy onnxruntime
编辑 examples/registered/python/gait_pose_api_demo.py 顶部的 API_KEY。
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_gait_pose_api_demo.py /path/to/video.mp4
```

本地检测模型输入是 `images: float32[1,3,352,640]`，BGR，0-255，NCHW。
