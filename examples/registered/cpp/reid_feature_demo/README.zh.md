# ReID 识别示例

这个示例演示单张人体图片到 ReID 特征的完整流程：

1. 读取一张人体图片。
2. 调用 `POST /v1/features/reid`。
3. 输出 512 维 ReID 特征和计费结果。

准备依赖：

```bash
sudo apt-get install -y cmake g++ libopencv-dev libcurl4-openssl-dev
```

修改 `main.cpp` 顶部的 `kAPIKey`，填入你的 API Key。

编译和运行：

```bash
cmake -S . -B build
cmake --build build -j
./build/w_agent_reid_feature_demo /path/to/image.jpg
```

接口输入应是单张人体目标图。多人原图请先在本地检测人体框并裁剪后再调用。
