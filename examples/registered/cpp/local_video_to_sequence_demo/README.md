# C++ Local Video Gait API Demo

Input is a video file. This package builds a complete C++ gait recognition demo:

1. Runs local C++ CPU ONNX Runtime person detection and tracking.
2. Writes one folder per detected person sequence.
3. Calls the registered gait sequence API for each generated sequence.

Before building, edit `local_video_api_demo.cpp`:

- `kAPIKey`: your API Key.
- `kVideoPath`: optional default video path if no command-line path is passed.

Build and run:

```bash
sudo apt-get install -y cmake g++ libopencv-dev libcurl4-openssl-dev nlohmann-json3-dev
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j

./build/local_video_to_gait_api_demo /path/to/video.mp4
```

The package includes the Linux x64 CPU ONNX Runtime files under
`third_party/onnxruntime-linux-x64/` and the detector model
`gait_detect.onnx`. No CUDA/cuDNN/TensorRT dependency is required. The
default endpoint is already set to `https://www.w-agent.cn/api`.
