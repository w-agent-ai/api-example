# ReID 识别示例

这个示例演示单张人体图片到 ReID 特征的完整流程：

1. 读取一张人体图片。
2. 调用 `POST /v1/features/reid`。
3. 输出 512 维 ReID 特征和计费结果。

运行前请先在 `main.go` 顶部填入你的 API Key。

运行：

```bash
go run . /path/to/image.jpg
```

接口输入应是单张人体目标图。多人原图请先在本地检测人体框并裁剪后再调用。
