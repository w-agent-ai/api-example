# 图搜万物 Go API Key 示例

本包使用一张本地图片和文字描述调用 `POST /v1/object-search`。

1. 编辑 `object_search_demo/main.go`，填写 `defaultAPIKey`。
2. 运行：

```bash
go run ./object_search_demo/main.go ./example.jpg "人"
```

返回内容包含匹配目标框和计费信息。
