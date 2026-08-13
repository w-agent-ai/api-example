# Python 本地视频转序列 x402 示例

输入是一个本地视频文件。示例会：

1. 使用 ONNX Runtime CPU 和 `gait_detect.onnx` 在本地做人检测和跟踪。
2. 为每个检测到的人体轨迹写出一个序列目录。
3. 通过 x402 支付调用对应的 public API。

步态识别：

```bash
pip install requests opencv-python numpy onnxruntime eth-account web3 'x402[evm]'
编辑 examples/anonymous/python/anonymous_sequence_x402_demo.py 顶部的 EVM_PRIVATE_KEY。
python3 examples/anonymous/python/local_video_to_sequence_demo/local_video_to_sequence_x402_demo.py /path/to/video.mp4
```

人体 2D/3D 关节点：

```bash
pip install requests opencv-python numpy onnxruntime eth-account web3 'x402[evm]'
编辑 examples/anonymous/python/anonymous_gait_pose_x402_demo.py 顶部的 EVM_PRIVATE_KEY。
python3 examples/anonymous/python/local_video_to_sequence_demo/local_video_to_gait_pose_x402_demo.py /path/to/video.mp4
```
