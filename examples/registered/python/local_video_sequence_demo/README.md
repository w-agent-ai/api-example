# Python Local Video-To-Sequence Demo

Input is a video file. The demo:

1. Runs local CPU person detection and tracking.
2. Writes one folder per detected person sequence.
3. Uploads each generated sequence folder to the registered Sequence API.

Run:

```bash
pip install requests opencv-python numpy
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
export GAIT_API_BASE_URL='https://www.h-agent.ai/api'
python3 examples/registered/python/local_video_sequence_demo/local_video_sequence_demo.py /path/to/video.mp4
```
