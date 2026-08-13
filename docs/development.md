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

### 2.1 数据库模式

必须配置 `GAIT_DB_DSN`。API 和 worker 启动时会连接 PostgreSQL；未配置或连接失败时启动失败，不再回退到本地 JSON/文件存储，也不会在正常启动路径自动导入本地账户 JSON。

- SQL 模式下，API 进程账户服务启动只加载用户、API Key、钱包和套餐等运行必要的轻量状态；`account_wallet_ledger` 历史钱包流水和 `account_deposits` 充值记录不再启动时全量加载。
- 用户使用记录、后台用户活动摘要、最近流水和充值记录改为按用户、时间、类型、状态和 limit 从数据库查询。
- worker 进程不创建账户服务，不缓存用户、API Key、钱包或套餐；所有钱包余额事务只允许由单个 API 进程处理。

- 任务、账户、账单、支付、审计、统计走 PostgreSQL
- 对象资产仍可继续走本地对象存储

`GAIT_DB_DSN` 填 PostgreSQL 连接串：

```bash
GAIT_DB_DSN=postgres://<用户名>:<密码>@<主机>:<端口>/<数据库名>?sslmode=disable
```

本机部署通常类似：

```bash
GAIT_DB_DSN=postgres://gaitagent:<password>@127.0.0.1:5432/gaitagent?sslmode=disable
```

线上 systemd 环境文件分别是：

- `/etc/gaitagent/gait-api.env`
- `/etc/gaitagent/gait-worker.env`

适合：

- 持久化验证
- 生产部署
- 本地联调，需先启动 PostgreSQL 并执行迁移
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
- 创建 sequence service
- 绑定 SQL 视频任务仓库
- 绑定 SQL 序列任务仓库
- 启动本地 worker API
- 启动任务轮询 runner

worker 进程的边界：

- 可以读取运行时配置、轮询任务、写任务状态和 SDK 结果。
- 不允许创建 `accounts.Service`，不调用 `SetAccounts(...)` 注入账户服务。
- 不允许调用 `ChargeWallet(...)`、`SettleDeposit(...)`、`CreditWallet(...)`、`DebitWallet(...)` 等钱包/充值/补扣款入口。
- 计费、充值到账、套餐购买、套餐续费、后台补款和扣款都必须留在 API 进程。
- worker 轮询任务时只按待处理状态查询：视频查 `uploaded` / `processing`，序列查 `processing`；过期清理由 API 定时循环负责，避免 worker tick 全表扫描任务表。
- worker 只保存 SDK 原始 gait 特征，不保存或计算用户旋转矩阵。完整 sequence/video 结果 JSON 写入对象存储 `sequence-results/<task_id>/result.json` / `video-results/<task_id>/result.json`，数据库任务 metadata 只保存 `result_object_key`。注册用户结果在 API 返回前读取结果文件并按用户 `gait_rotation_seed` 旋转；seed 缺失时由 API 账户服务自动生成并持久化，矩阵由 API 进程内存缓存。

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
- x402 支付验证
- WeChat Pay / Alipay checkout
- Crypto recharge scanner

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
- 仓库层在 `SaveTask` 时把结构化列之外的任务补充信息写入 `metadata_json`
- 再同步兼容字段到 SQL 列

优点：

- 对现有业务代码入侵小
- 任务和账户等元数据统一进入 SQL，结构化列是事实源；`metadata_json` / `detail_json` 只保存结构化列之外的补充信息
- 兼容期内，任务对象中的 `billing` 仍随任务 JSON 保存并用于恢复运行态；同步写入的 `billing_orders` 用于查询、统计和对账，不作为运行态账单重建来源

代价：

- 真实聚合查询需要兼容部分 JSON 与部分冗余列

## 7. 计费与支付开发说明

### 7.1 计费策略

当前价格策略由 `internal/pricing` 提供，运行时配置可覆盖默认值。后台统一按人民币分设置 API 价格，注册用户钱包余额、包月套餐额度和消费记录统一使用 CNY。英文页面只在展示层按 `cny_usd_exchange_rate` 折算美元估算；匿名 x402 仍按 USD/稳定币结算，服务端会用 `cny_usd_exchange_rate` 把 CNY 订单金额折算成 USD cents。CNY 转 USD 后按 USD cent 向上取整，任何正数美元金额至少为 `$0.01`。

核心规则：

- 序列单次：注册用户按输出序列个数固定计费，输出为空按 1 个序列计费；匿名 x402 按输入序列个数计费
- Gait Pose 单次：按上传序列个数，后台按人民币分每序列配置，默认 1 分/序列
- 人脸识别单次：`POST /v1/features/face` 输入一张矫正后人脸图，按 `face_per_k_frames` 计费，默认 100 分/千帧，单张向上取整到 1 分
- ReID识别单次：`POST /v1/features/reid` 输入一张人体图，按 `reid_per_k_frames` 计费，默认 100 分/千帧，单张向上取整到 1 分
- 注册用户序列提特征另有每用户每月上限，按实际成功提取出步态特征的输出序列数计数；默认 100000，可在后台“注册用户策略”配置，`0` 表示不限制
- 官网首页人脸体验依赖 `examples/browser/client/facedet_wasm.js` 和 `facedet_wasm.wasm`；如修改 `examples/registered/cpp/face_feature_demo/third_party/libfacedetection/src`，需先 `source /opt/emsdk/emsdk_env.sh`，再运行 `examples/browser/client/build_facedet_wasm.sh` 重建 WASM。首页人脸检测最长边按 1280 缩放并在浏览器 Worker 中运行；ReID 人体检测最长边按 640 缩放并优先在 Worker 中运行。

对应运行配置字段：

- `sequence_per_k_frames`
- `sequence_per_sequence`
- `gait_pose_per_sequence`
- `face_per_k_frames`
- `reid_per_k_frames`
- `currency`
- `cny_usd_exchange_rate`
- `eurc_usd_exchange_rate`
- `runtime:account.monthly_sequence_feature_limit`
- `runtime:account.signup_bonus_amount`

### 7.2 注册用户扣费

注册用户通过：

- CNY 钱包余额
- 包月 CNY 额度
- 自动扣费

账户注册成功后只创建用户、默认 CNY 钱包和默认 API Key，不再立即发放赠送余额。用户首次普通充值到账后，后端按 `runtime:account.signup_bonus_amount` 给 CNY 充值余额发放首充赠送额度，默认 5 元；该字段名保留历史命名，业务语义为首充赠送。赠送只对普通余额充值触发一次，套餐购买订单不触发；0 表示不赠送。注册用户创建序列任务时会先检查是否有可用 CNY 余额以及是否已经达到月度提特征上限，余额不足或限额已满时不会分配上传地址。

用户登录用户中心时，`/v1/me` 会返回 `has_settled_deposit`、`needs_first_deposit_prompt` 和 `first_deposit_bonus_amount`。如果用户还没有完成首次普通充值，前端会在本次登录会话中弹窗提示“完成首次充值，将赠送对应金额”，并提供“忽略”和“去充值”两个按钮；退出后再次登录或刷新重新进入时仍会再次提醒，直到有普通充值到账记录。

注册用户序列解析返回结果前，会对 512 维步态特征应用该用户绑定的 512x512 正交旋转矩阵。数据库只保存用户的 `gait_rotation_seed`，服务端按 seed 确定性生成并缓存矩阵；非 512 维兼容测试特征不旋转。

包月套餐购买与自动续费：

- 用户购买套餐时默认勾选自动续费
- 购买套餐支持微信、支付宝和余额；PayPal、Apple Pay、Google Pay、国际银行卡不再支持
- 选择余额支付时立即扣 CNY 余额并创建套餐实例；选择第三方支付时只创建 checkout，支付成功回调后再扣套餐金额并发放套餐实例
- 第三方充值和第三方套餐购买共用 `internal/httpapi/handlers/users/handler.go` 的 checkout deposit 创建路径；不要在充值和套餐购买里分别手写 provider/channel/currency 解析
- `account_deposits.detail_json.purchase_kind=monthly_plan` 是套餐购买和普通充值的分界；webhook/admin settle 完成后根据该字段决定是否调用套餐发放逻辑
- 套餐 checkout 回调必须幂等：如果 `account_deposits` 已经是 `settled` 但还没有 `source_deposit_id` 对应的 subscription，回调会继续补发套餐；重复回调不能创建第二个 subscription
- checkout 成功回调必须校验平台返回的商户订单金额和币种，必须与 `account_deposits.amount/currency` 完全一致后才能入账或补发套餐。微信支付优惠/满减场景下，`amount.payer_total` 是用户优惠后的实付金额，不能用它和系统订单金额比较；系统应使用 `amount.total` 校验，并把 `payer_total` 只作为审计字段记录。支付宝使用 `total_amount` 校验，不使用优惠后的买家实付或商家实收字段作为订单金额。
- API 进程会定时扫描 `awaiting_checkout` / `awaiting_payment` / `expired` 的在线 checkout 充值单，向支持主动查询的 provider 查询支付状态；如果确认已完成，会走和 webhook 相同的金额校验、入账和套餐补发逻辑。这个扫描用于补偿服务更新、网络抖动或第三方 webhook 未送达，不替代 webhook 实时入账。
- 在线充值单超过未支付 TTL 后不再硬删除，而是标记为 `expired` 并默认从充值列表隐藏；保留 provider ref / checkout session，后续 webhook 或主动对账确认已付款时仍可恢复结算，避免“用户已付款但账户未到账”。
- 托管 mock checkout 和用户自助 mock complete 路由已移除；测试环境也不能通过 HTTP 自助把充值单标记为已支付
- 每次购买创建独立 `account_subscriptions` 套餐实例；同一用户可以同时拥有多个套餐实例，同一套餐也可以重复购买
- 每个套餐实例独立维护 `remaining_amount`、`expires_at`、`auto_renew`、`renewal_key` 和通知状态
- 同一个套餐 ID 最多一个实例开启自动续费；开启新实例自动续费时，后端会关闭同套餐其他实例的自动续费
- 自动续费只从 CNY 充值余额扣款；续费前 3 天发送提醒。系统在到期前约 1 天先尝试扣款，失败后发余额不足/续费失败提醒；之后到期日当天、到期日后一天最多各再尝试一次。`renewal_key` 使用本地日期，例如 `2026-07-10`，用于防止同一天重复扣款
- API 消费按最早到期优先消耗套餐实例额度，套餐额度不足时再扣 CNY 充值余额

资金一致性要求：

- 生产 SQL store 下，钱包、流水、充值单、套餐实例等资金多表写入必须通过账户层批量持久化并放在同一个数据库事务里提交
- SQL store 的充值单保存带数据库级幂等保护：已 `settled` 的充值单不能被第二个 `settled` upsert 再次结算，跨进程重复 webhook 要让事务回滚
- 文件 store 仍用于本地开发/测试，不能作为资金一致性的生产依据
- 注册接口如果同时提交 email 和 phone，且对应验证服务已启用，两个渠道都必须验证通过；前端注册入口自动识别邮箱/手机号，登录后绑定另一种联系方式必须使用 `bind_email` / `bind_phone` 验证码 purpose
- 邮箱和短信验证码只保存 `code_hash`，不保存明文验证码。API 进程后台维护循环每天最多清理一次验证码记录，删除 `created_at` 早于 90 天的 `email_verification_codes` 和 `sms_verification_codes`。
- CORS 只对公开任务/上传/支付能力等浏览器 API 开放 `Authorization`；用户会话、账户和管理类 `/v1/` API 不使用通配跨域
- 注册用户任务扣费按 `order_id + reason_code` 幂等；`ChargeWallet(...)` 在内存流水未命中时，SQL store 会按 `user_id + order_id + reason_code + direction=debit` 查询历史 `account_wallet_ledger`。服务重启后即使没有加载历史流水，同一订单重复恢复也必须返回既有 ledger、不重复扣钱包；金额不一致时必须报错。回归测试见 `TestChargeWalletIdempotencyFallsBackToStoreLedgerQuery`。
- 注册用户图搜万物和 Gait Pose 必须先拿到上游/SDK 成功结果，再扣钱包；失败请求不能扣费
- 免注册试用如果 SDK/上游失败，必须回退刚消费的试用 request/frame/amount 计数
- `usage_records` 追加失败不能静默吞掉；钱包/支付结算成功后如果审计流水落库失败，应返回错误等待重试或人工盘点
- `usage_records` 写入是同步单条写库，不做内存攒批。每条成功写入会在同一个数据库事务里更新 `daily_usage_summary`、`daily_api_key_usage_summary`、`daily_monthly_usage_summary` 和 `daily_public_identity_summary`，避免进程崩溃导致明细和汇总长期不一致。
- 本地对象存储必须拒绝包含 `..`、绝对路径或反斜杠的 object key，防止共享存储接口被路径穿越
- 桌面客户端本地 HTTP 服务只能接受 loopback Host/Origin；`/api/state` 等响应不能返回 session token 或完整 API Key
- 管理端运行时配置先持久化到 runtime store，再应用到内存服务，避免持久化失败但运行态已经改变
- 管理端 cookie 会话执行非只读请求时必须校验同源 Origin/Referer；Bearer admin token 仍用于脚本和服务端调用
- 管理端创建用户必须显式传入密码，不能使用固定默认密码

财务收入确认口径：

- `user_deposit` 充值到账不算收入，只算充值现金流入和用户充值余额增加
- `monthly_plan_purchase` / `monthly_plan_renewal` 按实际支付金额确认套餐购买收入
- API 消费流水中的 `monthly_amount` 表示套餐额度消耗，不确认收入
- API 消费流水中的 `wallet_amount` / `recognized_revenue_amount` 表示从充值余额扣费的部分，确认充值余额消费收入
- 匿名调用收入来自公开支付或 x402 的已结算金额
- 运维营收周报/月报/年报统一按人民币 CNY 分聚合和展示。注册用户调用只统计 `recognized_revenue_amount` 或 `wallet_amount`，不把 `monthly_amount` 包月额度消耗重复算作收入；包月购买/续费收入从 `account_wallet_ledger` 的 `monthly_plan_purchase` / `monthly_plan_renewal` 确认；匿名 USD 结算按运行时 `cny_usd_exchange_rate` 折算为人民币口径。
- 财务管理页总览拆分展示套餐购买收入、充值余额消费收入、匿名调用收入、充值余额、累计现金流入和支出
- 财务管理页支出当前只有代理商费用，按已到账充值在充值发生时匹配代理商启用状态和当时生效的费率历史计算，作为线下结算参考，不在系统内自动打款
- 财务管理页表格分为“充值余额流水、套餐流水、收入记录、充值记录、匿名消费记录”：底层仍复用账户账本、充值单和匿名支付记录，不新建多套物理账本表。充值余额流水只展示充值到账、后台补扣款、购买套餐和自动续费等余额资金变动；套餐流水只展示套餐购买、额度发放和自动续费；消费类明细统一在收入记录、匿名消费记录或用户/API Key 使用记录中按时间查询。默认打开时，充值余额流水优先展示充值到账，套餐流水优先展示购买套餐，充值记录优先展示已到账记录；收入记录和匿名消费记录默认限制在近期样本，避免后台页面刷新扫描全历史消费明细。财务 CSV 导出服务端默认限制近 30 天，最多返回 10000 行；如果只传结束日期，系统按结束日期向前 30 天导出。

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
4. 让充值和套餐购买都通过公共 checkout deposit 创建路径生成 `account_deposits`
5. 在 webhook 或回调中写到账户/账单
6. 增加同一渠道的两类测试：充值 checkout、套餐 checkout；套餐 checkout 必须验证支付成功前不创建 subscription

### 7.4 微信/支付宝接入建议

正式接入时建议补齐：

- 商户订单号与内部订单号一一映射
- 回调幂等
- 回调签名校验
- 充值单状态机
- 账单对账脚本

当前微信支付 Native 下单、回调解密和主动查单补偿已经接入。微信回调是主路径，查单是兜底补偿；两者都按商户订单金额 `amount.total` 入账校验。支付宝当前主要依赖异步回调，回调金额使用 `total_amount`。

### 7.5 支付配置与密钥原则

真实支付密钥不要提交到 Git。

当前建议：

- systemd 环境文件放在 `/etc/gaitagent/*.env`。
- 仓库里的 `deploy/systemd/*.env` 只能作为模板或本机运行配置，不应提交真实私钥、API Secret、钱包私钥。
- 测试钱包私钥只能写在本地测试脚本或环境变量中，不进入公共 Demo。
- 管理后台可以展示和修改支付配置，但修改必须有确认弹窗、审计日志和历史记录。
- 运行时密钥类配置优先存数据库 `runtime_configs` 的独立配置行，例如短信配置存 `runtime:sms`，不要再增加环境变量兜底。

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

- 未登录时展示可试玩首页、产品能力、API 接入、Agent 接入、计费方式和资源下载。
- 首页试玩按图搜万物、人体2D/3D关节点、步态识别、人脸识别、ReID识别展示能力。图搜万物上传图片并输入目标文本后发起试用；人体关节点和步态识别打开对应浏览器客户端，客户端内同时支持示例视频和用户本地视频；人脸识别和 ReID识别上传图片1/图片2，在浏览器侧检测候选目标，点击画面候选框或候选卡片选择后调用单图特征接口比对。
- 首页示例素材放在 `/opt/gaitagent/portal/examples/`，通过 `/portal/examples/<filename>` 访问。替换示例图片或视频不需要重新编译；替换浏览器检测 WASM 或入口 HTML 需要重新构建并重启 `gait-api`。
- 通过邮箱和密码注册/登录。
- 注册页包含推荐码输入框；有效推荐码绑定代理商，无效推荐码在用户确认后按空推荐码处理。
- 登录后管理余额、充值、API Key、使用记录。
- API Key 表展示完整 key、状态和使用记录入口，并支持复制、暂停、恢复、删除。
- 使用记录按分页和条件过滤展示，金额按账户币种显示为正数；API Key 使用记录弹窗展示按天、类型聚合的使用汇总，按当前 API Key、日期范围和类型从 `daily_api_key_usage_summary` 查询，底部显示当前筛选条件下的累计金额。导出文件按当前 API Key、日期范围和类型从 `account_wallet_ledger` 导出明细流水，按时间由近到远排列，不导出日汇总。单次时间跨度限制为不超过半年；计费说明按语言展示人民币或换算后的美元价格。
- 登录后仍保留功能说明与资源下载，方便用户集成。
- 登录前后顶部导航必须保持同一坐标；当前实现把左侧导航 fixed 到视口，修改顶部模板时不要改回依赖父容器 grid/absolute 的定位。
- 匿名 Agent 与 x402 路线说明归入 Agent 接入页面，不再维护独立支付方式门户页。

管理后台职责：

- 看板：用户数、活跃用户、收入、支出和业务量。运营看板图表展示每日/每周/每月业务量、每日确认收入、活跃用户数，不展示区间累计收入；图表鼠标滚轮不触发缩放，避免滚动页面时误操作。
- 用户管理：用户状态、用户 ID、邮箱、手机号、钱包、充值、后台补款、后台扣款、使用记录。列表和导出都应保留用户 ID 与手机号，并在累计充值后展示累计补款、累计扣款；累计扣款只统计后台扣款流水，不替代累计消费。搜索应覆盖邮箱、手机号和用户 ID，方便排查手机号注册用户。用户详情的账户流水查询按指定日期范围从后端加载全部明细，并支持导出 CSV；账户变动记录展示扣费方式，并分别展示套餐余额和充值余额。代理商功能上线后，用户列表和导出还必须包含推荐码、代理商姓名、代理商手机号或邮箱。用户主数据、钱包、API Key 和订阅是热数据，但管理列表必须服务端分页和服务端搜索，前端每页只解析当前页数据，不能一次返回几十万用户。
- 财务管理：收入/支出总览、充值余额流水、套餐流水、收入记录、充值记录、匿名消费记录；充值不直接算收入，收入按套餐购买、充值余额消费和匿名调用分开展示，支出当前展示代理商费用。后台主要表格需要展示序号列，序号按当前筛选结果和分页位置连续计算。财务页只在主接口返回 summary，充值余额流水、套餐流水、收入记录、匿名消费记录和充值记录都使用独立分页接口；筛选和翻页必须重新请求后端，不能把多类流水一次性返回给浏览器后本地分页。
- 营收报表：周报、月报、年报邮件除资金流入、确认收入和充值余额外，也展示支出和代理商费用；该费用是预计应付佣金，不代表系统已自动打款。
- 代理商管理：超级管理员创建、编辑、停用代理商账号，配置 4 位代理编号和分成比例；列表展示客户数量、当月收入、累计收入和启停记录；代理商登录后只能查看自己发展的客户、客户充值明细、充值汇总和两卡片摘要（客户、收入）。代理商看板的客户列表和充值明细分页展示并带序号列，充值明细必须包含用户 ID、手机号和邮箱。
- 计费与清理：视频一期、视频二期、序列计费、人民币/美元展示汇率、EURC 汇率、任务清理时长等运行配置。
- 支付配置：支付宝、微信支付、x402 收款钱包和支付路线。
- 操作审计：管理员补款、修改计费、修改支付配置等操作必须落审计日志。

代理商功能开发边界：

- 后台账号需要区分超级管理员和代理商账号；接口层必须做权限判断，不能只靠前端隐藏页面。
- 代理商账号使用手机号和密码登录后台；密码必须 hash 保存，不保存明文。
- 代理商只能查询 `agent_id` 等于当前代理商的客户和充值数据。
- 代理商不查看客户 API 消费明细，避免暴露客户业务使用细节。
- 代理商佣金按成功充值到账金额计算，不按 API 消费金额计算；停用或删除后，老客户后续充值不再计入该代理商收益。
- 代理商重新启用后，历史客户仍属于该代理商；重新启用后的客户充值继续计入收益，停用期间充值不补算。
- 默认分成比例为 40%；每次调整写入 `sales_agent_rate_events` 费率历史，历史充值按到账时生效费率计算，不被当前费率回算。
- 月底定时短信只通知应得收入，不做系统内提现、打款、结算状态或结算按钮。
- 短信统计口径为：当期付费客户数按成功充值用户去重，当期充值总额按成功到账后的 CNY 入账金额合计，外币充值优先使用充值明细中的 `credit_amount` / `credit_currency`；当期应得收入按每笔充值到账时生效费率计算后汇总；统计范围按代理商状态事件排除停用期间和删除后的充值。
- 代理商看板摘要分为“客户”和“收入”：客户卡片展示累计客户数、当期注册客户数、当期充值客户数；收入卡片展示累计收入、当期客户充值收入、当期应得收入；时间范围支持手动日期和“今年、上月、当月”快捷按钮。客户列表和充值明细使用独立分页；充值明细从后端返回 `user_id`、`phone`、`email`，不能只展示用户 ID。
- 代理商相关创建、编辑、停用和后台补充调整都应写入 `admin_audit_logs`。

### 8.2 当前统计实现

当前后台统计分成两类：

- 概览/财务：使用 SQL 聚合；SQL 查询失败时直接返回错误，不回退到服务内存汇总，避免触发全量流水扫描
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
- API 与 worker 通过本地 Unix Socket 通信，并共享同一份本地对象存储目录；不要把当前 worker 直接部署到另一台机器。
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
3. 明确 `runtime_configs.config_key` 的独立 section，单独保存该 section，不得覆盖 payment、pricing、monthly 等不相关配置
4. 在后台 `portal.html` 增加表单和独立保存按钮
5. 在 API/Worker 热更新逻辑中应用该配置
6. 增加“只改本配置，不改变其他配置”的测试
7. 更新文档

当前短信验证码配置：

- 后台菜单：短信配置
- 数据库行：`runtime:sms`
- Provider：`aliyun`
- 用途：手机号注册/绑定/找回密码验证码、代理商收益通知、套餐续费提醒
- 必填：`access_key_id`、`access_key_secret`、`sign_name`、`template_code`
- 代理商收益通知另用 `notification_template_code`；未配置时不影响验证码短信，但代理商周报/月报短信会发送失败并记录错误
- 套餐续费提醒另用 `renewal_notice_template_code`；未配置时不影响验证码和代理商通知，手机号用户的续费前提醒会发送失败并记录错误
- 套餐续费失败另用 `renewal_failure_template_code`；未配置时不影响验证码、代理商通知和续费前提醒，手机号用户的扣费失败通知会发送失败并记录错误
- 默认 endpoint：`dysmsapi.aliyuncs.com`
- 套餐续费提醒短信模板建议：`您的W-Agent套餐将于${days_left}天后自动续费，续费金额${renew_amount}元。当前余额${balance}元。`
- 套餐续费提醒模板变量：`days_left`、`renew_amount`、`balance`
- 套餐续费失败短信模板建议：`您的W-Agent套餐自动续费失败，应扣${renew_amount}元。请及时充值，连续失败后将关闭自动续费。`

### 11.3 人脸检测 ONNX 模型更新

人脸 Python/C++ 示例使用 `face_detect.onnx` 和 ONNX Runtime CPU 做本地人脸检测、5 点关键点检测和矫正，再调用 `/v1/features/face`。

当前 `face_detect.onnx` 是从于诗琪 `libfacedetection` 的 `facedetectcnn-data.cpp` 静态权重导出。ONNX 只包含 53 层卷积前向；原库特殊的 3x3/stride2/pad32 图像预处理、bbox/keypoint decode、sigmoid、NMS 和双眼仿射矫正仍保留在 Python/C++ 示例代码里。

导出命令：

```bash
python3 examples/tools/face_detection_onnx/export_face_detect_onnx.py \
  --source examples/registered/cpp/face_feature_demo/third_party/libfacedetection/src/facedetectcnn-data.cpp \
  --output examples/registered/cpp/face_feature_demo/face_detect.onnx
cp examples/registered/cpp/face_feature_demo/face_detect.onnx \
  examples/registered/python/face_feature_demo/face_detect.onnx
```

一致性验证命令：

```bash
g++ -std=c++17 -O2 \
  -Iexamples/registered/cpp/face_feature_demo \
  -Iexamples/registered/cpp/face_feature_demo/third_party/libfacedetection/src \
  -Iexamples/registered/cpp/local_video_to_sequence_demo/third_party/onnxruntime-linux-x64/include \
  examples/tools/face_detection_onnx/compare_cpp_and_onnx.cpp \
  examples/registered/cpp/face_feature_demo/facedet_onnx.cpp \
  examples/registered/cpp/face_feature_demo/third_party/libfacedetection/src/facedetectcnn.cpp \
  examples/registered/cpp/face_feature_demo/third_party/libfacedetection/src/facedetectcnn-data.cpp \
  examples/registered/cpp/face_feature_demo/third_party/libfacedetection/src/facedetectcnn-model.cpp \
  -Lexamples/registered/cpp/local_video_to_sequence_demo/third_party/onnxruntime-linux-x64/lib \
  -lonnxruntime $(pkg-config --cflags --libs opencv4) \
  -Wl,-rpath,$PWD/examples/registered/cpp/local_video_to_sequence_demo/third_party/onnxruntime-linux-x64/lib \
  -o /tmp/compare_face_onnx
/tmp/compare_face_onnx /tmp/image/face1.png /tmp/image/face2.png
```
