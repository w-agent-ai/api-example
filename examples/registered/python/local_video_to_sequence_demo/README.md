# Python Local Video-To-Sequence API Demo

Input is a video file. The demos:

1. Runs local ONNX Runtime CPU person detection and tracking.
2. Writes one folder per detected person sequence.
3. Upload each generated sequence folder to the selected registered API.

Gait recognition:

```bash
pip install requests opencv-python numpy onnxruntime
编辑 examples/registered/python/gait_sequence_api_demo.py 顶部的 API_KEY。
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
```

Human 2D/3D keypoints:

```bash
pip install requests opencv-python numpy onnxruntime
编辑 examples/registered/python/gait_pose_api_demo.py 顶部的 API_KEY。
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_gait_pose_api_demo.py /path/to/video.mp4
```

Detector:

- The local detector uses `onnxruntime` with `gait_detect.onnx`.
- Model input is `images: float32[1,3,352,640]`, BGR, 0-255, NCHW.
- Outputs are `p3/p4/p5`; each point is decoded as `tx, ty, tw, th, obj`.
