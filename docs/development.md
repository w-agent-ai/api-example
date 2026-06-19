# 步态解析公网服务开发文档

本文档面向开发人员，描述如何理解代码结构、如何本地开发、如何扩展功能、如何调试常见问题，以及推荐的改造顺序。

如果你要先运行服务，请优先看 [testing.md](/home/watrix/tiandk/agent/gaitAgent/docs/testing.md)。

如果你要先理解系统整体设计，请先看 [design.md](/home/watrix/tiandk/agent/gaitAgent/docs/design.md)。

如果你要直接查数据库、表、字段含义，请看 [database-dictionary.md](/home/watrix/tiandk/agent/gaitAgent/docs/database-dictionary.md)。

## 1. 本地开发前提

建议开发环境：

- Linux `amd64`
- Go `1.24`
- PostgreSQL `12+`
- CUDA 运行环境
- OpenCV/FFmpeg 动态库
- SDK 加密狗

如果只做接口层、账户层、后台页面开发：

- 不一定需要加密狗
- 不一定需要 SDK 成功初始化

如果要做真实解析联调：

- 必须有加密狗
- 必须配置 SDK 动态库

## 2. 关键运行模式

### 2.1 纯文件模式

不配置 `GAIT_DB_DSN`，系统会使用：

- 本地 JSON/文件存储任务与账户数据
- 本地对象存储保存上传文件与结果资产

适合：

- 快速联调
- 单机调试

### 2.2 数据库模式

配置 `GAIT_DB_DSN` 后：

- 任务、账户、账单、支付、审计、统计走 PostgreSQL
- 对象资产仍可继续走本地对象存储

适合：

- 持久化验证
- 多进程协同
- 后续扩展多机 worker

## 3. 代码入口说明

### 3.1 API 进程

入口：

- [cmd/api/main.go](/home/watrix/tiandk/agent/gaitAgent/cmd/api/main.go)

核心组装：

- [internal/app/api.go](/home/watrix/tiandk/agent/gaitAgent/internal/app/api.go)

主要职责：

- 创建 sequence service
- 创建 video service
- 创建 account service
- 装配 payment provider
- 装配 checkout provider
- 绑定 SQL 仓库
- 注册路由
- 启动 HTTP 服务

### 3.2 Worker 进程

入口：

- [cmd/worker/main.go](/home/watrix/tiandk/agent/gaitAgent/cmd/worker/main.go)

核心组装：

- [internal/app/worker.go](/home/watrix/tiandk/agent/gaitAgent/internal/app/worker.go)

主要职责：

- 初始化 SDK engine
- 创建 video service
- 绑定 SQL 视频任务仓库
- 启动本地 worker API
- 启动任务轮询 runner

## 4. 主要业务模块说明

### 4.1 `internal/sequences`

职责：

- 序列任务创建
- 帧上传
- 同步解析
- public 匿名支付
- 注册用户钱包扣费
- 结果返回
- 清理过期任务

建议重点阅读：

- [internal/sequences/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/sequences/service.go)

### 4.2 `internal/videos`

职责：

- 视频任务创建
- 视频上传
- 一期支付
- worker 处理推进
- 二期支付
- 结果返回
- 过期清理

当前代码约束：

- 注册用户视频任务只能通过 `CreateTaskForUser` / `GetTaskForUser` / `GetResultForUser` / `DeleteTaskForUser`
- 匿名调用只能通过 public 路径
- `CreateTask` / `GetTask` / `GetResult` / `DeleteTask` 这些未绑定用户的旧入口当前只保留为显式返回 `unauthorized`

建议重点阅读：

- [internal/videos/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/videos/service.go)

### 4.3 `internal/accounts`

职责：

- 用户注册
- 登录与 session
- API Key
- 钱包
- 充值单
- 钱包流水
- 后台补款

建议重点阅读：

- [internal/accounts/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/accounts/service.go)
- [internal/accounts/sql_store.go](/home/watrix/tiandk/agent/gaitAgent/internal/accounts/sql_store.go)

### 4.4 `internal/payments`

职责：

- 匿名支付协议
- checkout provider
- webhook 解析
- mock 支付
- x402 支付验证
- Stripe / Paddle / WeChat Pay / Alipay checkout

建议重点阅读：

- [internal/payments/provider.go](/home/watrix/tiandk/agent/gaitAgent/internal/payments/provider.go)
- [internal/payments/checkout.go](/home/watrix/tiandk/agent/gaitAgent/internal/payments/checkout.go)
- [internal/payments/checkout_providers.go](/home/watrix/tiandk/agent/gaitAgent/internal/payments/checkout_providers.go)

### 4.5 `internal/httpapi`

职责：

- 路由
- handler
- 中间件
- 页面 HTML
- 用户门户
- 管理后台

核心文件：

- [internal/httpapi/router.go](/home/watrix/tiandk/agent/gaitAgent/internal/httpapi/router.go)

子模块：

- `handlers/users`
- `handlers/admin`
- `handlers/videos`
- `handlers/sequences`
- `handlers/public`

### 4.6 `internal/repository/sqlrepo`

职责：

- 视频任务 SQL 仓库
- 序列任务 SQL 仓库
- 兼容父表 `tasks`
- 账单同步
- 支付记录同步
- 任务事件同步

重点文件：

- [internal/repository/sqlrepo/sequence_tasks.go](/home/watrix/tiandk/agent/gaitAgent/internal/repository/sqlrepo/sequence_tasks.go)
- [internal/repository/sqlrepo/video_tasks.go](/home/watrix/tiandk/agent/gaitAgent/internal/repository/sqlrepo/video_tasks.go)
- [internal/repository/sqlrepo/task_compat.go](/home/watrix/tiandk/agent/gaitAgent/internal/repository/sqlrepo/task_compat.go)
- [internal/repository/sqlrepo/billing_records.go](/home/watrix/tiandk/agent/gaitAgent/internal/repository/sqlrepo/billing_records.go)
- [internal/repository/sqlrepo/task_events.go](/home/watrix/tiandk/agent/gaitAgent/internal/repository/sqlrepo/task_events.go)

## 5. 当前数据模型说明

### 5.1 真实迁移表结构来源

不要只看 `docs/schema.sql`，运行时真实库结构以迁移文件为准：

- [db/migrations/000001_init.up.sql](/home/watrix/tiandk/agent/gaitAgent/db/migrations/000001_init.up.sql)
- [db/migrations/000002_video_task_metadata.up.sql](/home/watrix/tiandk/agent/gaitAgent/db/migrations/000002_video_task_metadata.up.sql)
- [db/migrations/000003_sequence_task_metadata.up.sql](/home/watrix/tiandk/agent/gaitAgent/db/migrations/000003_sequence_task_metadata.up.sql)
- [db/migrations/000004_account_metadata.up.sql](/home/watrix/tiandk/agent/gaitAgent/db/migrations/000004_account_metadata.up.sql)
- [db/migrations/000005_admin_runtime_audit_stats.up.sql](/home/watrix/tiandk/agent/gaitAgent/db/migrations/000005_admin_runtime_audit_stats.up.sql)

### 5.2 任务相关表

- `tasks`
- `video_tasks`
- `sequence_tasks`
- `billing_orders`
- `payments`
- `task_events`

### 5.3 账户相关表

- `account_users`
- `account_api_keys`
- `account_wallets`
- `account_wallet_ledger`
- `account_deposits`

### 5.4 运行与后台相关表

- `runtime_configs`
- `admin_audit_logs`
- `admin_stats_snapshots`

## 6. 任务持久化实现方式

当前视频、序列服务本身仍保留原始业务结构，不直接围绕数据库建模，而是：

- 业务服务维护任务对象
- 仓库层在 `SaveTask` 时把任务 JSON 写入 `metadata_json`
- 再同步兼容字段到 SQL 列

优点：

- 对现有业务代码入侵小
- 文件模式与 SQL 模式可以共存

代价：

- 真实聚合查询需要兼容部分 JSON 与部分冗余列

## 7. 计费与支付开发说明

### 7.1 计费策略

当前价格策略由 `internal/pricing` 提供，运行时配置可覆盖默认值。后台统一按人民币分设置 API 价格，注册用户钱包余额、包月套餐额度和消费记录统一使用 CNY。英文页面只在展示层按 `cny_usd_exchange_rate` 折算美元估算；匿名 x402 仍按 USD/稳定币结算，服务端会用 `cny_usd_exchange_rate` 把 CNY 订单金额折算成 USD cents。

核心规则：

- 视频一期：按视频帧数
- 视频二期：按序列个数 + 总序列帧数
- 序列单次：注册用户按输出序列个数固定计费，输出为空按 1 个序列计费；匿名 x402 按输入序列个数计费
- Gait Pose 单次：按序列帧数，后台按人民币分每千帧配置

对应运行配置字段：

- `video_per_k_frames`
- `sequence_per_k_frames`
- `sequence_per_sequence`
- `gait_pose_per_k_frames`
- `currency`
- `cny_usd_exchange_rate`
- `eurc_usd_exchange_rate`

### 7.2 注册用户扣费

注册用户通过：

- CNY 钱包余额
- 包月 CNY 额度
- 自动扣费

包月套餐购买与自动续费：

- 用户购买套餐时默认勾选自动续费
- 勾选自动续费时，后端创建 `purchase_kind=monthly_plan` 的 checkout deposit，并调用支付渠道的 agreement/session 签约能力
- 如果当前 checkout provider 不支持 agreement，接口返回 `monthly_agreement_unsupported`
- 用户取消勾选自动续费时，后端优先从 CNY 充值余额扣套餐支付金额；充值余额不足时创建整笔套餐金额的一次性 checkout
- 生效套餐关闭自动续费时，当前实现先把本地 `monthly_auto_renew=false`、`monthly_agreement_status=canceled`；生产接入真实支付渠道后，需要同时调用支付渠道取消协议/订阅
- 生效套餐重新开启自动续费时，不允许只通过 PUT 修改本地开关，必须重新进入签约授权流程

财务收入确认口径：

- `user_deposit` 充值到账不算收入，只算充值现金流入和用户充值余额增加
- `monthly_plan_purchase` / `monthly_plan_renewal` 按实际支付金额确认套餐购买收入
- API 消费流水中的 `monthly_amount` 表示套餐额度消耗，不确认收入
- API 消费流水中的 `wallet_amount` / `recognized_revenue_amount` 表示从充值余额扣费的部分，确认充值余额消费收入
- 匿名调用收入来自公开支付或 x402 的已结算金额
- 财务管理页总览拆分展示套餐购买收入、充值余额消费收入、匿名调用收入、充值余额和累计现金流入
- 财务管理页表格分为“充值余额流水、套餐流水、收入记录、充值记录、匿名消费记录”：底层仍复用账户账本、充值单和匿名支付记录，不新建多套物理账本表

当前扣费流水保存在：

- 账户层 `account_wallet_ledger`
- SQL 兼容账单层 `billing_orders`

### 7.3 匿名支付

匿名模式通过：

- `payment_required`
- `payment_context`

引导客户端再次发起支付确认。

当前真实匿名支付使用 x402。服务端会在 `402` 响应中返回多个 `accepts`，客户端可以按自己钱包资产选择可支付路线。

当前生产路线：

- Base / Polygon / Arbitrum 的 USDC，使用 EIP-3009。
- Base / Polygon / Arbitrum 的 USDT，使用 Permit2。
- Base 的 EURC，使用 EIP-3009，按后台运行配置里的 EURC 汇率从 USD 金额换算。

相关接口：

- `GET /v1/payment-capabilities`
- `GET /v1/portal/bootstrap`

如果你要扩展新协议：

1. 在 `internal/payments` 增加 provider 或 checkout
2. 在 `internal/app/api.go` 注入配置
3. 在用户门户支付选项中加入展示
4. 在 webhook 或回调中写到账户/账单

### 7.4 微信/支付宝接入建议

正式接入时建议补齐：

- 商户订单号与内部订单号一一映射
- 回调幂等
- 回调签名校验
- 充值单状态机
- 账单对账脚本

### 7.5 支付配置与密钥原则

真实支付密钥不要提交到 Git。

当前建议：

- systemd 环境文件放在 `/etc/gaitagent/*.env`。
- 仓库里的 `deploy/systemd/*.env` 只能作为模板或本机运行配置，不应提交真实私钥、API Secret、钱包私钥。
- 测试钱包私钥只能写在本地测试脚本或环境变量中，不进入公共 Demo。
- 管理后台可以展示和修改支付配置，但修改必须有确认弹窗、审计日志和历史记录。

## 8. 管理后台开发说明

### 8.1 管理后台页面代码

主要文件：

- [internal/httpapi/handlers/admin/portal.html](/home/watrix/tiandk/agent/gaitAgent/internal/httpapi/handlers/admin/portal.html)
- [internal/httpapi/handlers/admin/handler.go](/home/watrix/tiandk/agent/gaitAgent/internal/httpapi/handlers/admin/handler.go)
- [internal/httpapi/handlers/admin/overview.go](/home/watrix/tiandk/agent/gaitAgent/internal/httpapi/handlers/admin/overview.go)

当前页面入口：

- 用户门户：`/portal`
- 管理后台：`/admin`

用户门户职责：

- 未登录时展示可试玩首页、产品能力、API 接入、Agent 接入、计费方式和 Demo 下载。
- 首页试玩使用单行控件选择能力、上传文件、填写文字需求并发起免注册试用。图搜万物提示词示例为“猫、公交车、穿红衣服的人”，英文为 `cat, bus, person in red`；单文件图搜万物只显示文件名，多文件能力显示首个文件名和数量。
- 通过邮箱和密码注册/登录。
- 登录后管理余额、充值、API Key、使用记录。
- API Key 表展示完整 key、状态、累计使用金额，并支持复制、暂停、恢复、删除。
- 使用记录按分页和条件过滤展示，金额按账户币种显示为正数；计费说明按语言展示人民币或换算后的美元价格。
- 登录后仍保留功能说明与 Demo 下载，方便用户集成。
- 登录前后顶部导航必须保持同一坐标；当前实现把左侧导航 fixed 到视口，修改顶部模板时不要改回依赖父容器 grid/absolute 的定位。
- 匿名 Agent 与 x402 路线说明归入 Agent 接入页面，不再维护独立支付方式门户页。

管理后台职责：

- 看板：用户数、活跃用户、收入、处理量、硬件负载等图表。
- 用户管理：用户状态、钱包、充值、后台补款、使用记录。
- 财务管理：收入总览、充值余额流水、套餐流水、收入记录、充值记录、匿名消费记录；充值不直接算收入，收入按套餐购买、充值余额消费和匿名调用分开展示。
- 计费与清理：视频一期、视频二期、序列计费、人民币/美元展示汇率、EURC 汇率、任务清理时长等运行配置。
- 支付配置：支付宝、微信支付、PayPal、x402 收款钱包和支付路线。
- 操作审计：管理员补款、修改计费、修改支付配置等操作必须落审计日志。

### 8.2 当前统计实现

当前后台统计分成两类：

- 概览/财务：优先 SQL 聚合，失败时回退服务内存汇总
- `timeseries`：通过定时采样写入 `admin_stats_snapshots`

SQL 聚合实现：

- [internal/adminstats/sql_summary.go](/home/watrix/tiandk/agent/gaitAgent/internal/adminstats/sql_summary.go)

快照采样实现：

- [internal/adminstats/store.go](/home/watrix/tiandk/agent/gaitAgent/internal/adminstats/store.go)
- [internal/adminstats/sql_backend.go](/home/watrix/tiandk/agent/gaitAgent/internal/adminstats/sql_backend.go)

### 8.3 如果要继续增强后台

推荐顺序：

1. 增强 `timeseries` SQL 事件重建能力
2. 增加按维护人员筛选的审计页面
3. 增加匿名 Agent 来源维度
4. 增加支付渠道对账页面

## 9. SDK 相关开发说明

### 9.1 SDK 边界

SDK 相关代码主要在：

- `algorithms/sdk`
- `internal/sdkengine`

### 9.2 为什么不要把 SDK 放进 API 进程

原因：

- 崩溃风险高
- 动态库依赖复杂
- GPU 资源管理不适合公网进程
- 会影响接口稳定性

### 9.3 调试 SDK 问题

推荐顺序：

1. 先跑 `sdkprobe`
2. 再跑 `videoprobe`
3. 再启动 worker
4. 最后走完整 HTTP 链路

工具入口：

- [cmd/sdkprobe/main.go](/home/watrix/tiandk/agent/gaitAgent/cmd/sdkprobe/main.go)
- [cmd/videoprobe/main.go](/home/watrix/tiandk/agent/gaitAgent/cmd/videoprobe/main.go)

## 10. 任务恢复与重启语义

服务重启后，已经扣费的任务必须继续产出结果，不能因为进程退出丢失。

当前实现：

- 视频任务在 phase 1 已支付后进入 `uploaded` 或 `processing`。
- worker 周期性调用 `videos.Service.ProcessPending`，扫描 `uploaded` 和 `processing` 视频任务。
- 如果 SDK 内部已经丢失该视频任务，`GetVideoProgress` 返回 `-1`，worker 会重新 `StartVideo`，而不是直接失败。
- 序列任务在支付成功后进入 `processing`，同时保存 `PendingParse` 帧清单。
- worker 周期性调用 `sequences.Service.ProcessPending`，扫描带 `PendingParse` 的 `processing` 序列任务并重新执行真实 SDK。

限制：

- 当前仍是单机 worker 模式，API 与 worker 在同一台机器。
- 后续多机 worker 需要补 worker lease 和任务抢占，避免多个 worker 同时处理同一任务。

## 11. 常见开发任务说明

### 11.1 新增一个接口

步骤：

1. 在对应 service 中实现业务逻辑
2. 在对应 handler 中增加路由与解析
3. 如果涉及持久化，更新 SQL 仓库
4. 增加测试
5. 更新 `docs/api.md`

### 11.2 新增一个后台配置项

步骤：

1. 在 `internal/runtimeconfig` 增加状态字段
2. 在 `internal/admincfg` 增加读写逻辑
3. 在后台 `portal.html` 增加表单
4. 在 API/Worker 热更新逻辑中应用该配置
5. 更新文档

### 11.3 新增一个支付方式

步骤：

1. 在 `internal/payments` 实现 checkout 或 protocol
2. 在 `internal/app/api.go` 注入
3. 在用户页面展示支付选项
4. 增加 webhook 处理
5. 增加充值单与对账测试

### 11.4 新增一个任务事件

当前事件同步在仓库层做。

步骤：

1. 修改 [task_events.go](/home/watrix/tiandk/agent/gaitAgent/internal/repository/sqlrepo/task_events.go)
2. 如有必要，补充旧值/新值对比逻辑
3. 更新 `dbverify`
4. 更新设计文档

## 12. 测试与验证

### 12.1 常用测试命令

基础回归：

```bash
go test ./...
```

需要动态库时：

```bash
LD_LIBRARY_PATH=$PWD/algorithms/lib_core_64:$PWD/algorithms/lib_64:$PWD/algorithms/include/opencv4/lib64:/usr/local/cuda/lib64:/usr/local/lib:$LD_LIBRARY_PATH \
go test ./...
```

数据库验证：

```bash
GAIT_DB_DSN=postgres://... go run ./cmd/dbverify
```

### 12.2 `dbverify` 作用

`cmd/dbverify` 用于：

- 校验迁移是否完整
- 校验关键表字段是否存在
- 验证运行配置仓库
- 验证后台审计仓库
- 验证后台统计仓库
- 验证账户 SQL 仓库
- 验证视频/序列任务 SQL 仓库
- 验证账单与任务事件是否落库

### 12.3 真实 PostgreSQL 验证建议

建议每次涉及 SQL 仓库、迁移、支付落库、后台统计时，都跑一遍真实 PostgreSQL smoke，而不只跑单测。

## 13. 常见问题

### 13.1 `go test` 运行时报 OpenCV 动态库找不到

原因：

- 测试二进制运行时需要加载 OpenCV 动态库

处理：

- 补 `LD_LIBRARY_PATH`

### 13.2 `dbverify` 跑不起来

常见原因：

- `GAIT_DB_DSN` 未配置
- PostgreSQL 未启动
- `postgres` 用户无缓存目录权限
- 动态库路径缺失

### 13.3 端口绑定失败

如果在沙箱里出现禁止绑定端口，不代表真实机器不能绑定。真实机器上仍需以：

- `curl`
- `ss -ltnp`

做最终验证。

### 13.4 SDK 一直卡住

先确认：

- 是否插入加密狗
- SDK 进程是否重启
- 是否走的是 worker，而不是 API 直接调 SDK

## 14. 当前推荐开发顺序

如果继续推进项目，推荐顺序：

1. 完成正式微信/支付宝充值链路
2. 完成后台财务对账与订单查询
3. 完成国际化语言与地区支付路由
4. 完成基于事件的时序统计
5. 完成 worker lease 与多 worker 模式
6. 完成云对象存储后端

## 15. 文档维护原则

后续每次改动以下内容时，必须同步更新文档：

- 新接口或接口字段
- 任务状态变化
- 新增支付方式
- 新增数据库表/列
- 新增后台页面功能
- 新增运行配置项

建议同步更新的文档：

- `docs/design.md`
- `docs/development.md`
- `docs/api.md`
- `docs/state-machine.md`
- `docs/testing.md`
