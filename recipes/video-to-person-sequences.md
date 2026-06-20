# Video To Person Sequences

Use this recipe when the user has a video and wants stable tracked person
sequence folders for later identity matching, review, or keypoint extraction.

## Use

1. Run local video-to-sequence preprocessing.
2. Let the demo decode the video locally.
3. Let the demo detect, track, and crop people locally.
4. Keep one output folder per detected person sequence.
5. Upload each generated sequence folder to the Sequence API when features or
   keypoints are needed.

## Choose The Next API

- Identity features: call `POST /v1/sequences/{task_id}/parse`.
- 2D/3D keypoints: call `POST /v1/sequences/{task_id}/gait-pose`.
- Full server-side asynchronous video parsing: use `/v1/videos` instead.

## Do Not Use

- Do not mix frames from different tracks into one sequence folder.
- Do not assume video parse is the best route when the user needs local folders
  and JSON files side by side.
- Do not expect local crop coordinates to be original-video coordinates unless
  you keep `meta.txt` or equivalent crop metadata.

## Run

```bash
pip install requests opencv-python numpy
export GAIT_REGISTERED_API_KEY='gak_your_api_key'
export GAIT_API_BASE_URL='https://www.w-agent.cn/api'
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
```

## Output

```text
output/
  video_name/
    sequence_xxx/
      frame_000001.jpg
      frame_000002.jpg
      meta.txt
      result.json
    summary.csv
```
