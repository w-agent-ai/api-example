# C++ Local Video-To-Sequence Demo

Input is a video file. This demo:

1. Runs local C++ CPU person detection and tracking.
2. Writes one folder per detected person sequence.
3. Calls the C++ registered Sequence API demo for each generated sequence.

Run:

```bash
sudo apt-get install -y libcurl4-openssl-dev nlohmann-json3-dev
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
export GAIT_API_BASE_URL='https://www.h-agent.ai/api'
./examples/registered/cpp/local_video_sequence_demo/run_local_video_sequence_demo.sh /path/to/video.mp4
```
