# Python Human 2D/3D Keypoints x402 Demo

This package only demonstrates human 2D/3D keypoint extraction for anonymous users with x402 payment.

## Setup

```bash
pip install requests eth-account web3 'x402[evm]'
```

For the local video demo, also install:

```bash
pip install opencv-python numpy onnxruntime
```

## Existing Sequence Images

Put one person's ordered frame images directly under `./images`, then edit `EVM_PRIVATE_KEY` at the top of `anonymous_gait_pose_x402_demo.py`.

```bash
python3 anonymous_gait_pose_x402_demo.py
```

## Local Video Input

```bash
python3 local_video_to_sequence_demo/local_video_to_gait_pose_x402_demo.py /path/to/video.mp4
```

The script detects and tracks people locally, then pays through x402 and calls the human keypoints API.
