# 业务数据流与数据库操作说明

本文档专门说明：

- 某个业务动作发生时
- 代码先做什么、后做什么
- 写了哪些数据库表
- 为什么要这么写
- 如果出问题，优先检查哪里

这份文档的目标不是讲接口怎么调用，而是讲“业务动作与数据库变化的因果关系”，方便你判断当前设计是否合理，以及出问题时快速盘点原因。

## 1. 先看总原则

当前项目的数据写入有两层：

- 业务主写层
- SQL 同步层

### 1.1 业务主写层

大部分业务服务仍然先更新内存中的任务/账户对象，再调用各自的持久化接口：

- 账户：`internal/accounts/service.go`
- 序列任务：`internal/sequences/service.go`
- 视频任务：`internal/videos/service.go`

### 1.2 SQL 同步层

服务启动必须配置 `GAIT_DB_DSN`。各持久化接口最终会写 PostgreSQL，不再回退到本地 JSON/文件存储；API/worker 正常启动也不会自动把本地 JSON 账户状态导入 SQL，历史导入必须走显式迁移工具。

API 进程里的账户服务在 SQL 模式下不把历史钱包流水 `account_wallet_ledger` 和充值记录 `account_deposits` 全量装入内存。启动加载范围控制在账号、API Key、钱包和套餐等运行必要的轻量状态；钱包流水、充值记录、用户活动摘要和最近记录通过数据库按条件查询。支付轮询、结算防重和过期清理按单号、provider ref、checkout session 或状态条件直接访问数据库。

worker 进程不创建账户服务，不缓存用户、API Key、钱包或套餐，也不参与任何钱包余额事务。所有 `ChargeWallet(...)`、`SettleDeposit(...)`、`CreditWallet(...)`、`DebitWallet(...)` 等资金写入都必须由单个 API 进程负责；worker 只通过数据库写任务状态、SDK 结果和结果资产索引。

worker 写入的 SDK 结果保存原始 gait 特征。完整结果 JSON 不写入 `sequence_tasks.metadata_json` / `video_tasks.metadata_json`，而是写入对象存储：

- 序列结果：`sequence-results/<task_id>/result.json`
- 视频结果：`video-results/<task_id>/result.json`

任务表只保留状态、计费、统计字段和 `result_object_key`，避免包含 512 维特征的大 JSON 持续膨胀数据库、WAL 和查询 IO。注册用户读取序列/视频结果时，API 进程按 `result_object_key` 读取原始结果文件，再按该用户稳定的 `gait_rotation_seed` 生成或复用旋转矩阵并返回旋转后的 512 维 gait 特征；如果历史用户缺少 seed，API 会自动生成并持久化。worker 不持有用户 seed 或旋转矩阵。

在线充值单过期时只更新为 `expired`，不硬删除。普通列表默认隐藏 `expired` 记录，但 webhook 和主动对账仍可按 deposit ID、provider ref 或 checkout session 找回订单并完成结算。

其中：

- 账户直接写 `account_*` 表
- 视频/序列任务先写 `sequence_tasks` / `video_tasks`
- 同时兼容同步到 `tasks`
- 再同步到 `billing_orders`
- 必要时同步到 `payments`
- 再同步到 `task_events`

这意味着：

- SQL 结构化列是事实源
- `detail_json` / `metadata_json` 只保存结构化列之外的补充信息
- SQL 冗余字段和审计字段是为了查询、统计、对账

## 2. 数据库表分组

### 2.1 账户相关表

- `account_users`
- `account_api_keys`
- `account_wallets`
- `account_wallet_ledger`
- `account_deposits`

### 2.2 任务相关表

- `tasks`
- `video_tasks`
- `sequence_tasks`
- `billing_orders`
- `payments`
- `task_events`
- `usage_records`

### 2.3 后台相关表

- `runtime_configs`
- `admin_audit_logs`
- `admin_stats_snapshots`

### 2.4 财务消费流水

- `usage_records`

`usage_records` 是独立的长期消费流水表，注册用户调用、匿名 public 调用和免注册试用调用都会写入这里。试用调用金额为 0，来源为 `trial`。

`daily_api_key_usage_summary` 是 API Key 维度的小汇总表，按天、用户、API Key、算法和币种聚合调用次数、金额、套餐抵扣、帧数和序列数。

每条消费明细写入 `usage_records` 时，会在同一个数据库事务内增量更新日汇总、API Key 日汇总、套餐额度消耗日汇总和匿名身份日汇总。系统不把消费明细先缓存在内存里等待批量落库，避免服务重启时丢失财务记录。

如果汇总表异常，可以用 `cmd/rebuild-usage-summary` 从 `usage_records` 按 UTC 日期范围重建这些小汇总表；工具默认 dry-run，只有加 `--execute` 才提交。

它和任务清理策略解耦：视频文件、序列图片、任务 JSON 可以按过期策略删除，但财务消费记录不能跟着任务删除。

高容量消费数据采用三层结构：

- 热库：PostgreSQL 在线 `usage_records` 仅保留最近 3 个月原始明细，`usage_record_keys` 保留同周期幂等键，保证在线查询、排障、审计抽查速度。
- 汇总层：`daily_usage_summary`、`daily_api_key_usage_summary`、`daily_monthly_usage_summary` 长期保留，后台看板、财务报表、API Key 使用记录直接查汇总，不扫明细。
- 冷归档层：更早的月分区由 `cmd/usagearchive` 复制到归档 PostgreSQL 库后再从在线库脱离；归档库可放机械盘 tablespace，用于长期留存和精确追溯。

管理后台“消费记录”和 CSV 导出优先读取 `usage_records`。

## 3. 注册流程

代码入口：

- [internal/accounts/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/accounts/service.go) `Register(...)`

### 3.1 发生了什么

用户注册时，系统会创建：

- 用户
- 默认钱包
- 默认 API Key
- 登录 session

### 3.2 写哪些表

注册主流程里实际持久化的是：

1. `account_users`
2. `account_wallets`
3. `account_api_keys`

session 当前在内存里，不落数据库。

### 3.3 为什么这么设计

- 用户是账户根对象，必须先创建
- 钱包依赖用户
- API Key 依赖用户
- session 是短期状态，当前不要求跨进程共享

### 3.4 出问题优先看哪里

- 注册成功但登录失败：先看 `account_users` 是否写入成功，再看密码 hash 是否正确
- 注册成功但没有默认钱包：看 `account_wallets`
- 注册成功但 API Key 丢失：看 `account_api_keys`

## 4. 登录流程

代码入口：

- [internal/accounts/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/accounts/service.go) `Login(...)`

### 4.1 发生了什么

登录会：

- 校验邮箱和密码
- 创建 session token

### 4.2 写哪些表

当前登录不写数据库表。

写入的是内存 session：

- `sessions`
- `sessionByHash`

### 4.3 为什么这么设计

当前用户门户和管理后台都默认认为：

- API 进程是单实例
- session 不需要跨机器共享

### 4.4 风险点

如果未来：

- API 多实例
- 重启后希望保留登录状态

那 session 必须改为：

- Redis
- 或数据库

## 5. 创建支付订单流程

代码入口：

- 用户 API handler：`createDeposit(...)`、`createMonthlyCheckoutDeposit(...)`
- 统一 checkout deposit 创建入口：`createCheckoutDeposit(...)`
- 账户服务：[internal/accounts/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/accounts/service.go) `CreateDeposit(...)`

### 5.1 用户点击充值或购买套餐时发生了什么

用户在门户输入充值金额，或在套餐页选择第三方支付购买套餐后：

1. API 根据渠道判断是手工订单还是 checkout 订单
2. 通过统一入口解析 provider/channel/currency
3. 构造 `CreateDepositInput`
4. 创建 `account_deposits` 内部支付订单
5. 如果是在线支付，再创建 checkout session
6. 把 checkout 信息更新回支付订单

普通充值和套餐购买共享这条路径。区别只在 `detail_json`：

- 普通充值：`purchase_kind` 为空或不是 `monthly_plan`
- 套餐购买：`purchase_kind=monthly_plan`，并保存 `monthly_plan_id`、`monthly_pay_amount`、`monthly_grant_amount`、`monthly_auto_renew`

### 5.2 第一次写数据库

创建支付订单时写：

- `account_deposits`

关键字段：

- `public_id`
- `user_public_id`
- `currency`
- `amount`
- `status`
- `provider`
- `channel`
- `detail_json`
- `metadata_json`

状态一般是：

- 手工充值：`pending`
- 在线支付：`awaiting_checkout`

币种规则：

- 微信、支付宝充值和套餐购买：`currency=CNY`
- PayPal、国际卡、Apple Pay、Google Pay 不再支持
- 套餐配置仍以 CNY 为准；支付单在 detail 中记录 `checkout_amount`、`checkout_currency`

### 5.3 第二次写数据库

如果是在线支付，还会调用：

- `UpdateDepositCheckout(...)`

再次更新 `account_deposits`：

- `checkout_provider`
- `checkout_status`
- `checkout_url`
- `checkout_session_id`
- `checkout_expires_at`
- `provider_ref`
- `detail_json`
- `metadata_json`

### 5.4 为什么要先创建充值单，再创建 checkout

原因很直接：

- 系统需要先有内部订单号
- 再把内部订单号传给外部支付系统
- 外部回调回来时，才能通过内部订单号、provider_ref 或 checkout_session_id 找回这笔订单

这也是为什么 `account_deposits` 里会存：

- `provider_ref`
- `checkout_session_id`

### 5.5 出问题排查顺序

#### 情况 1：前端点了充值或购买套餐，但后台没有单

先查：

- `account_deposits` 是否有新记录

如果没有：

- 大概率在 `CreateDeposit(...)` 前就失败了

#### 情况 2：有支付订单，但页面没有跳转地址

先看：

- `account_deposits.checkout_url`
- `account_deposits.checkout_session_id`
- `account_deposits.checkout_provider`

如果这些为空：

- 说明 `prepareCheckout(...)` 失败
- 或 `UpdateDepositCheckout(...)` 没写进去

#### 情况 3：回调回来了，但找不到充值单

优先查：

- `provider_ref`
- `checkout_session_id`

以及内存索引：

- `depositByProviderRef`
- `depositByCheckoutSessionID`

## 6. 在线充值成功流程

代码入口：

- `handleCheckoutWebhook(...)`
- `applyCheckoutEvent(...)`
- `reconcilePendingCheckoutDeposit(...)`
- `accounts.Service.SettleDeposit(...)`

### 6.1 什么时候真正加余额

不是创建充值单的时候。

真正加余额是在：

- 手工确认到账
- 第三方支付 webhook 确认成功
- 第三方支付主动查单补偿确认成功

最终都会走：

- `SettleDeposit(...)`

微信支付成功确认以异步回调为主，主动查单只是补偿路径。两条路径都会生成同一种 checkout event，并走同一套金额校验和 `SettleDeposit(...)`。微信优惠/满减时，回调或查单结果里的 `amount.payer_total` 可能低于订单金额；系统校验使用 `amount.total` 对比 `account_deposits.amount`，并把 `wechat_pay_payer_total` 写入 `detail_json` 作为审计字段。支付宝校验使用 `total_amount` 对比 `account_deposits.amount`，不使用优惠后的买家实付或商家实收字段做订单金额匹配。

### 6.2 `SettleDeposit(...)` 做了什么

按顺序：

1. 找到充值单
2. 校验未结算
3. 找到用户钱包
4. 生成一条 wallet ledger
5. 更新钱包余额
6. 更新充值单状态为 `settled`
7. 记录 `settlement_ref`、`provider_ref`
8. 把 `ledger_entry_id` 写回充值单

### 6.3 会写哪些表

按当前实现顺序写：

1. `account_wallets`
2. `account_wallet_ledger`
3. `account_deposits`

其中：

- `account_wallets`：余额变化
- `account_wallet_ledger`：资金流水
- `account_deposits`：订单状态变化与关联流水号

### 6.4 事务和顺序

账户服务仍然先在内存锁内计算新状态，再持久化。生产 SQL store 下，`SettleDeposit(...)` 这类资金多表写入会通过账户层批量持久化放进一个数据库事务里提交：

- `SaveWallet`
- `SaveLedger`
- `SaveDeposit`

这三个写入在 SQL 模式下要么一起成功，要么一起回滚。文件 store 仍按顺序写文件，只用于本地开发/测试，不作为生产资金一致性的依据。

### 6.5 套餐 checkout 的补偿逻辑

套餐购买和普通充值都先落 `account_deposits`。支付回调结算后：

- 普通充值：只完成钱包入账和充值单结算
- 套餐购买：先让充值单结算到账，再扣除同等 CNY 余额并创建 `account_subscriptions`

如果异常发生在“充值单已结算、套餐还没创建”之间，后续重复 webhook/mock/admin settle 会检查 `source_deposit_id`。只要没有找到对应 subscription，就会继续执行套餐发放；如果已经发放，则直接按幂等成功处理，不会重复创建套餐。

### 6.6 发生异常时怎么盘点

如果怀疑充值有问题，建议按这个顺序查：

1. `account_deposits`
2. `account_wallet_ledger`
3. `account_wallets`

看三者是否对应：

- 充值单是否 `settled`
- `ledger_entry_public_id` 是否存在
- ledger 的 `order_public_id` 是否等于该充值单 ID
- 钱包余额是否已经包含该金额

如果三者不一致，说明发生了“部分写成功”。

## 7. 后台手工余额调整流程

代码入口：

- `accounts.Service.CreditWallet(...)`
- `accounts.Service.DebitWallet(...)`

### 7.1 会写哪些表

按顺序：

1. `account_wallets`
2. `account_wallet_ledger`

不会写 `account_deposits`。

### 7.2 为什么

补款和扣款本质都不是充值单成功，而是后台人工直接改钱包余额。

所以：

- 它应当有资金流水
- 但不一定对应充值订单
- 扣款输入仍是正数金额，账本方向为 `debit`，余额不足时拒绝，不允许扣成负数

### 7.3 识别方式

通过：

- `reason_code = admin_topup`
- `reason_code = admin_adjustment`

以及后台审计日志：

- `admin_audit_logs`

## 8. 注册用户步态序列解析扣费流程

代码入口：

- [internal/sequences/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/sequences/service.go) `ensureRegisteredPayment(...)`

### 8.1 业务时序

当注册用户发起步态序列解析时：

1. 如果没有账单，就先创建序列账单
2. 任务状态切到 `awaiting_payment`
3. 先保存任务
4. API 进程调用 `accounts.ChargeWallet(...)`
5. 扣费成功后，把账单标记为 `paid`
6. 再保存任务
7. 后续进入 `processing`
8. 解析成功后额外写入 `<data_dir>/sequence_samples/<YYYY-MM-DD>/user/<user_id>/<task_id>/`

### 8.2 账户层写哪些表

扣费发生时，账户层会写：

1. `account_wallets`
2. `account_wallet_ledger`

ledger 关键字段：

- `direction = debit`
- `reason_code = sequence_once`
- `task_public_id = task.TaskID`
- `order_public_id = task.Billing.OrderID`

扣费幂等依赖稳定的 `order_public_id + reason_code`。SQL 模式启动时不会全量加载历史
`account_wallet_ledger`，所以 `ChargeWallet(...)` 会先按
`user_id + order_id + reason_code + direction=debit` 查询数据库历史流水；查到后直接返回
既有 ledger，不再修改钱包余额，也不再写第二条扣费流水。所有注册用户扣费入口都必须传入
稳定 `OrderID`，包括视频一期/二期、步态序列、Gait Pose、图搜万物、套餐购买和续费。

### 8.3 样本归档写哪些文件

步态序列解析成功后，服务端会额外保存一份样本，不写数据库表：

- `frames/*.jpg`：用户上传的原始序列帧
- `metadata.json`：用户、任务、账单、归档时间等元数据
- `result.json`：完整步态序列解析结果

这份归档不参与任务 TTL 清理。管理人员可以直接从磁盘拷贝用于算法训练，也可以手工删除。

注册用户归档的 `metadata.json` 会包含用户邮箱/名称、API Key ID/名称/前缀/哈希、认证方式、请求 IP/User-Agent/request_id/Agent 请求头、任务创建时间和归档时间。完整 API Key 不写入归档目录。

匿名调用的目录按匿名付款主体区分：

```text
<data_dir>/sequence_samples/<YYYY-MM-DD>/anonymous/<anonymous_owner_id>/<task_id>/
```

如果 x402 收据里有 `payer_address`，`anonymous_owner_id` 会优先由 `network + payer_address` 生成；否则回退到 `settlement_ref`。

匿名归档的 `metadata.json` 会包含付款钱包地址、网络、代币合约、代币符号、结算引用、请求 IP/User-Agent/request_id/Agent 请求头、任务创建时间和归档时间。路径里的 `<anonymous_owner_id>` 是哈希标识，不直接暴露钱包地址。

### 8.3 任务层写哪些表

每次 `saveTaskLocked(...)` 在 SQL 模式下会写：

1. `tasks`
2. `sequence_tasks`
3. `billing_orders`
4. `payments`
5. `task_events`

但要注意：

- 注册用户钱包扣费时，不会新增独立第三方支付凭证
- `payments` 是否有记录，取决于仓库层是否从账单状态推导出 settlement 信息
- 当前项目里若 `SettlementRef` 是钱包 ledger id，例如 `led_xxx`，则会被推断为 `wallet` 协议

### 8.4 为什么先把任务保存成 `awaiting_payment`

这是合理的。

原因：

- 如果直接扣费失败，任务状态仍然有痕迹
- 可以明确知道失败发生在支付前
- 对后续前端提示、后台排障更友好

### 8.5 风险点

这里也不是一个完整数据库事务。

可能出现：

- 任务已保存为 `awaiting_payment`
- 但扣费失败

这本身不是错误，而是有意保留状态。

真正要小心的是另一种情况：

- 钱包已经扣费成功
- 但第二次 `saveTaskLocked(...)` 失败

这样会出现：

- 账户余额减少了
- ledger 也写了
- 但任务账单还没变成 `paid`

### 8.6 排查顺序

先查：

1. `account_wallet_ledger`
2. `account_wallets`
3. `sequence_tasks.metadata_json`
4. `billing_orders`
5. `task_events`

重点看：

- ledger 是否有 `reason_code = sequence_once`
- 任务账单是否已经 `paid`
- 是否有 `payment_confirmed`

## 9. 注册用户视频解析一期扣费流程

代码入口：

- [internal/videos/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/videos/service.go) `ensureRegisteredPhase1Payment(...)`

### 9.1 时序

视频上传完成后：

1. 创建一期账单 `Phase1`
2. 任务状态切到 `awaiting_payment_1`
3. 保存任务
4. API 进程调用 `accounts.ChargeWallet(...)`
5. 成功后把 `Phase1` 标记为 `paid`
6. 任务状态改回 `uploaded`
7. 保存任务
8. 如果开启自动处理，则启动 `ProcessTask(...)`

### 9.2 账户层写哪些表

1. `account_wallets`
2. `account_wallet_ledger`

ledger 关键字段：

- `reason_code = video_phase1`
- `task_public_id = task.TaskID`
- `order_public_id = task.Billing.Phase1.OrderID`

### 9.3 任务层写哪些表

保存任务时会同步写：

1. `tasks`
2. `video_tasks`
3. `billing_orders`
4. `payments`
5. `task_events`

### 9.4 为什么扣完费后状态改回 `uploaded`

因为当前视频服务把：

- `awaiting_payment_1`

视为“待付费状态”，而不是“真正可处理状态”。

一期支付成功后，业务会回到：

- 已上传、可进入处理

然后 worker 再把它推进到：

- `processing`

### 9.5 风险点

与序列一致，存在“扣费成功但任务状态持久化失败”的部分成功风险。

排查时要同时看：

- 钱包流水
- 视频任务状态
- 一期账单状态
- 任务事件

## 10. 注册用户视频二期扣费流程

代码入口：

- [internal/videos/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/videos/service.go) `ensureRegisteredPhase2Payment(...)`

### 10.1 时序

当视频已解析完成，但还没放出结果时：

1. 任务状态应为 `succeeded_awaiting_payment_2`
2. API 进程调用 `accounts.ChargeWallet(...)`
3. 扣费成功后，把 `Phase2` 标记为 `paid`
4. 任务状态改成 `succeeded`
5. 保存任务

### 10.2 写哪些表

账户层：

1. `account_wallets`
2. `account_wallet_ledger`

任务层：

1. `tasks`
2. `video_tasks`
3. `billing_orders`
4. `payments`
5. `task_events`

### 10.3 为什么二期收费放在结果释放前

因为产品定义就是：

- 先按视频帧数收一期
- 获取结果时，再按序列结果规模收二期

所以二期账单必须建立在：

- 解析结果已经产出
- 已知 `sequence_count`
- 已知 `total_sequence_frames`

的前提下。

## 11. public 序列支付流程

代码入口：

- `parseTask(...)` 创建待支付账单
- `SettlePublic(...)` 完成 public 支付确认

### 11.1 第一次保存任务

public 调用方第一次调用解析，但还未支付时：

1. 创建 `sequence_once` 账单
2. 任务状态切到 `awaiting_payment`
3. 保存任务
4. 返回 `payment_required`

这一步会写：

1. `tasks`
2. `sequence_tasks`
3. `billing_orders`
4. `task_events`

### 11.2 支付确认时

`SettlePublic(...)` 会：

1. 校验状态仍为 `awaiting_payment`
2. 调用 `payment.Verify(...)`
3. 做支付回放保护 `replay.CheckAndRecord(...)`
4. 标记账单 `paid`
5. 填充 `settled_at`
6. 填充 `settlement_ref`
7. 记录 `payment_protocol`
8. 再保存任务

### 11.3 会写哪些表

保存任务时同步写：

1. `tasks`
2. `sequence_tasks`
3. `billing_orders`
4. `payments`
5. `task_events`

这里不会写：

- `account_wallets`
- `account_wallet_ledger`

因为 public 调用方没有注册用户钱包体系。

### 11.4 为什么 `payments` 放在仓库层同步

当前项目没有独立的支付聚合服务层统一落表，而是根据任务账单快照推导：

- 若账单已 `paid`
- 且有 `settled_at`
- 且有 `settlement_ref`

就自动同步到 `payments`

优点：

- 对现有业务改动小

缺点：

- 不是严格意义上的支付系统事实源
- 如果未来支付逻辑复杂化，这部分要抽出去

## 12. public 视频支付流程

代码入口：

- `UploadVideo(...)` 创建一期账单
- `SettlePublicPhase1(...)` 完成一期支付
- `ProcessTask(...)` 解析成功后生成二期账单
- `SettlePublicPhase2(...)` 完成二期支付

### 12.1 一期账单创建

上传成功后：

1. 视频元数据探测
2. 创建 `Phase1`
3. 任务状态改成 `awaiting_payment_1`
4. 保存任务

### 12.2 一期支付确认

`SettlePublicPhase1(...)` 会：

1. 校验仍在 `awaiting_payment_1`
2. 调用 `payment.Verify(...)`
3. 回放保护
4. 标记 `Phase1` 为 `paid`
5. 写入 `settled_at` / `settlement_ref`
6. 任务状态改回 `uploaded`
7. 保存任务
8. 触发处理

### 12.3 二期账单创建

视频处理成功后：

1. 生成结果
2. 根据结果创建 `Phase2`
3. 任务进入 `succeeded_awaiting_payment_2`
4. 保存任务

### 12.4 二期支付确认

`SettlePublicPhase2(...)` 会：

1. 校验仍在 `succeeded_awaiting_payment_2`
2. 调用 `payment.Verify(...)`
3. 回放保护
4. 标记 `Phase2` 为 `paid`
5. 任务状态改成 `succeeded`
6. 保存任务

### 12.5 会写哪些表

每次任务保存都会同步写：

1. `tasks`
2. `video_tasks`
3. `billing_orders`
4. `payments`
5. `task_events`

不会写账户钱包表。

## 13. 任务保存时 SQL 仓库到底做了什么

以 `SequenceTaskRepository.SaveTask(...)` 和 `VideoTaskRepository.SaveTask(...)` 为准。

### 13.1 写入顺序

当前 `SaveTask(...)` 在一个 SQL 事务里执行：

1. 读取旧任务快照
2. `upsertTaskCompat(...)` 写 `tasks`
3. `syncSequenceBilling(...)` / `syncVideoBilling(...)` 写 `billing_orders`
4. 如果账单已支付，则 `syncPaymentRecord(...)` 写 `payments`
5. `syncSequenceTaskEvents(...)` / `syncVideoTaskEvents(...)` 写 `task_events`
6. 最后写 `sequence_tasks` 或 `video_tasks`

### 13.2 为什么这个顺序合理

因为：

- `tasks` 是父表，先有父行，后有子行
- `billing_orders` 依赖 `tasks.id`
- `payments` 依赖 `billing_orders.id`
- `task_events` 依赖 `tasks.id`
- 子表最后更新结构化列之外的补充上下文；结构化列是事实源
- 兼容期内任务运行态账单仍从任务 JSON 的 `billing` 字段恢复，`billing_orders` 是查询、统计和对账用的结构化同步表；后续若要彻底去 JSON，需要从 `billing_orders` 重建任务 Billing

### 13.3 删除任务时做了什么

`RemoveTask(...)` 现在不是直接全删：

1. 先插入 `task_deleted` 事件
2. 删除 `sequence_tasks` / `video_tasks` 子表行
3. 父表 `tasks` 做软删除兼容更新

这样做的原因：

- 保留账单
- 保留支付记录
- 保留事件审计

## 14. `task_events` 的意义

当前 `task_events` 已经记录关键转移：

- `task_created`
- `upload_completed`
- `billing_created`
- `payment_confirmed`
- `worker_succeeded`
- `worker_failed`
- `task_expired`
- `task_deleted`

你可以把它理解成：

- 对任务 JSON 快照的一层结构化审计索引

它的作用：

- 排查状态为什么变了
- 判断某次付费是否真的发生过
- 后续做时序统计
- 后续做多机 worker 审计

## 15. 你重点要留意的“不够硬”的地方

下面这些是我认为你后面最值得重点盘点的地方。

### 15.1 账户层不是数据库事务型写法

充值、补款、扣费目前都是：

- 先改内存
- 再多次独立持久化

所以存在部分写成功风险。

最典型的问题：

- 钱包余额已变
- 流水未写
- 订单状态未更新

### 15.2 任务服务与账户服务是跨模块、非单事务

例如注册用户扣费：

- 先保存任务成 `awaiting_payment`
- 再调用账户扣费
- 再保存任务成 `paid`

所以可能出现：

- 钱已经扣了
- 但任务账单状态还没更新

### 15.3 `payments` 当前是仓库层推导同步

它不是由独立支付聚合服务统一落库，而是从账单状态推导出来的。

这种设计短期够用，但后续若支付渠道复杂化，建议升级为：

- 支付事件先落支付事实表
- 再驱动账单状态

## 16. 出问题时的排查清单

### 16.1 充值不到账

先看：

1. `account_deposits`
2. `account_wallet_ledger`
3. `account_wallets`
4. `admin_audit_logs`

### 16.2 钱扣了但任务没放行

先看：

1. `account_wallet_ledger`
2. `billing_orders`
3. `payments`
4. `sequence_tasks.metadata_json` 或 `video_tasks.metadata_json`
5. `task_events`

### 16.3 public 支付成功但结果拿不到

先看：

1. `billing_orders.status`
2. `payments`
3. `task_events` 是否有 `payment_confirmed`
4. 任务状态是否进入了下一阶段

### 16.4 后台统计不对

先看：

1. `account_wallet_ledger`
2. `billing_orders`
3. `payments`
4. `task_events`
5. `admin_stats_snapshots`

## 17. 我对当前设计的判断

### 17.1 合理的地方

- 任务状态机清晰
- SQL 仓库把任务、账单、支付、事件串起来了
- `task_events` 的方向是对的
- 父任务软删除保留审计是合理的
- 匿名支付与注册用户钱包模式拆分清楚

### 17.2 需要继续增强的地方

最主要是两点：

1. 账户资金写入需要数据库事务化
2. 任务状态推进和账户扣费之间，需要更强的一致性设计

如果后面你准备做更严肃的生产化，我建议优先把这两点补掉。

## 18. API Key 生命周期

代码入口：

- [internal/httpapi/handlers/users/handler.go](/home/watrix/tiandk/agent/gaitAgent/internal/httpapi/handlers/users/handler.go) `handleAPIKeys(...)`
- [internal/httpapi/handlers/users/handler.go](/home/watrix/tiandk/agent/gaitAgent/internal/httpapi/handlers/users/handler.go) `handleAPIKeyItem(...)`
- [internal/accounts/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/accounts/service.go) `CreateAPIKey(...)`
- [internal/accounts/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/accounts/service.go) `PauseAPIKey(...)`
- [internal/accounts/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/accounts/service.go) `ResumeAPIKey(...)`
- [internal/accounts/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/accounts/service.go) `DeleteAPIKey(...)`

### 18.1 创建 API Key

用户创建 API Key 时：

1. handler 校验 session
2. 调用 `accounts.CreateAPIKey(...)`
3. 账户服务生成明文 secret
4. 内存中保存 `key_hash`、`key_prefix`、`status`
5. 持久化 `account_api_keys`
6. 响应里返回完整明文 secret

实际只写：

- `account_api_keys`

关键字段：

- `public_id`
- `user_public_id`
- `key_prefix`
- `key_hash`
- `secret`
- `name`
- `status`
- `metadata_json`

为什么要把明文 secret 持久化：

- 当前用户门户要求创建后能完整展示历史 API Key
- 所以实现不是“只存 hash 不可逆”，而是“存 hash + 存 secret”

这点对安全设计有直接影响。

### 18.2 暂停 / 恢复 API Key

暂停、恢复都只会：

1. 找到用户自己的 key
2. 修改内存对象里的 `status`
3. 覆盖写回 `account_api_keys`

不会写其他表。

### 18.3 删除 API Key

删除不是物理删除，而是逻辑删除：

1. `status = deleted`
2. `secret = ""`
3. `revoked_at = now`
4. 覆盖写回 `account_api_keys`

这样做的原因：

- 保留历史引用关系
- 旧 ledger / task detail 里仍可能引用这个 key id
- 后台统计还能看到曾经存在过几把 key

### 18.4 认证时又发生了什么

`Authenticate(...)` 成功后还会再写一次 `account_api_keys`：

- 更新 `last_used_at`

所以你如果发现某把 key“能调接口，但后台最近使用时间没更新”，优先查：

- `account_api_keys.last_used_at`
- `persistAPIKeyLocked(...)` 是否报错

### 18.5 风险点

API Key 链路本身比较简单，风险主要不是一致性，而是安全性：

- 当前 secret 可持久化恢复
- 适合产品体验，但不适合更高安全等级

如果未来要收紧安全策略，建议改成：

- 数据库只保留 hash
- 门户仅在创建瞬间展示明文一次

## 19. 用户偏好更新

代码入口：

- [internal/httpapi/handlers/users/handler.go](/home/watrix/tiandk/agent/gaitAgent/internal/httpapi/handlers/users/handler.go) `handlePreferences(...)`
- [internal/accounts/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/accounts/service.go) `UpdateUserPreferences(...)`

### 19.1 会做什么

用户修改偏好时，只会更新用户主记录里的：

- `preferred_locale`
- `country_code`
- `display_currency`
- `updated_at`

### 19.2 写哪些表

只写：

- `account_users`

### 19.3 为什么偏好放在用户主表

因为这些字段会影响：

- 门户默认语言
- 默认支付方式候选
- 默认展示币种

都属于用户画像的一部分，不值得单独拆子表。

### 19.4 排查入口

如果你发现页面展示语言或支付候选不符合预期，优先看：

1. `account_users.preferred_locale`
2. `account_users.country_code`
3. `account_users.display_currency`
4. 请求头里的 `Accept-Language`
5. 中间件注入的 `trafficmeta`

因为前端最终看到的是：

- 用户存储偏好
- 请求上下文推断值

两者综合后的结果。

## 20. 运行时配置读取、更新与热生效

代码入口：

- [internal/admincfg/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/admincfg/service.go)
- [internal/runtimeconfig/store.go](/home/watrix/tiandk/agent/gaitAgent/internal/runtimeconfig/store.go)
- [internal/runtimeconfig/sql_backend.go](/home/watrix/tiandk/agent/gaitAgent/internal/runtimeconfig/sql_backend.go)
- [internal/app/api.go](/home/watrix/tiandk/agent/gaitAgent/internal/app/api.go)
- [internal/app/worker.go](/home/watrix/tiandk/agent/gaitAgent/internal/app/worker.go)

### 20.1 配置的事实源是什么

当前运行时配置只有一个逻辑键：

- `runtime`

在 SQL 模式下写入：

- `runtime_configs.config_key = 'runtime'`

实际配置体保存在：

- `runtime_configs.metadata_json`

其中包含：

- retention payload
- pricing payload
- updated_at

### 20.2 管理员修改配置时会发生什么

`PUT /v1/admin/runtime-config` 时，按顺序：

1. handler 先读取旧配置 `before`
2. `admincfg.Service.UpdateRuntimeConfig(...)` 把请求解析成 retention/pricing policy
3. 同时解析免注册试用额度、包月套餐、报表、支付和 图搜万物转发配置
4. 先把新 policy 应用到内存中的 sequence service
5. 再应用到内存中的 video service
6. 最后 `runtimeStore.Save(...)` 持久化到 `runtime_configs`
7. handler 再写一条后台审计

### 20.3 写哪些表

这一条链路会写：

1. `sequence_tasks` / `video_tasks` / `tasks` / `billing_orders` / `task_events`
2. `runtime_configs`
3. `admin_audit_logs`

这里很多人会漏掉第 1 组表。

原因是：

- `UpdatePolicy(...)` 不是只改全局配置
- 它会遍历当前所有任务
- 重新计算 `expire_at` / `delete_after_at`
- 然后把每个任务重新保存一遍

### 20.4 为什么先改任务，再存配置

当前实现选择的是“先让运行中的业务对象生效，再持久化全局配置”。

优点：

- 修改接口返回前，当前进程已按新策略工作

缺点：

- 如果任务批量重写成功了一部分，但 `runtime_configs` 保存失败
- 可能出现“任务已经按新策略刷新，但全局配置表还是旧值”

这是当前配置链路最主要的一致性风险。

### 20.5 API 进程和 worker 怎么热加载

除了管理员显式更新外：

- API 进程每 `30s` 调一次 `runtimeStore.Load(...)`
- worker 进程每 `30s` 也调一次 `runtimeStore.Load(...)`

如果发现新旧 policy 不一样，就会：

- `UpdatePolicy(...)`
- `UpdatePricing(...)`

所以当前是：

- 管理端写一次
- API 和 worker 最迟 30 秒内感知

### 20.6 排查入口

如果你发现“页面显示配置已保存，但任务清理时长没生效”，建议按这个顺序查：

1. `runtime_configs`
2. API 进程日志中的 `api refresh ... runtime retention failed`
3. worker 进程日志中的 `worker refresh runtime retention failed`
4. 某条任务在 `tasks` / `video_tasks` / `sequence_tasks` 里的 `expire_at`、`delete_after_at`

## 21. 后台审计日志

代码入口：

- [internal/adminaudit/store.go](/home/watrix/tiandk/agent/gaitAgent/internal/adminaudit/store.go)
- [internal/adminaudit/sql_backend.go](/home/watrix/tiandk/agent/gaitAgent/internal/adminaudit/sql_backend.go)
- [internal/httpapi/handlers/admin/handler.go](/home/watrix/tiandk/agent/gaitAgent/internal/httpapi/handlers/admin/handler.go) `appendAuditRecord(...)`

### 21.1 什么动作会写审计

当前已接入审计的后台动作包括：

- 管理员创建用户
- 管理员为用户补款
- 管理员确认充值到账
- 修改运行时计费与清理配置
- 删除视频任务
- 删除序列任务

这些动作最终都调用：

- `appendAuditRecord(...)`

### 21.2 写哪些表

只写：

- `admin_audit_logs`

关键字段：

- `audit_id`
- `created_at`
- `action`
- `target_type`
- `target_id`
- `target_label`
- `summary`
- `actor_user_id`
- `actor_email`
- `actor_name`
- `actor_auth_method`
- `detail_json`
- `request_meta_json`
- `metadata_json`

### 21.3 为什么要同时存 detail 和 metadata

当前实现里：

- `detail_json` 是结构化列之外的业务细节
- `request_meta_json` 是 IP、UA、地域等请求信息
- `metadata_json` 是结构化列之外的补充上下文

这和任务表的 `metadata_json` 思路一致：

- 结构化列用于过滤
- metadata 用于保底回放上下文
- 已经有结构化列的字段不再重复写入 JSON

### 21.4 需要注意的地方

后台审计不是事务性挂靠在业务写入上。

比如管理员补款：

1. 先完成钱包写入
2. handler 再调用 `appendAuditRecord(...)`

所以可能出现：

- 钱包已经补成功
- 但 `admin_audit_logs` 没写进去

这不影响业务事实，但会影响追责与运维盘点。

## 22. 后台统计采样与图表数据

代码入口：

- [internal/app/api.go](/home/watrix/tiandk/agent/gaitAgent/internal/app/api.go) `sampleAdminStats(...)`
- [internal/adminstats/store.go](/home/watrix/tiandk/agent/gaitAgent/internal/adminstats/store.go)
- [internal/adminstats/sql_backend.go](/home/watrix/tiandk/agent/gaitAgent/internal/adminstats/sql_backend.go)
- [internal/adminstats/sql_summary.go](/home/watrix/tiandk/agent/gaitAgent/internal/adminstats/sql_summary.go)
- [internal/httpapi/handlers/admin/handler.go](/home/watrix/tiandk/agent/gaitAgent/internal/httpapi/handlers/admin/handler.go) `handleTimeseries(...)`

### 22.1 统计快照什么时候产生

API 进程启动时会先采一次。

之后每 `30s`：

1. 刷新运行时配置
2. 清理过期任务
3. 调 `sampleAdminStats()`

### 22.2 优先用什么数据源

如果配置了数据库，优先走：

- `adminstats.SQLSummary`

也就是直接聚合 SQL 表：

- `account_users`
- `account_wallet_ledger`
- `account_deposits`
- `video_tasks`
- `sequence_tasks`
- `billing_orders`
- `payments`

如果 SQL 聚合失败，才退回：

- 从内存 service 组装 snapshot

### 22.3 写哪些表

采样成功后写：

- `admin_stats_snapshots`

字段很简单：

- `snapshot_at`
- `metadata_json`

### 22.4 图表接口怎么取数

`GET /v1/admin/timeseries?range=24h|7d|30d|...` 时：

1. 从 `admin_stats_snapshots` 读快照
2. 按时间窗口过滤
3. 按 step 做 compact
4. 返回 points 和 legends

管理后台前端再按横轴单位把 points 聚合为天、周或月。当前运营看板只展示业务量、每日确认收入和用户活跃图，不展示区间累计收入图；图表保留悬停提示和拖拽查看窗口，鼠标滚轮不改变图表缩放范围。

图里不同颜色对应的“图例文字”，就是由：

- `sortedKeysFromPoints(...)`

从快照里的动态指标名推出来的。

### 22.5 为什么要先采样再查图表

因为很多系统指标：

- CPU load
- 内存使用率
- 磁盘使用率
- worker 在线状态

都是瞬时值，不适合靠实时 SQL 回放历史。

所以必须先定时采样，再供图表查询。

### 22.6 排查入口

如果你看到看板数值不对，优先分 2 类查：

#### 实时概览不对

先看：

1. `adminstats.SQLSummary` 聚合逻辑
2. 底层表是否已写入

运营中心当前同样由 `adminstats.SQLSummary` 直接聚合底层事实表，主要读取：

- `account_users`
- `usage_records`
- `account_deposits`
- `account_wallets`
- `account_wallet_ledger`
- `video_tasks`
- `sequence_tasks`

如果运营漏斗或最近事件不对，先确认对应业务是否已经写入这些事实表。后续如果需要更精细的首页访问、按钮点击、邮件触达等行为，再增加独立运营事件表。

#### 时间序列不对

先看：

1. `admin_stats_snapshots`
2. API 进程采样日志
3. `rangeConfig(...)` 的时间窗口与 step

## 23. worker 轮询推进视频任务

代码入口：

- [internal/worker/runner.go](/home/watrix/tiandk/agent/gaitAgent/internal/worker/runner.go)
- [internal/videos/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/videos/service.go) `ProcessPending(...)`
- [internal/videos/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/videos/service.go) `ProcessTask(...)`

### 23.1 每个 worker tick 做什么

每次 tick：

1. `video.ProcessPending(ctx)`
2. `seq.CleanupExpired(...)`
3. 打一条 `worker tick` 日志

其中视频推进是关键路径，序列只做清理，不做解析。

### 23.2 `ProcessPending(...)` 会做什么

按顺序：

1. 先 `CleanupExpired(...)`
2. 列出所有视频任务
3. 找到 `status == uploaded` 的任务
4. 逐个调用 `ProcessTask(...)`

也就是说：

- 真正进入 SDK 处理队列的唯一前置条件是 `uploaded`

### 23.3 `ProcessTask(...)` 的详细时序

1. 先创建文件锁，避免同一任务并发处理
2. 重新加载任务
3. 再次确认状态还是 `uploaded`
4. 立即保存成 `processing`
5. 获取本地视频路径
6. 调 `engine.StartVideo(...)`
7. 循环调用 `GetVideoProgress(...)`
8. 周期性把 `progress_percent` 写回库
9. 处理完成后调 `GetVideoResult(...)`
10. 持久化步态图、人脸图等资产
11. 生成结果对象
12. 如果需要二期收费，则创建 `Phase2`，状态置为 `succeeded_awaiting_payment_2`
13. 否则直接置为 `succeeded`
14. 最后保存任务

### 23.4 这一条链路写哪些表

每次状态推进都会反复写：

1. `tasks`
2. `video_tasks`
3. `billing_orders`
4. `payments`
5. `task_events`

其中最常见的事件是：

- `worker_succeeded`
- `worker_failed`
- `billing_created`

### 23.5 为什么视频任务单独放到 worker

不是为了代码分层好看，而是为了隔离这些运行风险：

- SDK 初始化失败
- GPU/动态库/加密狗问题
- 长时间处理阻塞
- 进程崩溃影响公网 API

### 23.6 排查入口

如果你发现“视频一直 uploaded 不处理”，优先查：

1. worker 是否在运行
2. `worker tick` 日志是否持续打印
3. `video_tasks.status`
4. 是否存在锁文件 `video_locks/<task>.lock`
5. SDK `StartVideo` 是否报错

## 24. 视频任务的创建、上传、成功、删除、清理

代码入口：

- [internal/videos/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/videos/service.go)

视频任务的临时对象数据保存在对象存储根目录下。当前线上 `GAIT_DATA_DIR=/data/gaitagent` 且未设置 `GAIT_OBJECT_STORE_ROOT`，所以根目录是 `/data/gaitagent/objects`。

视频相关 object key 主要是：

```text
objects/videos/<video_task_id>/...
objects/video-assets/<video_task_id>/...
```

这些文件会随任务删除或 TTL 清理被删除；长期样本归档在 `/data/gaitagent/sequence_samples`，不属于这里。

### 24.1 创建任务

创建视频任务时：

1. 生成 task id、upload token、asset token
2. 构造 object key
3. 状态设为 `created`
4. `applyLifecycle(...)` 计算 `expire_at`
5. 保存任务

这时会写：

- `tasks`
- `video_tasks`
- `task_events`

### 24.2 上传视频

上传完成时：

1. 先写对象存储
2. 任务改成 `uploaded`
3. 探测帧数、fps、duration
4. 如果是公开任务或注册用户任务，生成一期账单，状态改成 `awaiting_payment_1`
5. 保存任务

这里对象存储和数据库不是事务关系，所以可能出现：

- 文件已上传成功
- 但任务状态没更新

### 24.3 处理成功

成功后：

- 结果资产先写对象存储
- 再写任务状态与结果快照

所以也可能出现：

- 图片资产已经生成
- 但数据库里还没切到 `succeeded`

### 24.4 删除任务

管理员或用户主动删除时：

1. 先删上传视频和资产文件
2. 再把任务状态改成 `deleted`
3. 保存任务

这里不是直接删库记录。

真正物理移除记录发生在后续清理阶段。

### 24.5 定时清理

清理由后台循环触发，不依赖用户请求：

- API 进程启动后每 30 秒执行一次 runtime 配置刷新和任务清理：
  - `sequence.CleanupExpired(time.Now().UTC())`
  - `video.CleanupExpired(context.Background())`
- API 进程每天最多执行一次验证码清理，删除 `created_at` 早于 90 天的 `email_verification_codes` 和 `sms_verification_codes`
- Worker 进程按 `GAIT_WORKER_POLL_INTERVAL` 只处理待执行任务，不参与任务 TTL 清理、验证码清理或资金清理
- Worker 进程另有 30 秒 runtime 配置刷新循环，用于同步 TTL、价格和并发配置

`CleanupExpiredAt(...)` 会：

1. 先清 replay 收据
2. 对已过期任务转 `expired`
3. 对应删资产的任务转 `deleted`
4. 对已经到 `delete_after_at` 的任务，删除上传文件和结果资产，清空完整结果 JSON、上传 URL、token、资产索引等大字段
5. 任务记录继续保留为轻量摘要，供后台任务管理和财务/审计关联使用

轻量摘要保留任务 ID、状态、创建/更新时间、归属用户/API Key、调用方式、视频元信息或上传统计、计费信息等小字段。摘要不保留原始上传对象 key、上传 URL、访问 token、结果资产索引和完整解析结果 JSON。

当前线上 `GAIT_DATA_DIR=/data/gaitagent` 时：

- 原始上传和结果资产位于 `/data/gaitagent/objects/...`，属于任务生命周期数据，会被 TTL 清理
- 长期样本归档位于 `/data/gaitagent/sequence_samples/...`，由解析成功时额外拷贝生成，不参与任务 TTL 自动清理，需要管理员手动管理

## 25. 序列任务的创建、上传、解析、删除、清理

代码入口：

- [internal/sequences/service.go](/home/watrix/tiandk/agent/gaitAgent/internal/sequences/service.go)

序列任务的临时对象数据同样保存在对象存储根目录下：

```text
objects/sequences/<sequence_task_id>/...
objects/sequence-assets/<sequence_task_id>/...
```

其中 `objects/sequences` 是用户上传的序列帧，`objects/sequence-assets` 是解析后对外暴露的 gait image、face image 等结果资产。这些文件会随任务删除或 TTL 清理被删除。

### 25.1 创建任务

创建序列任务时：

1. 生成多帧上传目标
2. 状态设为 `created`
3. 计算上传过期时间
4. 保存任务

### 25.2 上传帧

每上传一帧：

1. 先把图片写对象存储
2. 再把该帧 `uploaded = true`
3. 保存任务

只有最后一帧也完成后，SQL 事件层才会生成：

- `upload_completed`

### 25.3 解析

解析时：

1. 校验帧顺序
2. 从对象存储读取每帧
3. 必要时先完成支付
4. 保存成 `processing`
5. 调 SDK 或 worker sequence engine
6. 结果资产先写对象存储
7. 任务改成 `succeeded`
8. 保存任务

### 25.4 删除与清理

和视频类似：

- 主动删除先删对象，再改状态
- 定时清理最后才物理移除记录

### 25.5 排查入口

如果你看到“上传都成功了，但 parse 说帧不完整”，优先查：

1. `sequence_tasks.uploaded_frame_count`
2. `metadata_json.uploads[].uploaded`
3. 对象存储里对应 object key 是否真的存在

## 26. 后台登录与授权

代码入口：

- [internal/httpapi/handlers/admin/handler.go](/home/watrix/tiandk/agent/gaitAgent/internal/httpapi/handlers/admin/handler.go)

### 26.1 不是独立管理员账户体系

当前后台登录复用普通账户体系：

1. 先调用 `accounts.Login(...)`
2. 拿到 session token
3. 再检查邮箱是否在 `adminEmails`
4. 通过后写管理员 cookie `gait_admin_session`

或者直接使用：

- `Authorization: Bearer <admin token>`

### 26.2 写哪些表

后台登录本身：

- 不写数据库
- 只写内存 session

所以管理后台和用户门户一样，也不具备跨实例共享 session 能力。

### 26.3 为什么要特别写在这里

因为它影响你后面判断很多现象：

- API 重启后后台登录失效是正常的
- 多实例部署后台登录不同步也是正常的
- 这不是数据库坏了，而是当前设计就没把 session 落库

## 27. 表写入责任矩阵

下面这张表是从“谁负责写、什么时候写、是否幂等、是否事务内”来总结当前实现。

### 27.1 账户侧表

- `account_users`
  - 负责模块：`accounts.Service` / `sqlAccountStore`
  - 触发时机：注册、修改用户偏好
  - 幂等性：`public_id` upsert，基本幂等
  - 事务性：否

- `account_api_keys`
  - 负责模块：`accounts.Service` / `sqlAccountStore`
  - 触发时机：注册、创建 key、暂停、恢复、删除、认证更新时间
  - 幂等性：`public_id` upsert，基本幂等
  - 事务性：否

- `account_wallets`
  - 负责模块：`accounts.Service` / `sqlAccountStore`
  - 触发时机：充值到账、后台补款、任务扣费
  - 幂等性：按 wallet 主键覆盖写，重复调用会重放余额状态
  - 事务性：否

- `account_wallet_ledger`
  - 负责模块：`accounts.Service` / `sqlAccountStore`
  - 触发时机：充值到账、后台补款、任务扣费
  - 幂等性：以 ledger public id upsert，单条记录幂等
  - 事务性：否

- `account_deposits`
  - 负责模块：`accounts.Service` / `sqlAccountStore`
  - 触发时机：创建充值单、创建 checkout、充值成功
  - 幂等性：按 deposit public id upsert
  - 事务性：否

### 27.2 任务侧表

- `tasks`
  - 负责模块：`sqlrepo` 的 task compat 同步
  - 触发时机：每次 sequence/video `SaveTask(...)`
  - 幂等性：按 `public_id` upsert
  - 事务性：是，在任务仓库事务内

- `sequence_tasks`
  - 负责模块：`SequenceTaskRepository`
  - 触发时机：每次序列任务保存
  - 幂等性：按 `public_id` update/insert
  - 事务性：是

- `video_tasks`
  - 负责模块：`VideoTaskRepository`
  - 触发时机：每次视频任务保存
  - 幂等性：按 `public_id` update/insert
  - 事务性：是

- `billing_orders`
  - 负责模块：`syncSequenceBilling` / `syncVideoBilling`
  - 触发时机：任务账单变化时
  - 幂等性：按 `(task_id, phase)` upsert
  - 事务性：是

- `payments`
  - 负责模块：`syncPaymentRecord(...)`
  - 触发时机：账单进入 paid 且有 settlement 信息时
  - 幂等性：先删后插，同 order 幂等
  - 事务性：是

- `task_events`
  - 负责模块：`sync*TaskEvents(...)`
  - 触发时机：建任务、上传完成、账单创建、支付成功、成功、失败、过期、删除
  - 幂等性：弱，重复保存可能重复事件，依赖前后状态判断尽量避免
  - 事务性：是

### 27.3 后台侧表

- `runtime_configs`
  - 负责模块：`runtimeconfig.Store`
  - 触发时机：后台保存运行时配置
  - 幂等性：按 `config_key` upsert
  - 事务性：否

- `admin_audit_logs`
  - 负责模块：`adminaudit.Store`
  - 触发时机：后台关键操作后
  - 幂等性：按 `audit_id` 唯一，调用方通常不重试
  - 事务性：否

- `admin_stats_snapshots`
  - 负责模块：`adminstats.Store`
  - 触发时机：API 周期采样
  - 幂等性：按 `snapshot_at` upsert
  - 事务性：单条写入，不和业务事务绑定

## 28. 当前实现与理想实现的主要差异

这一节专门回答“现在这样做是为了快落地，还是本来就应该这样设计”。

### 28.1 账户资金链路

当前实现：

- 账户服务内存更新后逐表写库

理想实现：

- 钱包、流水、充值单在一个数据库事务里提交

### 28.2 任务扣费一致性

当前实现：

- 任务状态保存和钱包扣费分两段完成

理想实现：

- 引入更明确的支付/扣费事件表
- 或使用本地事务 + outbox

### 28.3 支付事实源

当前实现：

- `payments` 是从账单状态反推同步出来的

理想实现：

- 先落独立支付事实，再驱动账单状态

### 28.4 session 管理

当前实现：

- session 只在内存

理想实现：

- Redis 或数据库共享 session

### 28.5 配置热生效

当前实现：

- 先改运行中任务，再存全局配置

理想实现：

- 全局配置变更与任务批量刷新有更强的一致性控制

## 29. 建议的项目级排障顺序

如果你以后遇到问题，又一时不确定从哪里切入，我建议按下面的顺序查。

### 29.1 先分清是哪一类问题

- 账户资金问题
- 任务状态问题
- 支付确认问题
- 配置热生效问题
- 后台统计问题
- SDK / worker 运行问题

### 29.2 账户资金问题

按顺序查：

1. `account_deposits`
2. `account_wallet_ledger`
3. `account_wallets`
4. `admin_audit_logs`

### 29.3 任务状态问题

按顺序查：

1. `tasks`
2. `video_tasks` 或 `sequence_tasks`
3. `billing_orders`
4. `payments`
5. `task_events`

### 29.4 配置和统计问题

按顺序查：

1. `runtime_configs`
2. `admin_stats_snapshots`
3. API/worker 日志

### 29.5 SDK 或 worker 问题

按顺序查：

1. worker 进程是否在运行
2. SDK 初始化日志
3. 任务是否卡在 `uploaded`
4. 锁文件是否残留
5. `task_events` 是否只停在 `upload_completed`
