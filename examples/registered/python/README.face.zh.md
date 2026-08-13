# Python 人脸识别 API 示例

这个下载包只演示人脸识别。

## 准备环境

```bash
pip install requests opencv-python numpy onnxruntime
```

## 使用方法

1. 打开 `face_feature_demo/face_feature_api_demo.py`。
2. 修改顶部的 `API_KEY`。
3. 运行：

```bash
python3 face_feature_demo/face_feature_api_demo.py /path/to/image.jpg
```

程序会使用包内 `face_detect.onnx` 在本地检测人脸和 5 点关键点，矫正出单张人脸图，再调用 `POST /v1/features/face` 返回 512 维人脸特征。

服务端接口输入是矫正后的人脸图片，检测和矫正发生在本地示例程序中。
