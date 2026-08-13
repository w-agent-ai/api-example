# C++ 步态识别 API 示例

这个下载包包含两类入口：已有序列图片直接调用 API，以及输入视频后在本地用 C++ CPU ONNX Runtime 检测、跟踪、生成序列，再调用 API。

## 已有序列图片

适用场景：你已经有同一个人的连续抓拍图片，例如一个文件夹里放着 `001.jpg`、`002.jpg`、`003.jpg`。

代码目录：

```bash
sequence_demo/
```

使用方法：

1. 打开 `sequence_demo/main.cpp`。
2. 修改代码顶部的 `kAPIKey` 为你的 API Key。
3. 默认读取 `./images`，也可以修改 `kSeqDir` 或在运行时把目录作为参数传入。
4. 编译并运行：

```bash
cd sequence_demo
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/registered_sequence_demo
```

这个入口会调用步态识别接口，返回 `gait_feature`、`reid_feature`、`face_feature` 等身份特征。

## 输入视频

适用场景：你手里是完整视频，希望先在本地检测人体、跟踪并切出序列，再上传序列调用步态识别 API。

代码目录：

```bash
local_video_to_sequence_demo/
```

使用方法：

1. 打开 `local_video_to_sequence_demo/local_video_api_demo.cpp`。
2. 修改代码顶部的 `kAPIKey` 为你的 API Key。
3. 修改 `kVideoPath` 为默认视频路径，或者运行时把视频路径作为参数传入。
4. 编译并运行：

```bash
cd local_video_to_sequence_demo
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/local_video_to_gait_api_demo /path/to/video.mp4
```

这个入口使用包内 `gait_detect.onnx` 和 Linux x64 CPU 版 ONNX Runtime，不需要 CUDA。

## 需要修改的代码项

- `kAPIKey`：你的 API Key。
- `kSeqDir`：默认序列图片目录，默认 `./images`。
- `kVideoPath`：可选默认视频路径。
