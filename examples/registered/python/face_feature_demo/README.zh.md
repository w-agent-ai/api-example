# 人脸识别 Python 示例

这个示例演示本地图片到人脸特征的完整流程：

1. 读取一张图片。
2. 使用 ONNX Runtime CPU 加载 `face_detect.onnx` 检测人脸和 5 点关键点。
3. 根据双眼位置做仿射矫正，并裁剪出单张人脸图。
4. 调用 `POST /v1/features/face` 获取 512 维人脸特征。

准备依赖：

```bash
pip install requests opencv-python numpy onnxruntime
```

修改 `face_feature_api_demo.py` 顶部的 `API_KEY`，填入你的 API Key。

运行：

```bash
python3 face_feature_api_demo.py /path/to/image.jpg
```

接口输入是矫正后的人脸图片。检测和矫正发生在本地示例程序中，服务端只负责提取特征和计费。
