# C++ 人脸识别 API 示例

这个下载包演示从本地图片到人脸特征的完整流程：

1. 读取一张本地图片。
2. 使用包内 `face_detect.onnx` 和 CPU 版 ONNX Runtime 检测人脸与 5 点关键点。
3. 根据双眼位置矫正并裁剪出单张人脸图。
4. 调用 `POST /v1/features/face` 获取 512 维人脸特征。

## 编译依赖

```bash
sudo apt-get install -y cmake g++ libopencv-dev libcurl4-openssl-dev
```

## 使用方法

1. 打开 `face_feature_demo/main.cpp`。
2. 修改代码顶部的 `kAPIKey` 为你的 API Key。
3. 编译并运行：

```bash
cd face_feature_demo
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/w_agent_face_feature_demo /path/to/image.jpg
```

接口输入是矫正后的人脸图片。检测和矫正发生在本地示例程序中，服务端只负责提取特征和计费。

包内已经带有 Linux x64 CPU 版 ONNX Runtime 和 `face_detect.onnx`，不需要 CUDA/cuDNN/TensorRT。
