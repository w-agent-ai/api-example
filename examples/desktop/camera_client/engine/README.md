# W-Agent Local Engine

This is the native C++ process used by the desktop client for local video and
camera parsing.

The Go desktop client starts this executable and reads newline-delimited JSON
events from stdout. The engine must not print non-JSON logs to stdout; write
diagnostic logs to stderr.

## Build

Windows with OpenCV:

```powershell
cmake -S examples/desktop/camera_client/engine -B build\w-agent-local-engine -G "Visual Studio 17 2022" -A x64
cmake --build build\w-agent-local-engine --config Release
```

Linux:

```bash
cmake -S examples/desktop/camera_client/engine -B /tmp/w-agent-local-engine-build
cmake --build /tmp/w-agent-local-engine-build -j
```

## Run

Video file:

```bash
w-agent-local-engine --source-id vid_1 --type video --video input.mp4 --output-dir ./runtime/vid_1
```

Camera or RTSP:

```bash
w-agent-local-engine --source-id cam_1 --type camera --rtsp rtsp://admin:pass@192.168.1.64/Streaming/Channels/101 --output-dir ./runtime/cam_1
```

## JSONL Protocol

All events are one JSON object per line.

Ready:

```json
{"type":"ready","source_id":"cam_1"}
```

Progress:

```json
{"type":"progress","source_id":"cam_1","processed":300,"total":12000,"fps":25.4}
```

Sequence ready:

```json
{
  "type":"sequence",
  "source_id":"cam_1",
  "sequence_id":"seq_000001",
  "track_id":"track_000003",
  "sequence_dir":"D:/WAgentData/runtime/cam_1/seq_000001",
  "frame_paths":[
    "D:/WAgentData/runtime/cam_1/seq_000001/frame_000001.jpg"
  ],
  "preview_path":"D:/WAgentData/runtime/cam_1/seq_000001/preview.jpg",
  "video_path":"D:/WAgentData/captures/cam_1/seq_000001.mp4"
}
```

Done:

```json
{"type":"done","source_id":"vid_1"}
```

Error:

```json
{"type":"error","source_id":"cam_1","message":"failed to open source"}
```

## Required Windows Implementation Work

The current skeleton opens video/RTSP and emits progress. The Windows agent must
port the existing detector/tracker code from:

```text
examples/registered/cpp/local_video_to_sequence_demo/
```

Required behavior:

- Open local video files with OpenCV.
- Open RTSP cameras with OpenCV/FFmpeg backend.
- Detect persons with `persondet.cpp`.
- Track boxes with the same IoU-based tracker used by the local demo, or a
  better tracker if available.
- Save one directory per stable moving person sequence.
- Emit `sequence` when the sequence is ready.
- Save preview image.
- Encode a short original-frame capture clip to MP4, resized to max 720p.
- Respect the desktop setting for whether the capture clip contains drawn boxes.

The Go client handles W-Agent API upload/parse, feature comparison, history
records, and library matching after it receives `sequence` events.
