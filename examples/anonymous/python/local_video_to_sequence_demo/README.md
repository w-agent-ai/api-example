# Anonymous Python Local Video-To-Sequence x402 Demo

Input is a video file. The demos:

1. Runs local ONNX Runtime CPU person detection and tracking.
2. Writes one folder per detected person sequence.
3. Upload each generated sequence folder to the selected public API.
4. Pay each anonymous API call with x402.

Gait recognition:

```bash
pip install requests opencv-python numpy onnxruntime eth-account web3 'x402[evm]'
编辑 examples/anonymous/python/anonymous_sequence_x402_demo.py 顶部的 EVM_PRIVATE_KEY。
python3 examples/anonymous/python/local_video_to_sequence_demo/local_video_to_sequence_x402_demo.py /path/to/video.mp4
```

Human 2D/3D keypoints:

```bash
pip install requests opencv-python numpy onnxruntime eth-account web3 'x402[evm]'
编辑 examples/anonymous/python/anonymous_gait_pose_x402_demo.py 顶部的 EVM_PRIVATE_KEY。
python3 examples/anonymous/python/local_video_to_sequence_demo/local_video_to_gait_pose_x402_demo.py /path/to/video.mp4
```

Detector:

- The local detector uses `onnxruntime` with `gait_detect.onnx`.
- Model input is `images: float32[1,3,352,640]`, BGR, 0-255, NCHW.
- Outputs are `p3/p4/p5`; each point is decoded as `tx, ty, tw, th, obj`.
