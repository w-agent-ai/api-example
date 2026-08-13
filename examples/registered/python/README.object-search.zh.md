# Python 图搜万物 API 示例

这个下载包只演示注册用户通过 API Key 调用图搜万物。

## 准备环境

```bash
pip install requests
```

## 使用方法

1. 打开 `object_search_api_demo.py`。
2. 修改顶部配置：
   - `API_KEY`：你的 W-Agent API Key。
   - `IMAGE_PATH`：待搜索图片路径。
   - `PROMPT`：要查找的目标描述，例如 `person`。
3. 运行：

```bash
python3 object_search_api_demo.py
```

程序会调用 `POST /v1/object-search`，返回匹配目标框和计费结果。
