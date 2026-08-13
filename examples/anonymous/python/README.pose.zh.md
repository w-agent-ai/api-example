# Python 人体 2D/3D 关节点 x402 示例

这个下载包只演示匿名用户通过 x402 支付调用人体 2D/3D 关节点。

## 准备环境

```bash
pip install requests eth-account web3 'x402[evm]'
```

如果运行本地视频示例，还需要：

```bash
pip install opencv-python numpy onnxruntime
```

## 已有序列图片

把同一个人的连续抓拍图片放到 `./images` 目录，修改 `anonymous_gait_pose_x402_demo.py` 顶部的 `EVM_PRIVATE_KEY`。

```bash
python3 anonymous_gait_pose_x402_demo.py
```

## 输入视频

```bash
python3 local_video_to_sequence_demo/local_video_to_gait_pose_x402_demo.py /path/to/video.mp4
```

程序会本地检测和跟踪人体序列，再通过 x402 支付调用人体 2D/3D 关节点 API。
