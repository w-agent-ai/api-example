# C++ ReID 识别 API 示例

这个下载包演示单张人体图片到 ReID 特征的完整流程：

1. 读取一张单个人体目标图。
2. JPEG 编码并转成 base64。
3. 调用 `POST /v1/features/reid` 获取 512 维 ReID 特征。

## 编译依赖

```bash
sudo apt-get install -y cmake g++ libopencv-dev libcurl4-openssl-dev
```

## 使用方法

1. 打开 `reid_feature_demo/main.cpp`。
2. 修改代码顶部的 `kAPIKey` 为你的 API Key。
3. 编译并运行：

```bash
cd reid_feature_demo
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/w_agent_reid_feature_demo /path/to/person.jpg
```

接口输入应是单张人体目标图。多人原图请先在本地检测人体框并裁剪后再调用。
