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
/data/gaitagent/sequence_samples/<YYYY-MM-DD>/user/<user_id>/<sequence_task_id>/
/data/gaitagent/sequence_samples/<YYYY-MM-DD>/user/<user_id>/<video_task_id>/<sequence_id>/
/data/gaitagent/sequence_samples/<YYYY-MM-DD>/anonymous/<wallet_or_settlement_hash>/<sequence_task_id>/
/data/gaitagent/sequence_samples/<YYYY-MM-DD>/anonymous/<wallet_or_settlement_hash>/<video_task_id>/<sequence_id>/
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

## 7. 使用记录大数据压测

`cmd/usagebench` 用于直接压测 `usage_records` 分区写入、幂等去重、日汇总和典型查询性能，不经过算法 SDK 和 HTTP 层。

它有两种模式：

- `-mode=store`：默认模式，走 `usageledger.Store` 真实写入路径，适合测线上追加写入吞吐和幂等逻辑。
- `-mode=sql-generate`：使用 SQL 批量生成历史明细，适合快速模拟一个月大数据后查询和报表性能；它不代表业务实时写入路径。

先确认已执行数据库迁移：

```bash
set -a
source /etc/gaitagent/gait-api.env
set +a
go run ./cmd/migrate
```

小规模冒烟：

```bash
set -a
source /etc/gaitagent/gait-api.env
set +a
go run ./cmd/usagebench -n 10000 -workers 4 -batch 1000 -cleanup=true
```

按真实业务写入路径模拟一天百万条：

```bash
set -a
source /etc/gaitagent/gait-api.env
set +a
go run ./cmd/usagebench -mode=store -n 1000000 -workers 16 -batch 50000 -day 2026-07-01 -cleanup=true
```

快速生成 30 天共 3000 万条历史明细，用于测试一个月后查询、运营看板和周报/月报：

```bash
set -a
source /etc/gaitagent/gait-api.env
set +a
PGOPTIONS='-c jit=off' go run ./cmd/usagebench -mode=sql-generate -n 30000000 -days 30 -chunk 200000 -batch 1000000 -day 2026-07-01 -cleanup=false
```

如果只想先验证 SQL 批量模式是否正常，可以跑 100 万条：

```bash
set -a
source /etc/gaitagent/gait-api.env
set +a
PGOPTIONS='-c jit=off' go run ./cmd/usagebench -mode=sql-generate -n 1000000 -days 30 -chunk 100000 -batch 1000000 -day 2026-07-01 -cleanup=true
```

关注输出：

- `rate=... rows/s`：写入吞吐。
- `failed=0`：应为 0。
- `query="reason day group"`：按天、算法聚合查询耗时。
- `query="user recent"`：按用户近期明细查询耗时。
- `query="summary day"`：日报汇总查询耗时。

压测会写入 `use_bench_...` 前缀的测试记录。默认 `-cleanup=true` 会删除本次明细、去重键，并把本次写入从 `daily_usage_summary` 中扣回。若要保留压测数据用于 EXPLAIN、运营看板或报表手工分析，可设置 `-cleanup=false`。

### 7.1 重建 usage 汇总表

`cmd/rebuild-usage-summary` 用于从 `usage_records` 明细重建小汇总表，适合排查或修复汇总异常时使用。它按 UTC 日期范围处理：

- `daily_usage_summary`
- `daily_api_key_usage_summary`
- `daily_monthly_usage_summary`
- `daily_public_identity_summary`

默认是 dry-run，会在事务里删除并重算目标日期范围，然后回滚，只输出 before/after 统计：

```bash
set -a
source /etc/gaitagent/gait-api.env
set +a
go run ./cmd/rebuild-usage-summary \
  --start 2026-07-01 \
  --end 2026-07-31
```

确认统计符合预期后再加 `--execute` 真正提交：

```bash
set -a
source /etc/gaitagent/gait-api.env
set +a
go run ./cmd/rebuild-usage-summary \
  --start 2026-07-01 \
  --end 2026-07-31 \
  --execute
```

`--start` 和 `--end` 都是包含当天的 UTC 日期。工具只重建汇总表，不修改 `usage_records` 明细和 `usage_record_keys` 幂等键。

### 7.2 15 个月业务数据性能种子

`cmd/perfseed` 用于重建一批接近真实业务形态的 15 个月性能测试数据，从 2025-05-01 开始，按月增长到约 19 万注册用户，并生成充值、钱包流水、套餐、使用记录和各类日汇总。它会走数据库批量写入，适合验证管理后台用户列表、财务页、运营看板和大表索引表现。

```bash
set -a
source /etc/gaitagent/gait-api.env
set +a
go run ./cmd/perfseed -reset=true -report tmp/perfseed_report.json
```

模拟用户写入 `account_users` 时使用 `metadata_json={"dataset":"perf_15m"}`。联系方式生成规则：

- 手机号参考真实国内手机号形态，使用 `132/135/136/137/138/139/153/155/156/157/158/159/176/177/180/181/182/183/185/187/188/189/191/192/199` 等常见号段。
- 邮箱使用常见域名，包含 `qq.com`、`163.com`、`126.com`、`yeah.net`、`sina.com`、`sohu.com`、`outlook.com`。
- 模拟用户不强制同时有手机号和邮箱，约一部分同时填写，部分仅手机号，部分仅邮箱；空联系方式写入数据库 `NULL`，避免空字符串触发唯一索引冲突。
- 所有生成的手机号和邮箱都保持唯一，便于管理后台按手机号、邮箱或用户 ID 做服务端搜索。

线上容量规划建议：

- 100 万条/天按当前字段和索引，保守估算约 `1-2GB/天`
- 3000 万条/月约 `30-60GB/月`
- 3.65 亿条/年建议按 `700GB-1TB` 预留，包含索引、膨胀和维护空间
- 在线库和归档 PostgreSQL 库通过环境变量配置；机器磁盘路径不要放到后台数据库运行配置里

如果 PostgreSQL 缺少 LLVM/JIT 运行库，大查询可能报：

```text
could not load library ".../llvmjit.so": libLLVM-*.so.*: cannot open shared object file
```

压测命令建议带 `PGOPTIONS='-c jit=off'`。生产库也可以对业务角色设置：

```sql
ALTER ROLE gaitagent SET jit = off;
```

### 7.3 使用记录归档测试

其它机器上线时，推荐把归档库放到机械盘或大容量盘的 PostgreSQL tablespace。假设机械盘目录是 `/data`：

```bash
sudo install -d -m 0700 -o postgres -g postgres /data/postgresql/tablespaces/gaitagent_archive

sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
  "CREATE TABLESPACE gaitagent_archive_ts LOCATION '/data/postgresql/tablespaces/gaitagent_archive';"

sudo -u postgres createdb -O gaitagent -T template0 -D gaitagent_archive_ts gaitagent_archive
```

配置 `/etc/gaitagent/gait-api.env`：

```env
GAIT_USAGE_ARCHIVE_ENABLED=true
GAIT_USAGE_ARCHIVE_DSN=postgres://gaitagent:<password>@127.0.0.1:5432/gaitagent_archive?sslmode=disable
GAIT_USAGE_ONLINE_RETENTION_MONTHS=3
```

先验证归档库能连接：

```bash
set -a
source /etc/gaitagent/gait-api.env
set +a
PGOPTIONS='-c jit=off' psql "$GAIT_USAGE_ARCHIVE_DSN" -c "SELECT current_database(), current_user;"
```

当前测试机已使用：

```text
tablespace: gaitagent_archive_ts
path: /data/postgresql/tablespaces/gaitagent_archive
database: gaitagent_archive
enabled: true
```

归档按月执行，不按天执行。手动 dry-run：

```bash
set -a
source /etc/gaitagent/gait-api.env
set +a
PGOPTIONS='-c jit=off' go run ./cmd/usagearchive -dry-run
```

确认命中的分区正确后执行：

```bash
set -a
source /etc/gaitagent/gait-api.env
set +a
PGOPTIONS='-c jit=off' go run ./cmd/usagearchive -execute
```

也可以临时指定归档库 DSN 和保留月数：

```bash
PGOPTIONS='-c jit=off' go run ./cmd/usagearchive \
  -execute \
  -archive-dsn 'postgres://gaitagent:***@127.0.0.1:5432/gaitagent_archive?sslmode=disable' \
  -retention-months 3
```

归档后检查：

```sql
-- 在线库：旧月明细和幂等键应已删除，日汇总保留
SELECT COUNT(*)
FROM usage_records
WHERE created_at >= '2025-06-01'
  AND created_at < '2025-07-01';

SELECT COUNT(*), COALESCE(SUM(call_count), 0)
FROM daily_usage_summary
WHERE usage_date >= '2025-06-01'
  AND usage_date < '2025-07-01';

-- 归档库：旧月明细可直接 SQL 查询
SELECT COUNT(*) FROM usage_records_2025_06;
SELECT partition_name, row_count, retained_key_count
FROM usage_archive_manifests
WHERE partition_name = 'usage_records_2025_06';
```

2026-07-02 在当前测试机上，生成 2025-06 单月 1 万条并归档到 PostgreSQL 归档库的验证结果：

- 在线库 `usage_records_2025_06` 分区已删除
- 在线库 2025-06 明细为 0
- 在线库对应 `usage_record_keys` 保留 1 万条幂等键
- 在线库 `daily_usage_summary` 保留 12 行，合计 1 万次调用
- 归档库 `usage_records_2025_06` 有 1 万条，可直接 SQL 查询
- 归档库 `usage_archive_manifests` 记录 `row_count=10000`、`retained_key_count=10000`

2026-07-02 在当前测试机上，生成 2025-07 单月 3000 万条并归档到 PostgreSQL 归档库的参考结果：

- SQL 批量造数：`30000000` 条，约 `1h05m56s`，平均约 `7583 rows/s`
- 明细 count 查询：约 `20.36s`
- 按天/算法聚合查询：约 `5.99s`
- 按用户近期明细查询：约 `3.36ms`
- `daily_usage_summary` 查询：约 `1ms`
- 本次归档库方案 SQL 批量造数：`30000000` 条，约 `1h04m06s`，平均约 `7799 rows/s`
- 本次归档前明细 count 查询：约 `16.81s`
- 本次归档前按天/算法聚合查询：约 `4.77s`
- 本次归档前按用户近期明细查询：约 `4.66ms`
- 本次归档到 PostgreSQL 归档库：约 `19m`
- 归档库 `usage_records_2025_07`：`30000000` 条
- 归档库 `usage_archive_manifests`：`row_count=30000000`、`retained_key_count=30000000`
- 归档后在线明细为 0，幂等键保留 3000 万条，`daily_usage_summary` 保留 360 行、合计 3000 万次调用
- 归档月表带索引后大小约 `19GB`
- 归档月表未建索引时，按 `user_public_id` 查询约 `4.43s`；补齐索引并 `ANALYZE` 后约 `45ms`

当前 HTTP Demo 统一放在 [examples](/home/watrix/tiandk/agent/gaitAgent/examples) 下，按调用者类型区分：

- [examples/registered](/home/watrix/tiandk/agent/gaitAgent/examples/registered)：注册用户，使用 `Authorization: Bearer <api_key>` 调用私有接口。
- [examples/anonymous](/home/watrix/tiandk/agent/gaitAgent/examples/anonymous)：匿名 Agent，使用 public 接口并通过 x402 完成付款。

页面资源下载入口：

- 用户门户：`https://www.w-agent.cn/portal`
- 页面按“API 示例”和“客户端”拆成两个表格展示；客户端支持接入实时摄像头。客户端文件名较长时在单元格内换行，不使用横向滚动条。
- 图搜万物 API Key Python：`/portal/demo-download?type=object-search-api-key-python`
- 人体 2D/3D 关节点 API Key Python/C++/Go：`type=pose-api-key-python`、`type=pose-api-key-cpp`、`type=pose-api-key-go`
- 步态识别 API Key Python/C++/Go：`type=gait-api-key-python`、`type=gait-api-key-cpp`、`type=gait-api-key-go`
- 图搜万物 X402 Python：`/portal/demo-download?type=object-search-x402-python`
- 人体 2D/3D 关节点 X402 Python：`/portal/demo-download?type=pose-x402-python`
- 步态识别 X402 Python：`/portal/demo-download?type=gait-x402-python`
- 图搜万物编译客户端：`type=object-search-client-windows`、`type=object-search-client-mac`
- 人体关节点编译客户端：`type=pose-client-windows`、`type=pose-client-mac`
- 步态识别编译客户端：`type=gait-client-windows`、`type=gait-client-mac`

编译客户端文件由运维上传到服务端固定目录。接口会返回对应目录下第一个非隐藏普通文件；目录为空时返回
`404 client_binary_unavailable`。资源下载页每次请求 `/portal` 时检查这些目录：没有文件显示 `-`，有文件时显示真实文件名。上传或替换二进制后刷新页面即可看到最新状态。

- 图搜万物 Windows：`/data/gaitagent/resource_downloads/clients/object-search/windows/`
- 图搜万物 Mac：`/data/gaitagent/resource_downloads/clients/object-search/mac/`
- 人体关节点 Windows：`/data/gaitagent/resource_downloads/clients/pose/windows/`
- 人体关节点 Mac：`/data/gaitagent/resource_downloads/clients/pose/mac/`
- 步态识别 Windows：`/data/gaitagent/resource_downloads/clients/gait/windows/`
- 步态识别 Mac：`/data/gaitagent/resource_downloads/clients/gait/mac/`

每个语言包按两类输入组织：

- 输入序列：上传已经跟踪好的人形图片序列到 Sequence API。
- 本地视频转序列：先在本地从视频抽取人员序列，再上传序列到 Sequence API。

### 6.1 注册用户 Python 序列 API Demo

```bash
python3 examples/registered/python/gait_sequence_api_demo.py
```

默认配置：

- API 地址：`https://www.w-agent.cn/api`
- API Key：写在脚本顶部，调用 `/v1/sequences`
- 序列目录：`examples/seqs`
- 视频目录：`examples/video`
- 输出目录：`tmp/registered_batch_results`

脚本行为：

- 递归扫描 `examples/seqs` 下所有“最末级图片目录”，每个目录作为一个序列。
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
go build -o registered_sequence_demo main.go
./registered_sequence_demo
```

```bash
cd examples/registered/go/video_demo
go build -o registered_video_demo main.go
./registered_video_demo
```

Go Demo 不依赖第三方包，适合给客户快速参考接口调用方式。

本地视频输入示例包内不再使用 shell 脚本或环境变量。下载 Go 资源包后，修改源码顶部的 `apiKey`、`videoPath`，然后编译运行：

```bash
cd local_video_to_sequence_demo
cmake -S cpp_detector -B cpp_detector/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp_detector/build -j
go build -o local_video_api_demo main.go
./local_video_api_demo /path/to/video.mp4
```

### 6.3 注册用户 C++ Demo

先安装依赖：

```bash
sudo apt-get install -y libcurl4-openssl-dev nlohmann-json3-dev
```

序列 Demo：

```bash
cd examples/registered/cpp/sequence_demo
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/registered_sequence_demo
```

视频 Demo：

```bash
cd examples/registered/cpp/video_demo
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/registered_video_demo
```

C++ Demo 使用 CMake 编译，分别演示序列和视频的独立调用。

本地视频输入示例包内不再使用 shell 脚本或环境变量。下载 C++ 资源包后，修改 `local_video_api_demo.cpp` 顶部的 `kAPIKey`、`kVideoPath`，然后编译运行：

```bash
cd local_video_to_sequence_demo
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/local_video_to_gait_api_demo /path/to/video.mp4
```

### 6.4 匿名 x402 Python Demo

匿名调用不使用 API Key。服务端先返回 `402 Payment Required`，客户端读取 `payment_context.challenge.accepts`，选择可支付的网络和币种，签名 x402 payment payload 后重试同一个接口。

安装依赖：

```bash
pip install requests eth-account 'x402[evm]' web3
```

图搜万物 x402 Demo：

```bash
python3 examples/anonymous/python/anonymous_object_search_x402_demo.py
```

人体 2D/3D 关节点 x402 Demo：

```bash
python3 examples/anonymous/python/anonymous_gait_pose_x402_demo.py
```

步态识别单序列 x402 Demo：

```bash
python3 examples/anonymous/python/anonymous_sequence_x402_demo.py
```

本地视频转序列后匿名上传：

```bash
python3 examples/anonymous/python/local_video_to_sequence_demo/local_video_to_sequence_x402_demo.py /path/to/video.mp4
```

### 6.5 在线浏览器客户端

当前浏览器客户端是纯 HTML/JS，无需安装 Python 或 Node.js。官网首页“人体2D/3D关节点”和“步态识别”按钮会在新页面打开对应在线客户端：双视频步态识别和人体 3D 关节点，其中人体关节点是独立的 `gait-pose` 接口。图搜万物直接在官网首页 playground 体验，不提供浏览器客户端下载。通过 `open=1` 在线打开时，HTML 会内嵌浏览器端 `persondet` 主逻辑和 WASM detector，但不会内嵌较大的 JS fallback 权重，避免浏览器在 WASM 可用时仍解析备用权重导致启动变慢。不带 `open=1` 的兼容下载响应会保留 JS fallback 权重。

通过 `/portal/demo-download?type=browser-pose&open=1` 或 `/portal/demo-download?type=browser-gait&open=1` 打开的在线客户端不展示 API Key 输入。已登录用户会先用当前登录 session 读取 `/v1/me` 和 `/v1/me/api-keys`，自动选择 default 或第一个 active API Key 发起注册用户调用；未登录用户走免费试用接口。试用额度不足时提示登录后使用。客户端右上角未登录时显示“登录”，已登录时显示当前账号（优先邮箱，其次手机号、姓名和用户 ID）。

资源下载页的“客户端”列不是网页客户端，而是编译好的 Windows/Mac 二进制客户端，下载类型为
`object-search-client-windows`、`object-search-client-mac`、`pose-client-windows`、`pose-client-mac`、`gait-client-windows`、`gait-client-mac`。

资源下载页的示例包链接显示 zip 文件名，不再显示统一的“下载”。示例包内部使用浅层目录：顶层目录是 zip 文件名去掉 `.zip`，例如 `gait-api-key-python/`；单算法包在根目录同时包含英文 `README.md` 和中文 `README.zh.md`，并且只说明当前算法，不混入其他算法的通用说明。功能子目录如果有独立使用入口，也同时提供中英文 README。步态识别和人体关节点的视频检测、跟踪、生成序列入口放在 Python ONNX Runtime 示例包和 C++ CPU ONNX Runtime 示例包里，Go 单算法包只保留已有序列图片直接调用 API 的示例。

单算法包文档说明：

- 已有序列图片：进入 `sequence_demo/` 或 `gait_pose_demo/`，修改 API Key 和序列目录后编译运行。
- 输入视频：C++ 包进入 `local_video_to_sequence_demo/`，使用包内 Linux x64 CPU ONNX Runtime 和 `gait_detect.onnx` 本地检测、跟踪并调用 API；Go 包先使用 Python/C++ 本地视频转序列示例生成序列图片，再用 Go 示例调用对应 API。

在线客户端左侧上传区域下方会展示服务端预生成的示例视频：人体关节点示例使用 `/portal/examples/pose-demo/manifest.json` 中的 source video、序列抓拍、pose JSON 和 2D/3D 视频；步态识别示例使用 `/portal/examples/gait-demo/manifest.json` 中的视频1/视频2示例、序列抓拍和预提取 feature。用户点击示例视频可直接查看序列、播放关节点结果或进行相似度比对；上传自有视频时仍走浏览器本地解析和 API 调用流程。

注册用户余额不足时，图搜万物、人体关节点和步态识别都会弹出居中的“余额不足”提示，并提供跳转到充值页的链接。人体关节点余额不足不会把失败序列显示成空结果：如果已有成功结果则回退到上一条，否则清空 2D/3D 展示区。步态识别余额不足会保留抓拍卡片并显示“api调用失败”，不删除序列；用户充值后再次点击比对会重新尝试提取失败序列的特征。

浏览器客户端、Python 本地视频 demo 和 C++ 本地视频 demo 的 person detector 统一使用 `gait_detect.onnx`。浏览器端通过官方 `onnxruntime-web` WASM 推理，Python 示例通过 `onnxruntime` CPU 推理，C++ 示例通过包内 Linux x64 CPU ONNX Runtime 推理；人体关节点和步态识别的视频转序列流程都走同一个 ONNX 检测器。

生产环境替换检测模型时，只更新部署资源目录，默认路径是 `/opt/gaitagent/portal/resources`，也可通过 `GAIT_PORTAL_RESOURCES_DIR` 覆盖。需要同时替换：

- `/opt/gaitagent/portal/resources/examples/browser/client/gait_detect.onnx`
- `/opt/gaitagent/portal/resources/examples/registered/python/local_video_to_sequence_demo/gait_detect.onnx`
- `/opt/gaitagent/portal/resources/examples/anonymous/python/local_video_to_sequence_demo/gait_detect.onnx`
- `/opt/gaitagent/portal/resources/examples/registered/cpp/local_video_to_sequence_demo/gait_detect.onnx`

服务端在线客户端资源和资源下载包都会优先读取上述部署目录；代码目录下的 `examples/.../gait_detect.onnx` 只是开发环境和部署目录缺失时的 fallback 副本，不作为生产替换入口。替换后无需重启 `gait-api`，下一次请求 `/portal/browser-assets/gait_detect.onnx` 或资源下载 zip 时会读取新的部署目录文件。旧的 `persondet_weights.js` 和 `persondet_wasm.*` 只作为浏览器兼容 fallback，不再作为主路径。当前默认检测参数为 `score_threshold = 0.35`、`nms_threshold = 0.50`。

```bash
curl -fsS "http://127.0.0.1:3006/portal/demo-download?type=browser-pose" -o w-agent-pose-browser-client.html
curl -fsS "http://127.0.0.1:3006/portal/demo-download?type=browser-gait" -o w-agent-gait-browser-client.html
open w-agent-pose-browser-client.html
open w-agent-gait-browser-client.html
```

浏览器客户端会在本地做视频解码、检测、跟踪和序列裁剪。语言选择器可在中文和英文之间切换，无需刷新页面。

### 6.6 首页示例结果生成 Smoke

首页人体关节点和步态识别示例由 `cmd/portal-demo-generator` 从原视频生成静态资源。构建：

```bash
source /home/watrix/tiandk/agent/gaitAgent/algorithms/env.sh
go build -tags sdk -o /tmp/portal-demo-generator ./cmd/portal-demo-generator
```

使用真实 SDK 视频生成：

```bash
source /home/watrix/tiandk/agent/gaitAgent/algorithms/env.sh
/tmp/portal-demo-generator \
  --pose-video /path/to/pose.mp4 \
  --gait-video1 /path/to/video1.mp4 \
  --gait-video2 /path/to/video2.mp4 \
  --out /opt/gaitagent/portal/examples
```

如果首页步态识别需要多组视频1和视频2示例，使用目录模式：

```bash
/tmp/portal-demo-generator \
  --gait-video1-dir /path/to/video1-examples \
  --gait-video2-dir /path/to/video2-examples \
  --out /opt/gaitagent/portal/examples \
  --data-dir /opt/gaitagent/portal/demo-generator-work \
  --max-gait-sequences 0 \
  --timeout 30m \
  --poll 2s
```

生成后确认 `gait-demo/manifest.json` 中包含 `video1_examples`、
`video2_examples`，并且 `comparisons` 中有 `left_video_id` 和
`right_video_id`。首页 demo 会让用户分别选择视频1、视频2示例；比对后只显示
当前视频组合和当前视频1序列对应的相似度。

如果首页人体关节点需要多个示例视频，使用目录模式：

```bash
/tmp/portal-demo-generator \
  --pose-video-dir /path/to/pose-videos \
  --frame-extractor /opt/gaitagent/bin/portal-frame-extractor \
  --out /opt/gaitagent/portal/examples \
  --data-dir /opt/gaitagent/portal/demo-generator-work \
  --max-pose-sequences 6 \
  --max-pose-frames 0 \
  --fps 30 \
  --timeout 30m \
  --poll 2s
```

目录模式会直接从源视频抽帧生成关节点示例序列，避免健身、站姿等静止动作被“有效步态”过滤掉。`--max-pose-frames 0` 表示全帧抽取，不跳帧；`--fps 30` 表示合成的 2D/3D 关节点视频按 30fps 写出。生成后的首页人体关节点 demo 会先展示示例视频列表；选择视频后展示该视频的人体序列抓拍；选择抓拍后展示对应的 2D/3D 关节点结果。

生成后检查：

```bash
curl -fsS http://127.0.0.1:3006/portal/examples/pose-demo/manifest.json
curl -fsS http://127.0.0.1:3006/portal/examples/gait-demo/manifest.json
curl -fsS http://127.0.0.1:3006/portal/examples/pose-demo/sequences/seq-001/pose-2d.mp4 -o /tmp/pose-2d.mp4
curl -fsS http://127.0.0.1:3006/portal/examples/pose-demo/sequences/seq-001/pose-3d.mp4 -o /tmp/pose-3d.mp4
```

如果只想确认无 SDK 环境的失败提示：

```bash
go build -o /tmp/portal-demo-generator-nosdk ./cmd/portal-demo-generator
/tmp/portal-demo-generator-nosdk
```

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

- 注册用户批量 Demo 默认读取 `examples/seqs`。
- 匿名批量 Demo 默认读取 `examples/seqs`。
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

## 9. 当前已知行为

- `face_image` 可能为空，这是正常情况
- 图片序列模式下，`image_ids/rects` 为空或为 0 是正常的；这种情况下 Sequence API 返回 `frames: []`、`frame_count: 0`，不会回退成输入图片数量
- 视频模式下，理论上 `image_ids/rects` 应该更完整，但这部分是否完整仍受 SDK 实际输出影响
- 视频上传后会自动进入解析，不需要再调用 `complete`
