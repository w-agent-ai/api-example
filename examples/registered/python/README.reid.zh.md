# Python ReID 识别 API 示例

这个下载包只演示 ReID 识别。

## 准备环境

```bash
pip install requests
```

## 使用方法

1. 准备一张单个人体目标图。
2. 打开 `reid_feature_demo/reid_feature_api_demo.py`。
3. 修改顶部的 `API_KEY` 和 `IMAGE_PATH`，或者运行时传入图片路径。
4. 运行：

```bash
python3 reid_feature_demo/reid_feature_api_demo.py /path/to/person.jpg
```

程序会调用 `POST /v1/features/reid`，返回 512 维 ReID 特征。

接口输入应是单张人体目标图。多人原图请先在本地检测人体框并裁剪后再调用。
