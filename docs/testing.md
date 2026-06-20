# GaitAgent 部署与测试说明

本文档面向“把当前服务跑到另一台机器上并验证可用”。

当前运行架构：

- `gait-api`: 对外 HTTP 服务，默认监听 `:3005`
- `gait-worker`: 本机后台 worker，唯一调用 SDK 的进程
- API 和 worker 通过本机 Unix Socket 通信：`/run/gaitagent/worker.sock`

## 1. 前置条件

目标机器至少需要满足：

- Linux `amd64`
- Go 已安装
- CUDA 运行库可用
- 已部署 `algorithms/` 目录
- 已插入 SDK 加密狗

仓库内依赖的 SDK 相关目录：

- `algorithms/model_encryption_64`
- `algorithms/lib_core_64`
- `algorithms/lib_64`
- `algorithms/include/opencv4`

说明：

- `gait-worker` 必须使用 `-tags sdk` 编译
- `gait-api` 不应使用 `-tags sdk` 编译，SDK 只应由 worker 进程加载
- `gait-api` 仍依赖 `algorithms/lib_64` 中的 OpenCV/FFmpeg 动态库来探测视频元数据
- 如果机器没有加密狗，二进制可以启动，但真实 SDK 解析会失败

## 2. 构建

在仓库根目录执行：

```bash
export PATH=/usr/local/cuda/bin:$PATH
export ALG_DIR=$PWD/algorithms
export RecognitionSDK_HOME=$PWD/algorithms/model_encryption_64
export LD_LIBRARY_PATH=$PWD/algorithms/lib_core_64:$PWD/algorithms/lib_64:/usr/local/cuda/lib64:/usr/local/lib
export OPENBLAS_NUM_THREADS=1
export GOCACHE=/tmp/go-build

mkdir -p /opt/gaitagent/bin

go build -o /opt/gaitagent/bin/gait-api ./cmd/api
go build -tags sdk -o /opt/gaitagent/bin/gait-worker ./cmd/worker
```

如果只是做接口层单测，不依赖 SDK：

```bash
GOCACHE=/tmp/go-build go test ./...
```

如果要跑带 SDK 的测试或探针：

```bash
PATH=/usr/local/cuda/bin:$PATH \
ALG_DIR=$PWD/algorithms \
RecognitionSDK_HOME=$PWD/algorithms/model_encryption_64 \
LD_LIBRARY_PATH=$PWD/algorithms/lib_core_64:$PWD/algorithms/lib_64:/usr/local/cuda/lib64:/usr/local/lib \
OPENBLAS_NUM_THREADS=1 \
GOCACHE=/tmp/go-build \
go test -tags sdk ./...
```

## 3. 直接运行

先准备目录：

```bash
mkdir -p /data/gaitagent
mkdir -p /run/gaitagent
```

启动 worker：

```bash
PATH=/usr/local/cuda/bin:$PATH \
ALG_DIR=$PWD/algorithms \
RecognitionSDK_HOME=$PWD/algorithms/model_encryption_64 \
LD_LIBRARY_PATH=$PWD/algorithms/lib_core_64:$PWD/algorithms/lib_64:/usr/local/cuda/lib64:/usr/local/lib \
OPENBLAS_NUM_THREADS=1 \
GOCACHE=/tmp/go-build \
GAIT_DATA_DIR=/data/gaitagent \
GAIT_WORKER_SOCKET=/run/gaitagent/worker.sock \
/opt/gaitagent/bin/gait-worker
```

另开一个终端启动 API：

```bash
PATH=/usr/local/cuda/bin:$PATH \
ALG_DIR=$PWD/algorithms \
RecognitionSDK_HOME=$PWD/algorithms/model_encryption_64 \
LD_LIBRARY_PATH=$PWD/algorithms/lib_core_64:$PWD/algorithms/lib_64:/usr/local/cuda/lib64:/usr/local/lib \
OPENBLAS_NUM_THREADS=1 \
GOCACHE=/tmp/go-build \
GAIT_API_ADDR=:3005 \
GAIT_DATA_DIR=/data/gaitagent \
GAIT_WORKER_SOCKET=/run/gaitagent/worker.sock \
/opt/gaitagent/bin/gait-api
```

默认未设置 `GAIT_OBJECT_STORE_ROOT` 时，上传视频、上传序列帧、gait image、face image 等会随任务清理的数据保存在：

```text
/data/gaitagent/objects
```

主要目录包括：

```text
/data/gaitagent/objects/videos/<video_task_id>/...
/data/gaitagent/objects/sequences/<sequence_task_id>/...
/data/gaitagent/objects/video-assets/<video_task_id>/...
/data/gaitagent/objects/sequence-assets/<sequence_task_id>/...
```

长期样本归档目录是 `/data/gaitagent/sequence_samples`，不参与普通任务 TTL 自动清理，需要管理人员自行拷贝或删除。

样本归档命名规则：

```text
/data/gaitagent/sequence_samples/user/<user_id>/<sequence_task_id>/
/data/gaitagent/sequence_samples/user/<user_id>/<video_task_id>/<sequence_id>/
/data/gaitagent/sequence_samples/anonymous/<wallet_or_settlement_hash>/<sequence_task_id>/
/data/gaitagent/sequence_samples/anonymous/<wallet_or_settlement_hash>/<video_task_id>/<sequence_id>/
```

每个目录包含 `frames/`、`metadata.json`、`result.json`。`metadata.json` 会记录注册用户邮箱/API Key 信息/请求 IP/时间，匿名用户钱包地址/网络/代币/请求 IP/时间。目录名不直接使用邮箱、IP 或钱包地址；API Key 只保存前缀和 SHA-256 哈希，不保存完整明文。

健康检查：

```bash
curl http://127.0.0.1:3005/healthz
```

期望返回：

```json
{"service":"gait-api","status":"ok"}
```

## 4. systemd 运行

仓库里已经有模板：

- `deploy/systemd/gait-api.service`
- `deploy/systemd/gait-worker.service`
- `deploy/systemd/gait-api.env`
- `deploy/systemd/gait-worker.env`

安装步骤：

```bash
mkdir -p /etc/gaitagent
cp deploy/systemd/gait-api.env /etc/gaitagent/gait-api.env
cp deploy/systemd/gait-worker.env /etc/gaitagent/gait-worker.env
cp deploy/systemd/gait-api.service /etc/systemd/system/gait-api.service
cp deploy/systemd/gait-worker.service /etc/systemd/system/gait-worker.service

systemctl daemon-reload
systemctl enable gait-worker.service gait-api.service
systemctl restart gait-worker.service gait-api.service
```

查看状态：

```bash
systemctl status gait-worker.service
systemctl status gait-api.service
```

查看日志：

```bash
journalctl -u gait-worker.service -f
journalctl -u gait-api.service -f
```

## 5. SDK 探针

用于先排查“SDK 初始化是否正常”，不走 HTTP 服务。

序列探针：

```bash
PATH=/usr/local/cuda/bin:$PATH \
ALG_DIR=$PWD/algorithms \
RecognitionSDK_HOME=$PWD/algorithms/model_encryption_64 \
LD_LIBRARY_PATH=$PWD/algorithms/lib_core_64:$PWD/algorithms/lib_64:/usr/local/cuda/lib64:/usr/local/lib \
OPENBLAS_NUM_THREADS=1 \
GOCACHE=/tmp/go-build \
go run -tags sdk ./cmd/sdkprobe
```

默认读取：

```text
data/image/seq0/*.jpg
```

视频探针：

```bash
PATH=/usr/local/cuda/bin:$PATH \
ALG_DIR=$PWD/algorithms \
RecognitionSDK_HOME=$PWD/algorithms/model_encryption_64 \
LD_LIBRARY_PATH=$PWD/algorithms/lib_core_64:$PWD/algorithms/lib_64:/usr/local/cuda/lib64:/usr/local/lib \
OPENBLAS_NUM_THREADS=1 \
GOCACHE=/tmp/go-build \
go run -tags sdk ./cmd/videoprobe ./data/video/test.mp4
```

## 6. HTTP Demo 与示例脚本

当前 HTTP Demo 统一放在 [examples](/home/watrix/tiandk/agent/gaitAgent/examples) 下，按调用者类型区分：

- [examples/registered](/home/watrix/tiandk/agent/gaitAgent/examples/registered)：注册用户，使用 `Authorization: Bearer <api_key>` 调用私有接口。
- [examples/anonymous](/home/watrix/tiandk/agent/gaitAgent/examples/anonymous)：匿名 Agent，使用 public 接口并通过 x402 完成付款。

页面下载入口：

- 用户门户：`https://www.w-agent.cn/portal`
- 注册用户全部 Demo：`/portal/demo-download?type=registered`
- 注册用户 Python Demo：`/portal/demo-download?type=registered-python`
- 注册用户 C++ Demo：`/portal/demo-download?type=cpp`
- 注册用户 Go Demo：`/portal/demo-download?type=go`
- 匿名 x402 全部 Demo：`/portal/demo-download?type=anonymous`
- 匿名 x402 Python Demo：`/portal/demo-download?type=anonymous-python`
- 试用全部 Demo：`/portal/demo-download?type=trial`
- 试用 Browser Demo：`/portal/demo-download?type=browser`，直接返回 HTML 文件，不打 zip。

每个语言包按三类输入组织：

- 输入序列：上传已经跟踪好的人形图片序列到 Sequence API。
- 输入视频：直接上传完整视频到 Video API。
- 本地视频转序列：先在本地从视频抽取人员序列，再上传序列到 Sequence API。

### 6.1 注册用户 Python 序列与视频 API Demo

```bash
python3 examples/registered/python/sequence_and_video_api_demo.py
```

默认配置：

- API 地址：`https://www.w-agent.cn/api`
- API Key：写在脚本顶部，调用 `/v1/sequences` 和 `/v1/videos`
- 序列目录：`examples/sample_sequences`
- 视频目录：`examples/video`
- 输出目录：`tmp/registered_batch_results`

脚本行为：

- 递归扫描 `examples/sample_sequences` 下所有“最末级图片目录”，每个目录作为一个序列。
- 递归扫描 `examples/video` 下所有视频文件。
- 保存每个接口返回的完整 JSON。
- 对序列结果计算 `gait_feature`、`reid_feature`、`face_feature` 的两两点积相似度。
- 对每个视频内部的所有序列计算特征相似度。
- 如果 SDK 返回 `emotions`，这些字段会原样保存在 Demo 输出 JSON 中。`pose_2ds` 和 `pose_3ds` 只由独立的 `gait-pose` 接口返回。

本地视频转序列后上传：

```bash
python3 examples/registered/python/local_video_to_sequence_demo/local_video_to_sequence_api_demo.py /path/to/video.mp4
```

### 6.2 注册用户 Go Demo

```bash
cd examples/registered/go/sequence_demo
./build.sh
./registered_sequence_demo
```

```bash
cd examples/registered/go/video_demo
./build.sh
./registered_video_demo
```

Go Demo 不依赖第三方包，适合给客户快速参考接口调用方式。

本地视频转序列后上传：

```bash
./examples/registered/go/local_video_to_sequence_demo/run_local_video_to_sequence_api_demo.sh /path/to/video.mp4
```

### 6.3 注册用户 C++ Demo

先安装依赖：

```bash
sudo apt-get install -y libcurl4-openssl-dev nlohmann-json3-dev
```

序列 Demo：

```bash
cd examples/registered/cpp/sequence_demo
./build.sh
./build/registered_sequence_demo
```

视频 Demo：

```bash
cd examples/registered/cpp/video_demo
./build.sh
./build/registered_video_demo
```

C++ Demo 使用 CMake 编译，分别演示序列和视频的独立调用。

本地视频转序列后上传：

```bash
./examples/registered/cpp/local_video_to_sequence_demo/run_local_video_to_sequence_api_demo.sh /path/to/video.mp4
```

### 6.4 匿名 x402 Python Demo

匿名调用不使用 API Key。服务端先返回 `402 Payment Required`，客户端读取 `payment_context.challenge.accepts`，选择可支付的网络和币种，签名 x402 payment payload 后重试同一个接口。

安装依赖：

```bash
pip install requests eth-account 'x402[evm]' web3
```

序列与视频 x402 Demo：

```bash
python3 examples/anonymous/python/anonymous_sequence_and_video_x402_demo.py
```

单序列最小 Demo：

```bash
python3 examples/anonymous/python/anonymous_sequence_x402_demo.py
```

本地视频转序列后匿名上传：

```bash
python3 examples/anonymous/python/local_video_to_sequence_demo/local_video_to_sequence_x402_demo.py /path/to/video.mp4
```

### 6.5 浏览器试用客户端

当前浏览器客户端是纯 HTML/JS，无需安装 Python 或 Node.js。它支持免注册试用和注册用户 API Key 两种身份，当前可调用图搜万物、步态序列解析和人体关节点接口，其中人体关节点是独立的 `gait-pose` 接口。

```bash
curl -fsS "http://127.0.0.1:3006/portal/demo-download?type=browser" -o w-agent-browser-client.html
open w-agent-browser-client.html
```

浏览器版视频本地检测、跟踪、转序列还需要 WASM detector/tracker 包，尚未包含在该轻量客户端中。

当前匿名 x402 支持的生产路线：

| 网络 | 币种 | 方式 |
|---|---|---|
| Base Mainnet | USDC | EIP-3009 |
| Polygon Mainnet | USDC | EIP-3009 |
| Arbitrum One | USDC | EIP-3009 |
| Base Mainnet | USDT | Permit2 |
| Polygon Mainnet | USDT | Permit2 |
| Arbitrum One | USDT | Permit2 |
| Base Mainnet | EURC | EIP-3009 |

说明：

- USDC 和 EURC 路线通常不需要用户先做 ERC20 approve。
- USDT 路线走 Permit2，首次使用某个网络上的 USDT 时可能需要 allowance。
- 具体可用路线以 `GET /v1/payment-capabilities` 和 402 响应里的 `accepts` 为准。

## 7. 上传你自己的测试数据

### 序列图片

- 注册用户批量 Demo 默认读取 `examples/sample_sequences`。
- 匿名批量 Demo 默认读取 `examples/sample_sequences`。
- 目录可以有多级，最末级且包含图片文件的目录会被当成一个序列。

### 视频

支持各种视频格式，前提是当前机器上的 OpenCV/FFmpeg 能正常打开。

- 注册用户批量 Demo 默认读取 `examples/video`。
- 匿名批量 Demo 默认读取 `examples/video`。
- 子目录会被递归扫描。

## 8. 常见排查

### 8.1 `/healthz` 正常，但解析失败

先看 worker 日志：

```bash
journalctl -u gait-worker.service -n 200 --no-pager
```

常见原因：

- 没插加密狗
- `RecognitionSDK_HOME` 不对
- `LD_LIBRARY_PATH` 缺库
- CUDA 运行库不完整

### 8.2 API 正常，序列接口卡住或失败

检查 worker 内部 socket：

```bash
ls -l /run/gaitagent/worker.sock
```

如果不存在，说明 worker 没起来，或者 worker 启动失败。

### 8.3 换目录后编不过

当前代码已经把 OpenCV 头文件和库路径改成仓库相对路径，但前提仍然是仓库内存在：

- `algorithms/include/opencv4`
- `algorithms/lib_64`

### 8.4 视频结果还没好

`GET /v1/public/videos/{task_id}/result` 在结果未就绪时会返回：

- HTTP `409`
- `code = result_not_ready`

先轮询：

- `GET /v1/public/videos/{task_id}`

等 `status` 到 `succeeded_awaiting_payment_2` 再取结果。

## 9. 当前已知行为

- `face_image` 可能为空，这是正常情况
- 图片序列模式下，`image_ids/rects` 为空或为 0 是正常的；这种情况下 Sequence API 返回 `frames: []`、`frame_count: 0`，不会回退成输入图片数量
- 视频模式下，理论上 `image_ids/rects` 应该更完整，但这部分是否完整仍受 SDK 实际输出影响
- 视频上传后会自动进入解析，不需要再调用 `complete`
