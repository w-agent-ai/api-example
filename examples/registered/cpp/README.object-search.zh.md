# 图搜万物 C++ API Key 示例

本包将一张本地图片和文字描述发送到 `POST /v1/object-search`。

1. 编辑 `object_search_demo/main.cpp`，填写 `kAPIKey`。
2. 编译：

```bash
cmake -S object_search_demo -B build
cmake --build build
```

3. 运行：

```bash
./build/w_agent_object_search_demo ./example.jpg "人"
```

返回内容包含匹配目标框和计费信息。图片以原始 Base64 上传，不带 `data:image/...` 前缀。
