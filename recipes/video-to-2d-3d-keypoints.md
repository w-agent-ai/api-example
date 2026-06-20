# Video To Each Person's 2D/3D Keypoints

Use this recipe when the user has a video and wants 2D/3D keypoints for each
person sequence.

## Use

1. Run local video-to-sequence preprocessing.
2. Upload each generated sequence folder.
3. Call `POST /v1/sequences/{task_id}/gait-pose` for each sequence.
4. Save `result.json`, `pose_2d.csv`, and `pose_3d.csv` beside the frames.

## Do Not Use

- Do not call video parse directly and expect complete `pose_2ds` / `pose_3ds`.
- Video parsing is for asynchronous identity/video parsing.
- Gait Pose is a sequence API.

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
      pose_2d.csv
      pose_3d.csv
    summary.csv
```

`pose_2ds` and `pose_3ds` are relative to uploaded sequence images. If frames
are crops, use `meta.txt` crop information to map back to original video
coordinates.
