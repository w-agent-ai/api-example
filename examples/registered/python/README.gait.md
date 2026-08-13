# Python Gait Recognition API Demo

This package only demonstrates gait recognition. It supports two inputs:

1. Existing tracked person sequence images.
2. A local video, processed locally into person sequences before calling the API.

## Setup

```bash
pip install requests
```

For the local video demo, also install:

```bash
pip install opencv-python numpy onnxruntime
```

## Existing Sequence Images

Put one person's ordered frame images directly under `./images`, then edit `API_KEY` at the top of `gait_sequence_api_demo.py`.

```bash
python3 gait_sequence_api_demo.py
```

The script creates a sequence task, uploads frames with multipart batch upload, and calls `POST /v1/sequences/{task_id}/parse`.

## Local Video Input

Edit `API_KEY` at the top of `gait_sequence_api_demo.py`, then run:

```bash
python3 local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
```

The script uses `gait_detect.onnx` locally to detect and track people, writes one sequence folder per track, then calls the gait API for each sequence.
