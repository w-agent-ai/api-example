# 数据库字典与字段说明

本文档说明当前项目中各个数据库表、各个字段分别是什么意思，以及它们在当前实现中的实际角色。

这份文档的目标不是讲业务流程，而是回答下面这些问题：

- 这个库里一共有多少张表
- 每张表是干什么的
- 每个字段的业务含义是什么
- 哪些表是当前真实在写
- 哪些表更偏规范化设计、兼容层或预留表
- 金额、时间、状态这些字段应该怎么理解

相关事实来源：

- 真实迁移文件：`db/migrations/*.up.sql`
- 当前 SQL 持久化实现：`internal/repository/sqlrepo/*`
- 当前账户 SQL 持久化实现：`internal/accounts/sql_store.go`
- 运行配置/审计/统计 SQL 实现：
  - `internal/runtimeconfig/sql_backend.go`
  - `internal/adminaudit/sql_backend.go`
  - `internal/adminstats/sql_backend.go`

如果你要看“什么时候写这些表、先写什么后写什么、为什么这样写、出问题怎么查”，再看：

- [dataflow.md](/home/watrix/tiandk/agent/gaitAgent/docs/dataflow.md)

## 1. 先看总览

当前项目里实际存在 2 套表体系：

### 1.1 早期规范化表体系

这批表主要来自：

- `000001_init.up.sql`

包括：

- `users`
- `api_keys`
- `wallets`
- `wallet_ledger`
- `tasks`
- `video_tasks`
- `sequence_tasks`
- `task_assets`
- `task_results`
- `pricing_policies`
- `retention_policies`
- `billing_orders`
- `payments`
- `task_events`

其中当前真实运行中明确还在持续写的核心表是：

- `tasks`
- `video_tasks`
- `sequence_tasks`
- `billing_orders`
- `payments`
- `task_events`

### 1.2 当前账户/后台表体系

这批表主要来自：

- `000004_account_metadata.up.sql`
- `000005_admin_runtime_audit_stats.up.sql`

包括：

- `account_users`
- `account_api_keys`
- `account_wallets`
- `account_wallet_ledger`
- `account_deposits`
- `runtime_configs`
- `admin_audit_logs`
- `admin_stats_snapshots`

这批表当前都在真实使用。

## 2. 阅读约定

为了避免误解，下面统一约定：

- `id`：数据库内部自增主键，主要给关系引用、联表、索引用
- `public_id`：业务公开 ID，接口、日志、跨模块引用通常看这个
- `metadata_json`：结构化列之外的补充上下文
- `detail_json`：结构化列之外的业务明细
- `*_ref`：外部系统、外部支付、外部对象的引用
- 金额字段如果是 `BIGINT`：
  - 当前账户体系按“最小货币单位整数”理解
  - 例如 `USD` 下通常表示美分
- 金额字段如果是 `NUMERIC(20, 8)`：
  - 是通用金额表示，兼容更精细的小数

## 3. 当前表的使用优先级

这是你排障时最应该先记住的一件事。

### 3.1 当前高频真实使用的表

- `account_users`
- `account_api_keys`
- `account_wallets`
- `account_wallet_ledger`
- `account_deposits`
- `tasks`
- `video_tasks`
- `sequence_tasks`
- `billing_orders`
- `payments`
- `task_events`
- `runtime_configs`
- `admin_audit_logs`
- `admin_stats_snapshots`

### 3.2 当前存在但基本未作为主存储使用的表

- `users`
- `api_keys`
- `wallets`
- `wallet_ledger`
- `task_assets`
- `task_results`
- `pricing_policies`
- `retention_policies`

这些表更多代表：

- 早期规范化 schema
- 理想化设计
- 或后续扩展预留

当前项目主要没有用它们作为事实源。

## 4. 任务域表

任务域是当前系统的核心表群。

### 4.1 `tasks`

用途：

- 所有任务的父表
- 统一保存视频/序列任务的公共字段
- 给 `billing_orders`、`task_events` 等表提供统一外键入口

当前是否真实使用：

- 是，持续使用

字段说明：

- `id`
  - 数据库内部主键
  - 给子表和关联表引用

- `public_id`
  - 任务业务 ID
  - 例如 `vid_xxx`、`seq_xxx`
  - 对外接口和日志里通常看到的是它

- `task_type`
  - 任务类型
  - 当前主要是：
    - `video`
    - `sequence`

- `owner_type`
  - 任务归属类型
  - 当前常见值：
    - `public`
    - `user`
  - 当前主流程只保留这两类：
    - `public`
    - `user`
  - `anonymous` 主要是早期兼容历史值，不应再由当前主流程新写入

- `owner_id`
  - 规范化设计里给 `users.id` 预留的内部引用
  - 当前兼容写法基本不使用，通常为 `NULL`

- `status`
  - 当前任务状态
  - 例如：
    - `created`
    - `uploaded`
    - `awaiting_payment`
    - `awaiting_payment_1`
    - `processing`
    - `succeeded_awaiting_payment_2`
    - `succeeded`
    - `failed`
    - `expired`
    - `deleted`

- `task_token_hash`
  - 原本给 public 任务 token hash 预留
  - 当前兼容层没有真正写这个字段

- `idempotency_key`
  - 原本给接口幂等设计预留
  - 当前兼容层没有真正写这个字段

- `current_payment_phase`
  - 当前待支付阶段
  - 典型值：
    - `video_phase1`
    - `video_phase2`
    - `sequence_once`
  - 如果当前不处于待支付阶段，通常为空

- `pricing_policy_id`
  - 规范化外键，给 `pricing_policies.id` 预留
  - 当前兼容写法基本不使用

- `pricing_snapshot_json`
  - 该任务当前价格/账单相关快照
  - 当前真实写的是账单结构或其兼容快照

- `retention_policy_id`
  - 规范化外键，给 `retention_policies.id` 预留
  - 当前兼容写法基本不使用

- `retention_snapshot_json`
  - 当前任务保留策略快照
  - 当前常见内容包括：
    - `expire_at`
    - `delete_after_at`

- `expire_at`
  - 到了这个时间，如果任务还处于等待上传、等待支付等状态，就会转成 `expired`

- `delete_after_at`
  - 到了这个时间，任务资产或记录会进入删除阶段

- `status_entered_at`
  - 进入当前状态的时间
  - 当前兼容层直接用 `updated_at` 的时点写入，不是严格独立维护

- `created_at`
  - 任务创建时间

- `updated_at`
  - 最近一次任务状态或数据变更时间

- `deleted_at`
  - 父表软删除时间
  - 预留给 SQL 归档/软删除路径；当前任务 TTL 清理保留轻量任务摘要，不再依赖物理删除任务记录

索引说明：

- `tasks_public_id_uidx`
  - 用公开任务 ID 快速定位任务

- `tasks_status_expire_idx`
  - 便于按状态和过期时间做清理扫描

- `tasks_status_delete_after_idx`
  - 便于按状态和删除时间做清理扫描

- `tasks_owner_idx`
  - 便于按归属类型/归属人查看任务列表

### 4.2 `video_tasks`

用途：

- 视频任务子表
- 保存视频任务的专有字段
- `metadata_json` 只保留结构化列之外的补充上下文

当前是否真实使用：

- 是，持续使用

字段说明：

- `task_id`
  - 外键，指向 `tasks.id`
  - 同时也是本表主键

- `input_object_key`
  - 上传视频在对象存储里的 key
  - 例如 `videos/<task_id>/input.bin`

- `filename`
  - 用户上传时的文件名

- `content_type`
  - 上传文件的 MIME 类型

- `size_bytes`
  - 视频文件大小，单位字节

- `sha256`
  - 规范化设计预留的视频哈希
  - 当前主流程一般不写

- `duration_ms`
  - 视频时长，毫秒

- `fps`
  - 视频帧率

- `frame_count`
  - 视频总帧数

- `progress_percent`
  - 处理进度，0 到 100

- `sequence_count`
  - 视频解析出的序列总数

- `total_sequence_frames`
  - 所有序列累计帧数

- `started_at`
  - 规范化设计预留，当前兼容写法一般不单独维护

- `finished_at`
  - 规范化设计预留，当前兼容写法一般不单独维护

- `failure_code`
  - 规范化失败码预留
  - 当前通常不用

- `failure_message`
  - 当前失败原因文本

- `public_id`
  - 视频任务公开 ID
  - 与 `tasks.public_id` 对应

- `owner_type`
  - 归属类型
  - 常见值：
    - `public`
    - `user`

- `owner_ref`
  - 当前真实写法里通常是用户的 `public_id`
  - 如果是公开任务，可能为空

- `owner_api_key_ref`
  - 如果通过 API Key 创建，这里保存 API Key 的 `public_id`

- `public`
  - 是否是 public 任务
  - `true` 表示 public 任务
  - `false` 表示注册用户私有任务

- `status`
  - 当前视频任务状态

- `expire_at`
  - 当前任务过期时间

- `delete_after_at`
  - 当前任务删除时间

- `metadata_json`
  - 结构化列之外的视频任务补充上下文
  - 任务状态、归属、过期时间等以结构化列为准

- `created_at`
  - 创建时间

- `updated_at`
  - 更新时间

索引说明：

- `video_tasks_public_id_uidx`
  - 按视频任务 ID 直接查

- `video_tasks_owner_idx`
  - 查某个用户、某类拥有者的任务列表

- `video_tasks_status_idx`
  - 查某状态下的任务列表

### 4.3 `sequence_tasks`

用途：

- 序列任务子表
- 保存序列任务专有字段

当前是否真实使用：

- 是，持续使用

字段说明：

- `task_id`
  - 外键，指向 `tasks.id`

- `declared_frame_count`
  - 创建任务时声明的帧数

- `uploaded_frame_count`
  - 当前已经上传成功的帧数

- `started_at`
  - 规范化设计预留
  - 当前一般不单独维护

- `finished_at`
  - 规范化设计预留
  - 当前一般不单独维护

- `failure_code`
  - 规范化失败码预留
  - 当前一般不用

- `failure_message`
  - 当前失败原因文本

- `public_id`
  - 任务公开 ID

- `owner_type`
  - 拥有者类型

- `owner_ref`
  - 当前通常是用户 `public_id`

- `owner_api_key_ref`
  - 当前通常是 API Key `public_id`

- `public`
  - 是否是 public 任务
  - `true` 表示 public 任务
  - `false` 表示注册用户私有任务

- `status`
  - 序列任务当前状态

- `expire_at`
  - 任务过期时间

- `delete_after_at`
  - 任务清理时间

- `metadata_json`
  - 结构化列之外的序列任务补充上下文
  - 上传列表、结果资产、账单上下文等动态对象仍保存在 JSON 中
  - 兼容期内任务 `billing` 仍随任务 JSON 恢复运行态；`billing_orders` 用于查询、统计和对账

- `created_at`
  - 创建时间

- `updated_at`
  - 更新时间

索引说明：

- `sequence_tasks_public_id_uidx`
  - 按任务 ID 定位

- `sequence_tasks_owner_idx`
  - 按用户查任务

- `sequence_tasks_status_idx`
  - 按状态查任务

### 4.4 `task_events`

用途：

- 任务状态与关键动作的结构化审计表
- 记录任务生命周期的重要节点

当前是否真实使用：

- 是，持续使用
- 当前是任务账单的结构化同步表，用于查询、统计和对账；运行态任务 Billing 仍从任务 JSON 恢复

字段说明：

- `id`
  - 自增主键

- `task_id`
  - 外键，指向 `tasks.id`

- `event_type`
  - 事件类型
  - 当前常见值：
    - `task_created`
    - `upload_completed`
    - `billing_created`
    - `payment_confirmed`
    - `worker_succeeded`
    - `worker_failed`
    - `task_expired`
    - `task_deleted`

- `from_status`
  - 事件发生前状态

- `to_status`
  - 事件发生后状态

- `reason_code`
  - 原因码
  - 常见内容：
    - 失败原因
    - `retention_expired`
    - 支付协议名

- `payload_json`
  - 事件上下文快照
  - 当前会带任务摘要、账单摘要、支付协议等

- `operator_type`
  - 触发者类型
  - 例如：
    - `public`
    - `user`
    - worker 或系统触发语义

- `operator_id`
  - 触发者 ID
  - 一般是用户 ID、任务拥有者 ID 或相关标识

- `created_at`
  - 事件时间

索引说明：

- `task_events_task_idx`
  - 按任务拉事件时间线

### 4.5 `billing_orders`

用途：

- 保存任务相关的计费单
- 一个任务可以对应一个或多个阶段账单

当前是否真实使用：

- 是，持续使用

字段说明：

- `id`
  - 数据库内部主键

- `task_id`
  - 外键，指向 `tasks.id`

- `phase`
  - 计费阶段
  - 当前常见值：
    - `video_phase1`
    - `video_phase2`
    - `sequence_once`

- `owner_type`
  - 账单所有者类型
  - 与任务拥有者类型对应

- `currency`
  - 币种
  - 当前默认 `USD`

- `amount`
  - 金额
  - `NUMERIC(20, 8)`，可表示整数或小数
  - 当前很多业务值本质上仍是整数金额

- `status`
  - 账单状态
  - 常见值：
    - `pending`
    - `paid`
    - `expired`
    - `canceled`
    - `waived`

- `pricing_policy_id`
  - 规范化外键，预留给 `pricing_policies.id`
  - 当前一般不写

- `pricing_snapshot_json`
  - 计费快照
  - 当前通常存完整账单对象快照

- `quantity_snapshot_json`
  - 计费依据快照
  - 当前常见内容：
    - 视频帧数
    - 序列帧数
    - 序列总帧数
    - 每千帧费率

- `due_at`
  - 支付截止时间

- `paid_at`
  - 支付成功时间

- `created_at`
  - 创建时间

- `updated_at`
  - 更新时间

索引说明：

- `billing_orders_task_phase_uidx`
  - 保证一个任务的同一阶段只会有一张账单

- `billing_orders_status_idx`
  - 查待支付、已过期等账单

### 4.6 `payments`

用途：

- 保存支付确认记录
- 当前是账单进入 paid 后的支付同步结果

当前是否真实使用：

- 是，持续使用

需要特别注意：

- 它现在更像“支付确认镜像表”
- 不是独立支付事实源

字段说明：

- `id`
  - 自增主键

- `order_id`
  - 外键，指向 `billing_orders.id`

- `protocol`
  - 支付协议
  - 当前常见值：
    - `wallet`
    - `mock`
    - `x402`
    - 也可扩展到其他 provider

- `rail`
  - 支付通道/支付轨
  - 当前通常与 `protocol` 相同

- `provider_payment_id`
  - 第三方支付平台支付单号
  - 当前很多链路可能为空

- `receipt_ref`
  - 支付回执引用
  - 例如 settlement ref

- `request_ref`
  - 支付请求引用
  - 当前常常为空

- `amount`
  - 确认金额

- `currency`
  - 币种

- `status`
  - 支付状态
  - 当前同步时通常是 `confirmed`

- `receipt_json`
  - 支付回执快照
  - 当前通常包含：
    - `order_id`
    - `phase`
    - `settlement_ref`
    - `payment_protocol`
    - `detail`

- `created_at`
  - 写入时间

- `confirmed_at`
  - 支付确认时间

索引说明：

- `payments_provider_payment_id_uidx`
  - 避免同一个 provider payment id 重复

- `payments_order_idx`
  - 按订单查支付记录

## 5. 账户域表

当前用户、钱包、充值都走 `account_*` 这一套表。

### 5.1 `account_users`

用途：

- 当前用户主表

当前是否真实使用：

- 是，持续使用

字段说明：

- `public_id`
  - 用户业务 ID
  - 例如 `usr_xxx`

- `email`
  - 用户邮箱
  - 邮箱注册登录标识，手机号注册时可为空

- `phone`
  - 用户手机号
  - 规范化为 E.164 格式，例如 `+8613800138000`
  - 手机号注册登录标识，邮箱注册时可为空

- `name`
  - 用户姓名或显示名

- `preferred_locale`
  - 用户偏好语言
  - 例如 `zh-CN`、`en`

- `country_code`
  - 国家代码
  - 例如 `CN`、`US`

- `display_currency`
  - 门户展示币种
  - 例如 `USD`

- `status`
  - 用户状态
  - 当前常见值：
    - `active`

- `password_salt`
  - 密码哈希盐值

- `password_hash`
  - 密码哈希

- `gait_rotation_seed`
  - 用户步态特征旋转矩阵种子
  - 每个用户一个固定 seed；服务端按该 seed 确定性生成 512x512 正交矩阵，对 512 维步态特征做旋转后返回

- `sequence_feature_month`
  - 当前序列提特征计数所在自然月
  - 格式：`YYYY-MM`

- `sequence_feature_used`
  - 当前自然月已成功提取步态特征的序列数
  - 用于执行每用户每月序列/视频提特征上限

- `created_at`
  - 注册时间

- `updated_at`
  - 用户资料更新时间

- `metadata_json`
  - 结构化列之外的用户补充上下文
  - 结构化列是事实源；加载时用户 ID、邮箱、手机号、推荐码和代理商归属等以结构化列为准

索引说明：

- `account_users_email_uidx`
  - 邮箱唯一

- `account_users_phone_uidx`
  - 手机号唯一

代理商功能字段：

- `sales_agent_public_id`
  - 绑定的代理商业务 ID
  - 为空表示不是代理商发展的客户

- `referral_code`
  - 用户注册时最终生效的 4 位推荐码
  - 无效推荐码在用户确认继续注册后按空值保存

- `referral_bound_at`
  - 用户绑定代理商的时间

### 5.2 `sms_verification_codes`

用途：

- 手机号注册的短信验证码记录
- 同类邮箱验证码表为 `email_verification_codes`，字段结构基本一致，只是把 `phone` 换成 `email`

当前是否真实使用：

- 是，手机号注册、忘记密码、绑定手机号发送和校验短信时使用

字段说明：

- `public_id`
  - 验证码业务 ID

- `phone`
  - 规范化手机号

- `purpose`
  - 验证码用途
  - 当前支持：
    - `register`

- `code_hash`
  - 验证码哈希，不保存明文验证码

- `status`
  - 验证码状态
  - 当前常见值：
    - `pending`
    - `used`
    - `expired`
    - `failed`
    - `send_failed`

- `attempts`
  - 已校验失败次数

- `max_attempts`
  - 最大校验失败次数

- `request_ip`
  - 请求来源 IP

- `request_user_agent`
  - 请求 User-Agent

- `created_at`
  - 创建时间

- `expires_at`
  - 过期时间

- `used_at`
  - 使用时间

- `metadata_json`
  - 预留扩展信息

清理策略：

- API 进程后台维护循环每天最多执行一次验证码清理
- 删除 `created_at` 早于 90 天的 `sms_verification_codes` 和 `email_verification_codes`
- 验证码明文不会落库，只保存 `code_hash`

### 5.3 `account_api_keys`

用途：

- 当前用户 API Key 表

当前是否真实使用：

- 是，持续使用

字段说明：

- `public_id`
  - API Key 业务 ID

- `user_public_id`
  - 关联用户 `public_id`

- `key_prefix`
  - API Key 前缀
  - 用于界面快速识别

- `key_hash`
  - API Key 哈希值
  - 认证时主要靠它

- `secret`
  - API Key 明文
  - 当前实现会保存
  - 这是产品体验与安全性之间的取舍点

- `name`
  - API Key 名称

- `status`
  - 当前状态
  - 常见值：
    - `active`
    - `paused`
    - `deleted`

- `last_used_at`
  - 最近一次使用时间

- `created_at`
  - 创建时间

- `revoked_at`
  - 删除或吊销时间

- `metadata_json`
  - 结构化列之外的 API Key 补充上下文
  - 结构化列是事实源；认证和列表展示以结构化列为准

索引说明：

- `account_api_keys_key_hash_uidx`
  - 认证时按 hash 精确定位

- `account_api_keys_user_idx`
  - 拉用户 API Key 列表

### 5.4 `account_wallets`

用途：

- 当前用户钱包表
- 保存余额快照

当前是否真实使用：

- 是，持续使用

字段说明：

- `public_id`
  - 钱包业务 ID

- `user_public_id`
  - 所属用户 ID

- `currency`
  - 钱包币种

- `available_balance`
  - 可用余额
  - 当前是 `BIGINT`
  - 默认按最小货币单位整数理解

- `locked_balance`
  - 冻结余额
  - 当前实现大多为 0，预留扩展

- `last_ledger_entry_public_id`
  - 最近一条流水的业务 ID

- `updated_at`
  - 钱包最近更新时间

- `metadata_json`
  - 结构化列之外的钱包补充上下文
  - 余额、套餐汇总和最近流水以结构化列为准

索引说明：

- `account_wallets_user_currency_uidx`
  - 保证一个用户同币种只有一个钱包

### 5.5 `account_subscriptions`

用途：

- 注册用户套餐实例表
- 每次套餐购买或自动续费创建一条独立实例
- 支持同一用户多个套餐、同一套餐多次购买、每个实例独立自动续费状态

当前是否真实使用：

- 是

字段说明：

- `public_id`
  - 套餐实例业务 ID

- `user_public_id`
  - 所属用户 ID

- `plan_id` / `plan_name`
  - 后台配置中的套餐 ID 和购买时套餐名称快照

- `currency`
  - 套餐额度记账币种，当前为 CNY

- `initial_amount`
  - 初始发放套餐额度

- `remaining_amount`
  - 当前剩余套餐额度

- `pay_amount`
  - 购买或续费时对应的 CNY 支付金额

- `status`
  - `active` / `expired` 等

- `auto_renew`
  - 是否自动续费
  - 同一用户同一 `plan_id` 最多一个 active 实例开启自动续费
  - 套餐额度过期不会立即关闭自动续费；宽限期内仍可作为自动续费候选

- `renewal_key`
  - 最近一次自动续费尝试或成功的幂等 key，格式通常为本地日期，例如 `2026-07-10`
  - 用于防止同一天重复扣款，不表示永久停止自动续费

- `renewal_failure_count`
  - 连续自动续费失败次数
  - 成功续费或用户重新开启自动续费时清零
  - 达到 3 次后关闭该套餐实例自动续费

- `notify_before_key`
  - 到期前提醒幂等 key

- `expires_at`
  - 当前套餐实例到期时间

- `metadata_json`
  - 结构化列之外的套餐实例补充上下文
  - 套餐额度、续费状态、失败次数和到期时间以结构化列为准

索引说明：

- `account_subscriptions_user_idx`
  - 用户套餐列表和扣费排序

- `account_subscriptions_active_idx`
  - active 套餐查询

- `account_subscriptions_renew_idx`
  - 自动续费候选查询

### 5.6 `account_wallet_ledger`

用途：

- 当前钱包流水表
- 记录每次余额变动

当前是否真实使用：

- 是，持续使用

字段说明：

- `public_id`
  - 流水业务 ID
  - 例如 `led_xxx`

- `wallet_public_id`
  - 对应钱包 ID

- `user_public_id`
  - 对应用户 ID

- `task_public_id`
  - 如果这笔流水来自某个任务扣费，这里记录任务 ID

- `order_public_id`
  - 如果这笔流水关联某张账单或充值单，这里记录订单 ID

- `detail_json`
  - 业务细节
  - 当前常见内容：
    - `frame_count`
    - `sequence_count`
    - `total_sequence_frames`
    - `api_key_id`
    - `api_key_name`
    - `auth_method`
    - `request_meta`

- `direction`
  - 流水方向
  - 常见值：
    - `credit`
    - `debit`

- `amount`
  - 本次变动金额

- `currency`
  - 币种

- `balance_before`
  - 变动前余额

- `balance_after`
  - 变动后余额

- `reason_code`
  - 原因码
  - 当前常见值：
    - `user_deposit`
    - `admin_topup`
    - `admin_adjustment`
    - `sequence_once`
    - `video_phase1`
    - `video_phase2`

- `created_at`
  - 流水时间

- `metadata_json`
  - 结构化列之外的流水补充上下文
  - 金额、方向、原因、钱包和创建时间以结构化列为准

索引说明：

- `account_wallet_ledger_wallet_idx`
  - 按钱包看流水

- `account_wallet_ledger_user_idx`
  - 按用户看流水

- `account_wallet_ledger_reason_created_idx`
  - 按 `reason_code + created_at` 查询财务页充值余额流水、套餐流水和导出样本

### 5.6 `account_deposits`

用途：

- 当前充值单表
- 管理充值申请、checkout、到账确认

当前是否真实使用：

- 是，持续使用

字段说明：

- `public_id`
  - 充值单业务 ID
  - 例如 `dep_xxx`

- `user_public_id`
  - 所属用户

- `currency`
  - 充值币种

- `amount`
  - 充值金额

- `status`
  - 当前状态
  - 常见值：
    - `pending`
    - `awaiting_checkout`
    - `payment_mismatch`
    - `settled`

- `provider`
  - 充值提供方
  - 例如：
    - `alipay`
    - `wechat_pay`
    - `crypto`
    - 某个 checkout provider

- `channel`
  - 支付渠道
  - 例如：
    - `alipay`
    - `wechat_pay`
    - `crypto`

- `client_ref`
  - 客户端侧引用号

- `settlement_ref`
  - 到账结算引用号
  - 例如 webhook 回执号、第三方交易号

- `provider_ref`
  - 第三方平台引用号
  - 例如 provider order/session id

- `admin_note`
  - 管理员补充说明

- `checkout_provider`
  - 当前 checkout 使用的 provider

- `checkout_status`
  - checkout 当前状态
  - 例如：
    - `created`
    - `completed`

- `checkout_url`
  - 跳转支付页地址

- `checkout_session_id`
  - checkout session ID

- `checkout_expires_at`
  - checkout session 失效时间

- `requested_at`
  - 充值申请时间

- `updated_at`
  - 最近更新时间

- `settled_at`
  - 到账确认时间

- `ledger_entry_public_id`
  - 到账后关联的钱包流水 ID

- `detail_json`
  - 充值业务细节
  - 当前常见内容：
    - `auth_method`
    - `checkout_requested_at`
    - `checkout_provider`
    - `checkout_event_id`
    - `checkout_status`
    - `checkout_reconciled`
    - `wechat_pay_total`
    - `wechat_pay_payer_total`
    - `checkout_payment_mismatch`
    - `request_meta`
  - 微信支付优惠/满减时，`wechat_pay_total` 是用于校验的商户订单金额，`wechat_pay_payer_total` 是优惠后的用户实付金额，仅作为审计信息。

- `metadata_json`
  - 结构化列之外的充值单补充上下文
  - 金额、状态、支付渠道、provider 标识和到账时间以结构化列为准

索引说明：

- `account_deposits_provider_ref_uidx`
  - 用 provider ref 回查充值单

- `account_deposits_checkout_session_uidx`
  - 用 checkout session ID 回查充值单

- `account_deposits_user_idx`
  - 拉用户充值记录

- `account_deposits_status_requested_idx`
  - 按状态和申请时间查询财务页充值记录

- `account_deposits_unpaid_expiry_idx`
  - 支撑未支付在线充值单过期清理

## 6. 后台与运行配置表

### 6.1 `runtime_configs`

用途：

- 运行时配置表
- 保存当前全局运行配置
- 不同配置类别拆成同表的不同行保存，避免只改一个类别时覆盖其他类别

当前是否真实使用：

- 是，持续使用

字段说明：

- `config_key`
  - 配置键
  - 当前实际使用：
    - `runtime:retention`
    - `runtime:pricing`
    - `runtime:payment:root`
    - `runtime:payment:alipay`
    - `runtime:payment:wechat_pay`
    - `runtime:payment:crypto`
    - `runtime:payment:x402`
    - `runtime:portal`
    - `runtime:worker`
    - `runtime:reports`
    - `runtime:monthly`
    - `runtime:trial`
    - `runtime:account`
    - `runtime:locate_anything`
    - `runtime:sms`
  - `runtime:payment:crypto` 当前保存第三方加密货币充值配置：
    - `enabled`
    - `display_name`
    - `provider`，当前支持 `nowpayments`
    - `api_base_url`
    - `api_key`
    - `ipn_secret`
    - `order_ttl_minutes`
    - `assets`，每项包含 `network`、`network_name`、`token`、`token_name`、`provider_currency`

- `updated_at`
  - 配置最后更新时间

- `metadata_json`
  - 配置内容
  - 内容随 `config_key` 变化
  - `runtime:account` 保存注册用户策略：
    - `signup_bonus_amount`：首次普通充值到账后赠送到充值余额的 CNY 分金额，默认 `500`；字段名保留历史命名，业务语义为首充赠送
    - `monthly_sequence_feature_limit`：每用户每月通过序列或视频成功提取步态特征的序列数上限，默认 `100000`，`0` 表示不限制
  - `runtime:sms` 保存阿里云短信配置：
    - `enabled`
    - `provider`
    - `access_key_id`
    - `access_key_secret`
    - `sign_name`
    - `template_code`：验证码模板 Code
    - `notification_template_code`：代理商收益通知模板 Code
    - `renewal_notice_template_code`：套餐续费提醒模板 Code
    - `renewal_failure_template_code`：套餐续费失败模板 Code
    - `endpoint`
如果你以后只是想快速定位问题，可以按这个顺序看表。

### 9.1 查用户与余额

1. `account_users`
2. `account_wallets`
3. `account_wallet_ledger`
4. `account_deposits`
5. `account_api_keys`

### 9.2 查任务与支付

1. `tasks`
2. `video_tasks` 或 `sequence_tasks`
3. `billing_orders`
4. `payments`
5. `task_events`

### 9.3 查后台与配置

1. `runtime_configs`
2. `admin_audit_logs`
3. `admin_stats_snapshots`
4. `trial_usage`

### 9.4 查免注册试用

1. `trial_usage`

`trial_usage` 按 IP 哈希和算法分桶累计免注册试用请求次数、帧数和消耗金额。它不记录明文 IP，只记录哈希值与最近访问时间；实际限额以同一算法分桶的累计消耗金额为准。`fingerprint_hash` 字段当前用于保存算法分桶，例如 `op:object_search`、`op:gait_pose`、`op:gait_sequence`；旧数据中的空指纹分桶仅保留兼容。

## 10. 我对当前数据库设计的总结

### 10.1 优点

- 任务域已经形成比较完整的父表 + 子表 + 账单 + 支付 + 事件结构
- 账户域已经从早期规范化表中拆出更贴近当前业务的 `account_*` 表
- `metadata_json` 让系统迭代时兼容性比较强

### 10.2 需要注意的现实

- 现在不是所有表都同等重要
- 真正要查当前系统，优先看 `account_*`、`tasks`、`video_tasks`、`sequence_tasks`、`billing_orders`、`payments`、`task_events`
- `users`、`api_keys`、`wallets`、`wallet_ledger`、`task_assets`、`task_results`、`pricing_policies`、`retention_policies` 更偏历史/规范化/预留

如果你愿意，我下一步可以继续把这份文档再补成“每张表给几个真实样例 JSON/样例记录”的版本，这样你看字段会更直观。
