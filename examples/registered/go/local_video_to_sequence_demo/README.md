# Go Local Video Gait API Demo

Input is a video file. This package builds a complete Go gait recognition demo. It:

1. Runs the local CPU video-to-sequence extractor.
2. Writes one folder per detected person sequence.
3. Calls the registered gait sequence API for each generated sequence.

The local detector is C++ for speed and model compatibility; the upload/API
part is Go.

Before building, edit `main.go`:

- `apiKey`: your API Key.
- `baseURL`: API endpoint. The default is `https://www.w-agent.cn/api`.
- `videoPath`: default video path if no command-line path is passed.

Build and run:

```bash
cmake -S cpp_detector -B cpp_detector/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp_detector/build -j
go build -o local_video_api_demo main.go

./local_video_api_demo /path/to/video.mp4
```

Base URL:

- Mainland China: `https://www.w-agent.cn/api`
- Overseas entry: `https://www.h-agent.ai/api`
- Overseas redirects to `w-agent.cn` are expected.
- Do not use `https://api.w-agent.cn` unless it is explicitly documented.
