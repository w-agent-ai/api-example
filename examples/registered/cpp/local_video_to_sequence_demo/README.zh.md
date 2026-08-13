# C++ 本地视频转序列示例

输入是一个本地视频文件。示例会：

1. 使用 C++ CPU ONNX Runtime 和 `gait_detect.onnx` 在本地做人检测和跟踪。
2. 为每个检测到的人体轨迹写出一个序列目录。
3. 把生成的序列上传到对应的注册用户 API。

运行前请修改 `local_video_api_demo.cpp`：

- `kAPIKey`：你的 API Key。
- `kVideoPath`：可选默认视频路径。

编译和运行：

```bash
sudo apt-get install -y cmake g++ libopencv-dev libcurl4-openssl-dev nlohmann-json3-dev
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/local_video_to_gait_api_demo /path/to/video.mp4
```

包内已经包含 Linux x64 CPU 版 ONNX Runtime 和 `gait_detect.onnx`，不需要 CUDA/cuDNN/TensorRT。
