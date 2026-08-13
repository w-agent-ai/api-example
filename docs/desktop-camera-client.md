# Desktop Camera Client Implementation Guide

This document is for the Windows development agent that continues the W-Agent
desktop camera client.

## Architecture

The client uses the agreed scheme C:

- Go desktop shell: app window, local HTTP API, JSON state, W-Agent API calls,
  feature matching, capture/library records.
- Native WebView shell: Windows WebView2, macOS WKWebView, Linux WebKitGTK.
- C++ local engine: opens cameras/videos, detects persons, tracks boxes, saves
  person crop sequences and capture clips, emits JSONL events.

The Go process starts the C++ engine as a child process and reads one JSON event
per line from stdout. The C++ engine must write logs only to stderr.

## Important Paths

- Go app entry: `cmd/camera-client`
- Go desktop backend: `internal/desktopclient`
- Embedded UI: `internal/desktopclient/web/ui.html`
- C++ engine skeleton: `examples/desktop/camera_client/engine`
- Existing C++ detector/tracker demo to port:
  `examples/registered/cpp/local_video_to_sequence_demo`

## Build

Linux fallback build:

```bash
go build -o /tmp/w-agent-camera-client ./cmd/camera-client
```

Windows app-window build from Windows:

```powershell
go build -o w-agent-camera-client.exe ./cmd/camera-client
```

Windows app-window cross build from Linux requires mingw-w64:

```bash
GOOS=windows GOARCH=amd64 CGO_ENABLED=1 CC=x86_64-w64-mingw32-gcc \
  go build -o /tmp/w-agent-camera-client.exe ./cmd/camera-client
```

C++ engine build on Windows:

```powershell
cmake -S examples/desktop/camera_client/engine -B build\w-agent-local-engine -G "Visual Studio 17 2022" -A x64
cmake --build build\w-agent-local-engine --config Release
```

Run Go client with an explicit engine:

```powershell
.\w-agent-camera-client.exe -engine .\w-agent-local-engine.exe
```

## Current Implemented Go Features

- W-Agent account login through `/v1/users/login`.
- API Key list sync from login response.
- User pastes full `gak_...` API Key once; it is saved locally for the selected
  API Key.
- App-window shell with browser fallback.
- Local JSON state.
- Settings auto-save.
- Camera/video source list.
- Start/stop source API:
  - `POST /api/sources/start`
  - `POST /api/sources/stop`
- Process engine runner.
- W-Agent sequence API client:
  - create sequence task
  - batch-upload crop frames with `/v1/sequences/{task_id}/uploads/batch`
  - call `/v1/sequences/{task_id}/parse`
- Feature similarity:
  - gait-to-gait
  - face-to-face
  - reid-to-reid
  - max score wins
- Library matching with threshold.
- Capture records stored in local JSON.

## Engine JSONL Contract

See `examples/desktop/camera_client/engine/README.md`.

The most important event is `sequence`:

```json
{
  "type": "sequence",
  "source_id": "cam_1",
  "sequence_id": "seq_000001",
  "track_id": "track_000003",
  "sequence_dir": "D:/WAgentData/runtime/cam_1/seq_000001",
  "frame_paths": ["D:/WAgentData/runtime/cam_1/seq_000001/frame_000001.jpg"],
  "preview_path": "D:/WAgentData/runtime/cam_1/seq_000001/preview.jpg",
  "video_path": "D:/WAgentData/captures/cam_1/seq_000001.mp4"
}
```

When Go receives this event it uploads the frames to W-Agent, gets identity
features, matches the library, and inserts a history capture record.

## Data Directory Contract

The user can choose a directory copied from another computer. Keep data
self-contained under that directory:

```text
WAgentData/
  runtime/
    <source_id>/
      <sequence_id>/
        frame_000001.jpg
        preview.jpg
        meta.json
  captures/
    <source_id>/
      <sequence_id>.mp4
  features/
    <source_id>/
      <sequence_id>.json
  library/
    <person_id>/
      feature.json
      preview.jpg
```

Go currently stores the index/state in the config JSON. The Windows agent should
preserve the directory contract so later we can rebuild the JSON index by
scanning the directory.

## Required Windows Work

1. Finish C++ engine:
   - Port `persondet.cpp`, `persondet.h`, `persondet_weights.cpp`.
   - Port video tracking/cropping logic from `video_sequence_demo.cpp`.
   - Support local video path input.
   - Support RTSP camera input.
   - Emit progress/sequence/done/error JSONL events.
   - Encode capture clips to MP4, resized to max 720p.
   - Draw detection boxes when the setting asks for it.

2. Camera discovery:
   - Scan local subnet IPs.
   - Probe RTSP candidates by brand.
   - Let users preview before adding.
   - Keep max camera count at 4.

3. UI polish:
   - Wire preview button to a live frame endpoint or engine preview event.
   - Add user-facing errors for missing engine, bad RTSP, missing full API Key,
     and W-Agent API failures.

4. Packaging:
   - Ship `w-agent-camera-client.exe`.
   - Ship `w-agent-local-engine.exe` next to it unless statically linked into
     one process later.
   - Include OpenCV runtime DLLs required by the engine.
   - Ensure WebView2 Runtime is installed or prompt user to install it.

## Acceptance Tests

- Login with W-Agent account.
- Paste full API Key.
- Add local video.
- Start parsing.
- Engine emits at least one sequence event.
- Go uploads sequence frames and calls W-Agent parse API.
- History capture appears with similarity.
- Add capture to library.
- Start a second parse; matching name appears when similarity is above
  threshold.
- Stop camera/video source.
- Restart app; settings, sources, captures, and library persist.

## Verification Commands

Go:

```bash
go test ./internal/desktopclient
go build -o /tmp/w-agent-camera-client ./cmd/camera-client
```

UI script:

```bash
node - <<'NODE'
const fs = require('fs');
const html = fs.readFileSync('internal/desktopclient/web/ui.html', 'utf8');
const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map(m => m[1]);
new Function(scripts.join('\n'));
console.log('camera-ui-js-ok');
NODE
```
