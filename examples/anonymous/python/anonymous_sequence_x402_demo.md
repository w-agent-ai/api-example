# Public Sequence x402 Demo

这个 demo 用于测试匿名 `public sequence` 接口的真实 `x402` 付款流程。

## 依赖

推荐 Python 3.10+。

安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests eth-account 'x402[evm]'
```

## 准备

1. 打开脚本顶部配置区，直接填写：

- `EVM_PRIVATE_KEY`
- `BASE_URL`
- `SEQ_DIR`
- `TIMEOUT`

2. 准备一个序列图片目录，例如：

```bash
mkdir -p ./seq
cp /path/to/your/images/* ./seq/
```

## 运行

```bash
python3 examples/anonymous/python/anonymous_sequence_x402_demo.py
```

## 预期

脚本会：

1. 创建 `/v1/public/sequences`
2. 上传图片
3. 先请求一次 `/parse`，打印服务端当前返回的 `accepts`
   会显示每条 `accept` 的网络、币种、支付方法（`eip3009` 或 `permit2`）
4. 自动处理 `402 Payment Required`
5. 完成 `x402` 付款并重试
6. 输出解析结果

## 注意

- 付款钱包和服务端收款钱包不要使用同一个地址。
- 付款钱包需要在服务端当前返回的某一条 `accept` 对应网络上持有对应资产。
- 目前本项目线上已开放的 `accepts` 为：
  - `Base Mainnet / USDC / EIP-3009`
  - `Polygon Mainnet / USDC / EIP-3009`
  - `Arbitrum One / USDC / EIP-3009`
  - `Base Mainnet / USDT / Permit2`
  - `Polygon Mainnet / USDT / Permit2`
  - `Arbitrum One / USDT / Permit2`
  - `Base Mainnet / EURC / EIP-3009`
- `USDC` 路线当前走 `EIP-3009`。
- `USDT` 路线当前走 `Permit2`。首次使用该网络/该币种时，如果钱包还没有对 `Permit2` 做过 allowance，可能会看到一次额外授权相关动作。
- `EURC` 金额不是单独定价，而是把订单的美元金额按服务端当前汇率换算。
- 当前默认汇率为 `1 EUR = 1.15 USD`，后续可在管理后台调整。
- 示例脚本不再内置真实私钥。请自行填写测试私钥，并在测试完成后及时轮换。
- 付款失败时，保留脚本完整输出、调用时间、钱包地址、交易哈希，方便排查。
