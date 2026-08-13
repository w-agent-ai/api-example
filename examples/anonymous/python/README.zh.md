# 匿名 x402 Python 示例

这些示例用于不注册账号、通过 x402 自动支付后调用 W-Agent public API。

## 准备环境

```bash
pip install requests eth-account web3 'x402[evm]'
```

## 通用配置

打开对应的 `.py` 文件，直接修改顶部配置：

- `EVM_PRIVATE_KEY`：付款钱包私钥，用于签名 x402 支付挑战。
- `BASE_URL`：API 地址，官网默认是 `https://www.w-agent.cn/api`。
- `IMAGE_PATH` 或 `SEQ_DIR`：本地输入图片或序列目录。

示例代码里已经写了关键注释，用户可以直接看代码理解每一步。

## 示例列表

### 图搜万物

```bash
python3 anonymous_object_search_x402_demo.py
```

输入一张图片和文字描述，调用 `POST /v1/public/object-search`，返回匹配目标框。

### 人脸识别

```bash
python3 anonymous_face_x402_demo.py
```

输入一张已经检测并矫正好的人脸图片，调用 `POST /v1/public/features/face`，返回 512 维人脸特征。

### ReID 识别

```bash
python3 anonymous_reid_x402_demo.py
```

输入一张单个人体目标图，调用 `POST /v1/public/features/reid`，返回 512 维 ReID 特征。

### 步态识别

```bash
python3 anonymous_sequence_x402_demo.py
```

输入一个已经跟踪好的人体序列目录，批量上传帧图片，调用 `POST /v1/public/sequences/{task_id}/parse`。

### 人体 2D/3D 关节点

```bash
python3 anonymous_gait_pose_x402_demo.py
```

输入一个已经跟踪好的人体序列目录，批量上传帧图片，调用 `POST /v1/public/sequences/{task_id}/gait-pose`。

## x402 调用流程

代码里的 `x402_requests(client)` 会自动处理支付流程：

1. 第一次请求 public API。
2. 服务端返回 HTTP 402 和 `payment_context.challenge`。
3. x402 客户端用 `EVM_PRIVATE_KEY` 对挑战签名。
4. 自动重试同一个请求，并带上 `PAYMENT-SIGNATURE`。
5. 服务端验签和结算成功后返回算法结果。
