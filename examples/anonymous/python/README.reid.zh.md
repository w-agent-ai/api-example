# Python ReID 识别 x402 示例

这个下载包只演示匿名用户通过 x402 支付调用 ReID 识别。

## 准备环境

```bash
pip install requests eth-account web3 'x402[evm]'
```

## 使用方法

1. 打开 `anonymous_reid_x402_demo.py`。
2. 修改顶部的 `EVM_PRIVATE_KEY` 和 `IMAGE_PATH`。
3. 运行：

```bash
python3 anonymous_reid_x402_demo.py
```

程序会先请求接口获得 HTTP 402 支付信息，签名支付头后重试 `POST /v1/public/features/reid`。

接口输入应是单张人体目标图。
