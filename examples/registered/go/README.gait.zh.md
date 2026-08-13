# Go 步态识别 API 示例

这个下载包用于已有序列图片的 API 调用示例。输入视频请使用 Python 包里的 ONNX Runtime 本地视频转序列示例。

## 已有序列图片

适用场景：你已经有同一个人的连续抓拍图片，例如一个文件夹里放着 `001.jpg`、`002.jpg`、`003.jpg`。

代码目录：

```bash
sequence_demo/
```

使用方法：

1. 打开 `sequence_demo/main.go`。
2. 修改代码顶部的 `defaultAPIKey` 为你的 API Key。
3. 默认读取 `./images`，也可以修改 `defaultSeqDir` 或在运行时把目录作为参数传入。
4. 编译并运行：

```bash
cd sequence_demo
go build -o registered_sequence_demo main.go
./registered_sequence_demo
```

这个入口会调用步态识别接口，返回 `gait_feature`、`reid_feature`、`face_feature` 等身份特征。

## 需要修改的代码项

- `apiKey` / `defaultAPIKey`：你的 API Key。
- `baseURL` / `defaultBaseURL`：默认是 `https://www.w-agent.cn/api`，一般不用改。
- `defaultSeqDir`：默认序列图片目录，默认 `./images`。
