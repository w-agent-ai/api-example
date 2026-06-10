# Go Local Video-To-Sequence Demo

Input is a video file. This demo:

1. Runs the local CPU video-to-sequence extractor.
2. Writes one folder per detected person sequence.
3. Calls the Go registered Sequence API demo for each generated sequence.

The local detector is C++ for speed and model compatibility; the upload/API
part is Go.

Run:

```bash
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
export GAIT_API_BASE_URL='https://www.h-agent.ai/api'
./examples/registered/go/local_video_sequence_demo/run_local_video_sequence_demo.sh /path/to/video.mp4
```
