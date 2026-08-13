# Go 本地视频转序列示例

输入是一个本地视频文件。示例会：

1. 调用本地 C++ CPU 检测和跟踪程序生成序列。
2. 为每个检测到的人体轨迹写出一个序列目录。
3. 使用 Go 代码把生成的序列上传到注册用户 API。

本地检测部分使用 C++，上传和 API 调用部分使用 Go。

运行前请修改 `main.go`：

- `apiKey`：你的 API Key。
- `baseURL`：API 地址，默认是 `https://www.w-agent.cn/api`。
- `videoPath`：可选默认视频路径。

编译和运行：

```bash
cmake -S cpp_detector -B cpp_detector/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp_detector/build -j
go build -o local_video_api_demo main.go
./local_video_api_demo /path/to/video.mp4
```
