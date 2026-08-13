# Go ReID API 示例

这个下载包只演示注册用户调用 ReID 识别。

运行前请打开 `reid_feature_demo/main.go`，修改顶部的 `apiKey`。

运行：

```bash
go run ./reid_feature_demo /path/to/person.jpg
```

接口输入应是单张人体目标图。程序会调用 `POST /v1/features/reid`，返回 512 维 ReID 特征和计费结果。
