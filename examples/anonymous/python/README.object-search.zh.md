# Python 图搜万物 x402 示例

这个下载包只演示匿名用户通过 x402 支付调用图搜万物。

## 准备环境

```bash
pip install requests eth-account web3 'x402[evm]'
```

## 使用方法

1. 打开 `anonymous_object_search_x402_demo.py`。
2. 修改顶部的 `EVM_PRIVATE_KEY`、`IMAGE_PATH` 和 `PROMPT`。
3. 运行：

```bash
python3 anonymous_object_search_x402_demo.py
```

程序会先请求接口获得 HTTP 402 支付信息，签名支付头后重试 `POST /v1/public/object-search`。
