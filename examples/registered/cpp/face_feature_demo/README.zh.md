# 人脸识别示例

这个示例演示本地图片到人脸特征的完整流程：

1. 读取一张图片。
2. 使用 ONNX Runtime CPU 加载 `face_detect.onnx` 检测人脸和 5 点关键点。
3. 根据双眼位置做仿射矫正，并裁剪出单张人脸图。
4. 调用 `POST /v1/features/face` 获取 512 维人脸特征。

准备依赖：

```bash
sudo apt-get install -y cmake g++ libopencv-dev libcurl4-openssl-dev
```

修改 `main.cpp` 顶部的 `kAPIKey`，填入你的 API Key。

编译和运行：

```bash
cmake -S . -B build
cmake --build build -j
./build/w_agent_face_feature_demo /path/to/image.jpg
```

接口输入是矫正后的人脸图片。检测和矫正发生在本地示例程序中，服务端只负责提取特征和计费。

包内已经带有 CPU 版 ONNX Runtime 和 `face_detect.onnx`，不需要 CUDA/cuDNN/TensorRT。
