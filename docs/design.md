# 步态解析公网服务系统设计文档

本文档描述当前项目的完整系统设计，覆盖业务目标、系统边界、模块划分、任务流转、计费与支付、存储与持久化、管理后台、部署方式，以及后续演进建议。

如果你要看更细粒度的内部时序、数据库写入顺序、为什么这样写、以及排障入口，请再看：

- [dataflow.md](/home/watrix/tiandk/agent/gaitAgent/docs/dataflow.md)
- [database-dictionary.md](/home/watrix/tiandk/agent/gaitAgent/docs/database-dictionary.md)

文档面向以下读者：

- 后端开发
- 算法与 SDK 对接开发
- 运维部署人员
- 后台管理与产品设计人员

相关代码入口：

- API 进程入口：[cmd/api/main.go](/home/watrix/tiandk/agent/gaitAgent/cmd/api/main.go)
- Worker 进程入口：[cmd/worker/main.go](/home/watrix/tiandk/agent/gaitAgent/cmd/worker/main.go)
- API 应用组装：[internal/app/api.go](/home/watrix/tiandk/agent/gaitAgent/internal/app/api.go)
- Worker 应用组装：[internal/app/worker.go](/home/watrix/tiandk/agent/gaitAgent/internal/app/worker.go)

## 1. 项目目标

本项目基于 `algorithms/sdk` 对外提供一个可公开访问的步态解析服务，支持两类核心能力：

- 解析视频
- 解析序列
- Gait Pose 单独解析

其中：

- 视频解析是异步任务
- 序列解析是同步任务

服务同时支持两种使用方式：

- 注册用户模式：邮箱注册、密码登录、预充值、生成 API Key，后续按调用扣费
- 匿名 Agent 模式：不注册账号，通过匿名任务创建与单次支付完成调用

接口边界上只保留两类调用路径：

- 注册用户只能走私有接口 `/v1/videos`、`/v1/sequences`
- 匿名用户或 Agent 只能走公开接口 `/v1/public/videos`、`/v1/public/sequences`

当前已经不再支持“匿名但非 public”的私有任务模式。

系统设计目标：

- SDK 只在本机 worker 进程中加载，不暴露在 HTTP 进程中
- HTTP 服务支持公网访问
- 任务、计费、支付、用户、后台管理等能力可以独立演进
- 当前先保证单机可用，后续可演进到 API/Worker 分离部署

## 2. 功能范围

### 2.1 视频解析

用户上传完整视频后，系统解析并产出多个序列。每个序列表示一个人从出现到消失的完整过程，包含：

- 步态特征
- 人脸特征
- ReID 特征
- ReID 结构化属性
- 序列在视频中的帧信息
- 每帧的目标框信息
- 对外可访问的步态图
- 对外可访问的人脸图

视频任务流程：

1. 创建任务
2. 获取上传地址
3. 上传视频
4. 生成一期计费
5. 支付一期费用
6. worker 调用 SDK 解析
7. 生成二期计费
8. 支付二期费用
9. 获取完整结果
10. 到期自动删除资产与记录

### 2.2 序列解析

用户上传一个已经跟踪完成的单序列图片集合，返回：

- 步态特征
- 人脸特征
- ReID 特征
- ReID 结构化属性
- 步态图
- 人脸图

序列任务流程：

1. 创建任务
2. 获取每帧上传地址
3. 上传帧图片
4. 发起解析
5. 支付费用
6. 同步返回结果
7. 到期自动删除资产与记录

### 2.3 Gait Pose 单独解析

Gait Pose 是从完整序列解析里拆出来的独立能力，底层调用 SDK 的 `agentGaitGetSeqGaitPose` 接口。

输入仍然是已经跟踪完成的单序列图片集合，返回：

- 每帧对齐信息
- 2D 人体关节点
- 3D 人体关节点
- 情绪输出字段

Gait Pose 不返回 gait、face、ReID 特征，也不复用序列解析费用。它是单独接口、单独扣费，当前价格为 `$0.10 / 千帧`。

## 3. 系统架构

当前系统由以下部分组成：

- `gait-api`：对外 HTTP 服务
- `gait-worker`：本机后台解析进程
- 本地对象存储：上传内容与结果资产
- PostgreSQL：任务、账单、支付、账户、运行配置、审计、统计
- 本地 Unix Socket：API 与 worker 通信

### 3.1 进程拆分原则

API 与 worker 拆分的原因：

- SDK 初始化和运行风险较高，不应放进公网 HTTP 进程
- SDK 依赖 GPU、加密狗、OpenCV/FFmpeg 动态库，隔离后更容易运维
- HTTP 服务重启不应直接中断 SDK 进程
- 后续可以演进到多台 worker、单台 API 的形态

当前约束：

- API 与 worker 仍部署在同一台机器
- API 通过本地 Unix Socket 调用 worker 提供的序列 SDK 能力
- 视频任务的状态轮询与最终处理逻辑由 worker 驱动

### 3.2 当前推荐部署端口

- `3005`：API 服务端口
- `3006`：用户门户页面端口
- `3007`：管理后台页面端口

当前实现支持：

- 三端口：API、用户页面、管理页面分别监听
- Nginx：公网 `80/443` 负责 TLS 和域名反向代理，再转发到本机 `3005/3006/3007`
- 备案期间只公开已备案域名 `www.w-agent.cn`，不公开根域名和 `api` 子域名
- 用户门户当前采用紧凑充值面板布局，充值记录/使用记录在页面内以表格展示，并支持时间范围筛选和导出

用户当前采用的主方案是：

- `https://www.w-agent.cn/`：用户门户，Nginx 转发到 `3006`
- `https://www.w-agent.cn/api/...`：API，Nginx 去掉 `/api/` 前缀后转发到 `3005`
- `https://www.w-agent.cn/mcp`、`/openapi.json`、`/.well-known/...`：机器可读接口，Nginx 转发到 `3005`
- `3007`：管理后台端口，备案期间不建议直接通过未备案域名公开

## 4. 模块划分

### 4.1 目录概览

核心目录：

- `cmd/api`：API 进程入口
- `cmd/worker`：worker 进程入口
- `internal/app`：应用装配
- `internal/httpapi`：HTTP 路由、handler、中间件
- `internal/sequences`：序列任务服务
- `internal/videos`：视频任务服务
- `internal/accounts`：用户、钱包、充值、API Key
- `internal/admincfg`：后台运行配置
- `internal/adminaudit`：后台操作审计
- `internal/adminstats`：后台统计与看板
- `internal/payments`：支付协议与支付网关
- `internal/pricing`：计费策略
- `internal/retention`：清理与保留策略
- `internal/trialusage`：免注册试用额度计数，按 IP 累计试用金额；首页试玩和浏览器客户端试用共用同一累计额度
- `internal/locateanything`：图搜万物上游转发客户端
- `internal/storage`：对象存储抽象
- `internal/repository/sqlrepo`：SQL 持久化仓库
- `internal/sdkengine`：SDK 封装
- `internal/workerapi`：worker 内部服务接口
- `internal/workerclient`：API 访问 worker 的客户端
- `internal/reid`：ReID 属性解码
- `internal/resultfmt`：结果格式化

### 4.2 API 进程职责

API 进程负责：

- 用户注册、登录、会话
- API Key 鉴权
- 注册用户私有任务入口
- public 任务入口
- 上传地址生成
- 任务状态查询
- 结果查询
- 计费与支付流程
- 运行时配置读取与热更新
- 管理后台与用户门户页面
- 统计采样与审计写入

### 4.3 Worker 进程职责

worker 进程负责：

- 初始化 SDK
- 提供序列 SDK 接口
- 轮询视频任务
- 推进视频任务到 `processing`
- 获取视频解析进度
- 获取视频解析结果
- 清理视频 SDK 内部状态

## 5. 对外接口设计

接口总说明见 [api.md](/home/watrix/tiandk/agent/gaitAgent/docs/api.md)。

这里给出设计层面的接口分类。

### 5.1 公开解析接口

匿名或 Agent 可用：

- `POST /v1/public/videos`
- `PUT /v1/video-uploads/{task_id}`
- `POST /v1/public/videos/{task_id}/settle-phase1`
- `GET /v1/public/videos/{task_id}`
- `GET /v1/public/videos/{task_id}/result`
- `POST /v1/public/videos/{task_id}/settle-phase2`

- `POST /v1/public/sequences`
- `PUT /v1/uploads/{task_id}/{index}`
- `POST /v1/public/sequences/{task_id}/parse`
- `POST /v1/public/sequences/{task_id}/gait-pose`
- `POST /v1/public/sequences/{task_id}/settle`
- `GET /v1/public/sequences/{task_id}`
- `GET /v1/public/sequences/{task_id}/result`

### 5.2 注册用户接口

门户与 API Key 模式：

注册用户任务接口还包括：

- `POST /v1/videos`
- `POST /v1/videos/{task_id}/complete`
- `GET /v1/videos/{task_id}`
- `GET /v1/videos/{task_id}/result`
- `DELETE /v1/videos/{task_id}`
- `POST /v1/sequences`
- `POST /v1/sequences/{task_id}/parse`
- `POST /v1/sequences/{task_id}/gait-pose`
- `GET /v1/sequences/{task_id}`
- `GET /v1/sequences/{task_id}/result`
- `DELETE /v1/sequences/{task_id}`

- `POST /v1/users/register`
- `POST /v1/users/login`
- `POST /v1/users/logout`
- `GET /v1/me`
- `GET /v1/me/wallet`
- `GET /v1/me/ledger`
- `GET /v1/me/deposits`
- `POST /v1/me/deposits`
- `POST /v1/me/deposits/{deposit_id}/checkout`
- `GET /v1/me/api-keys`
- `POST /v1/me/api-keys`
- `POST /v1/me/api-keys/{key_id}/pause`
- `POST /v1/me/api-keys/{key_id}/resume`
- `DELETE /v1/me/api-keys/{key_id}`

### 5.3 管理接口

- `GET /v1/admin/overview`
- `GET /v1/admin/timeseries`
- `GET /v1/admin/finance`
- `GET /v1/admin/audit-logs`
- `GET /v1/admin/runtime-config`
- `PUT /v1/admin/runtime-config`
- `GET /v1/admin/users`
- `GET /v1/admin/users/{user_id}`
- `POST /v1/admin/users/{user_id}/topups`
- `GET /v1/admin/videos`
- `GET /v1/admin/videos/{task_id}`
- `GET /v1/admin/sequences`
- `GET /v1/admin/sequences/{task_id}`

## 6. 认证与授权

### 6.1 注册用户

用户通过：

- 邮箱
- 密码

完成注册和登录。

登录成功后：

- 浏览器门户使用会话 cookie
- 程序调用使用 API Key

### 6.2 API Key

API Key 用于：

- 注册用户发起解析请求
- 注册用户查询任务和结果
- 后续自动化调用

API Key 特性：

- 可创建多个
- 可暂停
- 可恢复
- 可删除
- 当前用户门户已支持展示完整值与快捷复制

### 6.3 匿名任务 Token

匿名任务创建后返回 `task_token`，用于：

- 查询任务状态
- 获取任务结果
- 删除任务
- 调用公开结算接口

说明：

- 文件上传本身依赖的是 `upload_url` 中的 `token=...`
- `task_token` 只用于 public 任务的状态、结果、删除、结算等接口

### 6.4 管理员登录

管理后台当前采用：

- 普通账号邮箱/密码登录
- 再校验该邮箱是否在 `GAIT_ADMIN_EMAILS` 白名单中

不是单独维护一套管理员账户体系。

## 7. 任务状态机

详细状态机见 [state-machine.md](/home/watrix/tiandk/agent/gaitAgent/docs/state-machine.md)。

### 7.1 视频状态

- `created`
- `uploaded`
- `awaiting_payment_1`
- `processing`
- `succeeded_awaiting_payment_2`
- `succeeded`
- `failed`
- `expired`
- `deleted`

### 7.2 序列状态

- `created`
- `awaiting_payment`
- `processing`
- `succeeded`
- `failed`
- `expired`
- `deleted`

### 7.3 当前实现说明

当前仓库层已经把关键事件持久化到 `task_events`，包括：

- `task_created`
- `upload_completed`
- `billing_created`
- `payment_confirmed`
- `worker_succeeded`
- `worker_failed`
- `task_expired`
- `task_deleted`

这为后续：

- 更精细的统计
- 多机审计
- 任务追踪
- 财务对账

提供了基础。

## 8. 结果数据设计

### 8.1 视频结果

视频结果的顶层包含：

- 视频总帧数
- 序列数量
- 序列总帧数
- 多个序列结果

每个序列包含：

- `sequence_id`
- `batch`
- `frame_count`
- `frames`
- `gait_feature`
- `reid_feature`
- `face_feature`
- `reid_structure_raw`
- `reid_attributes`
- `reid_summary`

序列解析使用 SDK 的 `GetSplitSeqFeature`。一个输入跟踪序列可能拆分成多个单人输出序列，用于处理串框、前后不同人或中间混入其他人的情况；SDK 可能丢弃不稳定帧。HTTP 响应通过 `sequences` 返回全部拆分后的单人序列，`sequence_count` 是返回数量。
- `emotions`
- `gait_images`
- `gait_image`
- `face_image`

其中：

- `emotions` 表示 SDK 返回的情绪识别结果。
- `gait_images` 是对外兼容字段，当前固定返回空数组，不向用户返回逐帧步态扣图内容。
- `gait_image` / `face_image` 是任务级 token 保护的结果资产链接，会随任务保留期过期；过期或清理后下载应返回错误，不能回退到其他任务或其他用户资产。
- SDK 内部还会返回 `gaitImages`，它是与 `ImageIds/Rects` 对齐的人形步态扣图 JPG 列表。该字段不直接返回到公网 JSON，主要用于服务端样本归档和后续算法迭代。

### 8.2.1 样本归档

为了后续算法模型迭代，服务端会在解析成功后额外保存一份样本，不跟随任务 TTL 自动清理：

```text
<data_dir>/sequence_samples/user/<user_id>/<task_id>/
<data_dir>/sequence_samples/anonymous/<anonymous_owner_id>/<task_id>/
```

序列解析接口会保存用户上传的人形小图帧；视频解析接口会在 SDK 返回 `gaitImages` 时按视频任务和序列分别保存扣图帧：

```text
<data_dir>/sequence_samples/user/<user_id>/<video_task_id>/<sequence_id>/frames/*.jpg
```

每个归档目录包含 `frames/`、`metadata.json`、`result.json`。该目录由管理人员自行拷贝和删除，业务清理任务不会删除它。

`metadata.json` 用于后续数据清洗、聚类和算法迭代追溯来源。注册用户样本会记录：

- `owner_user_id`、`owner_email`、`owner_name`
- `owner_api_key_id`、`api_key_name`、`api_key_prefix`、`api_key_hash`
- `auth_method`
- `request_meta.client_ip`、`request_meta.client_ip_mask`、`request_meta.user_agent`、`request_meta.request_id`、Agent 相关请求头
- `created_at`、`updated_at`、`archived_at`

匿名 public 样本会记录：

- `owner_type=anonymous` 和基于 `network + payer_address` 生成的匿名 `owner_id`
- `payment.payer_address`、`payment.network`、`payment.asset`、`payment.asset_symbol`、`payment.settlement_ref`
- `request_meta.client_ip`、`request_meta.client_ip_mask`、`request_meta.user_agent`、`request_meta.request_id`、Agent 相关请求头
- `created_at`、`updated_at`、`archived_at`

归档路径中不直接使用邮箱、IP 或钱包地址，避免在目录名里暴露敏感信息。API Key 不保存完整明文，只保存前缀和 SHA-256 哈希，便于追溯但不能反推出密钥。

### 8.2 序列结果

序列结果结构与视频中的单序列结构一致。

### 8.3 框坐标定义

当前 `rect` 采用 OpenCV `Rect` 语义：

- 左上角 `x`
- 左上角 `y`
- `width`
- `height`

### 8.4 ReID 属性解释

当前 ReID 属性解释来自用户提供的 C++ 逻辑：

- `/tmp/reidStructV4.cpp`
- `/tmp/reidStructAll.h`

对应函数：

```cpp
std::string getAttrString(std::vector<int> attr);
```

单个 ReID 值的规则：

- `val % 100` 是得分
- `val / 100` 是分类编号
- 得分大于阈值表示分类有效
- 第 `0` 位表示不确定

例如：

- `50`：不确定，得分 50
- `180`：分类 0，得分 80

当前项目已统一把分数和阈值都收敛为 `0~100` 整数语义，避免一部分地方是 `0~1` 浮点数、一部分地方是 `0~100` 整数的混用问题。

## 9. 计费设计

### 9.1 视频计费

视频有两次计费：

- 一期：上传后，根据视频总帧数计费
- 二期：获取结果时，根据序列数与总序列帧数计费
- 后台 API 计费金额统一按人民币分配置；注册用户钱包、包月额度和消费记录统一使用 CNY
- 英文页面只在展示层按 `cny_usd_exchange_rate` 折算美元估算；匿名 x402 支付按同一汇率把 CNY 订单金额折算成 USD/稳定币金额

### 9.2 序列计费

序列解析单次计费：

- 注册用户根据 SDK 输出序列个数计费
- 输入 1 个上传序列，如果 `GetSplitSeqFeature` 输出 3 个单人序列，注册用户按 3 个序列计费
- 注册用户输出为空时也按 1 个序列计费
- 匿名 x402 用户按输入序列个数计费；当前 Sequence API 一次输入 1 个序列，所以匿名调用按 1 个序列计费，不按拆分后的输出数量补扣费

### 9.3 注册用户扣费

注册用户采用钱包预充值模式：

- 充值单保留实际支付币种和金额，例如 CNY/USD
- 充值到账时统一折算成人民币分并写入 CNY 钱包
- API 消费优先扣包月 CNY 额度，再扣充值 CNY 余额
- 购买包月套餐时，用户页默认勾选自动续费
- 勾选自动续费时必须进入支付渠道签约授权；支付渠道不支持签约时返回明确错误，不允许只改本地开关
- 取消勾选自动续费时，优先从充值余额扣套餐支付金额；充值余额不足时创建整笔套餐金额的一次性支付订单
- 套餐生效期间关闭自动续费当前先更新本地状态；完整生产方案还需要调用支付渠道取消协议/订阅后再确认关闭
- 套餐生效期间重新开通自动续费必须重新进入支付渠道签约授权流程

- 序列在 `parse` 前自动扣费
- 视频在上传完成后自动尝试一期扣费
- 视频在获取结果时自动尝试二期扣费
- 扣费成功后推进任务
- 余额不足返回错误

### 9.4 财务收入确认口径

- 普通充值到账只增加用户充值余额，属于现金流入和负债变化，不直接确认收入
- 购买包月套餐按用户实际支付金额确认收入
- API 调用优先消耗套餐额度，套餐额度内消费不重复确认收入
- API 调用超出套餐额度后，从充值余额扣费的部分确认收入
- 匿名调用和 x402 调用按实际结算金额确认收入
- 财务管理页按“套餐购买收入 / 充值余额消费收入 / 匿名调用收入 / 充值现金流入”分开展示
- 财务管理页使用五张主表：“充值余额流水”展示充值余额增减，“套餐流水”展示套餐购买/发放/消费，“收入记录”只展示已确认收入事件，“充值记录”只展示充值申请、支付和到账状态，“匿名消费记录”单独展示匿名/x402 已支付调用

### 9.5 匿名支付

当前支付协议与网关支持：

- `mock`
- `x402`
- Hosted checkout
- Stripe
- Paddle
- WeChat Pay
- Alipay

其中：

- `mock` 已可用，用于联调
- `x402` 已接入匿名协议流
- `AP2` 暂未正式落地，保留后续支持空间

`x402` 当前代码内置了 CDP 官方支持矩阵说明，供外部客户端和门户读取：

- Base Mainnet
- Polygon Mainnet
- Arbitrum One
- World Chain
- Solana Mainnet

但当前部署是否真正开放这些链路，仍取决于本机配置出的 `project_supported_kinds`。

当前线上匿名调用实际开放的 x402 货币和网络：

| 网络 | 货币 | 支付方式 |
|---|---|---|
| Base Mainnet | USDC | EIP-3009 |
| Polygon Mainnet | USDC | EIP-3009 |
| Arbitrum One | USDC | EIP-3009 |
| Base Mainnet | USDT | Permit2 |
| Polygon Mainnet | USDT | Permit2 |
| Arbitrum One | USDT | Permit2 |
| Base Mainnet | EURC | EIP-3009，按后台 `eurc_usd_exchange_rate` 从 USD 金额换算 |

### 9.5 当前设计判断

对于匿名视频解析，当前方案采用：

- 创建任务
- 上传后生成账单
- 匿名支付后再处理

这是当前风险最低、状态最清晰的方案。

## 10. 支付与充值设计

### 10.1 注册用户充值

当前系统已经具备：

- 充值订单创建
- Hosted mock checkout
- 后台手工确认到账
- 充值记录展示

后续可接入正式支付方式：

- 微信支付
- 支付宝
- Stripe
- Paddle

### 10.2 国际化支付思路

面向全球用户的最终方向：

- 登录/门户页面根据浏览器语言自适应
- 根据用户国家与区域返回适合的支付方式
- 页面显示货币符号与计费文案本地化

当前代码里已预留：

- `preferred_locale`
- `display_currency`
- `cny_usd_exchange_rate`
- `country_code`

后续可以基于这些字段做国际化与地区支付路由。

## 11. 数据存储设计

### 11.1 对象存储

当前对象存储通过 `internal/storage` 抽象：

- 默认实现是本地文件系统
- 根目录由 `GAIT_OBJECT_STORE_ROOT` 或 `<GAIT_DATA_DIR>/objects` 决定
- 当前线上配置 `GAIT_DATA_DIR=/data/gaitagent`，未单独设置 `GAIT_OBJECT_STORE_ROOT` 时，对象存储根目录就是 `/data/gaitagent/objects`

存储内容包括：

- 视频原文件
- 序列帧图片
- 步态图
- 人脸图
- 结果资产

本地文件系统默认目录结构：

```text
<data_dir>/objects/videos/<video_task_id>/...
<data_dir>/objects/sequences/<sequence_task_id>/...
<data_dir>/objects/video-assets/<video_task_id>/...
<data_dir>/objects/sequence-assets/<sequence_task_id>/...
```

这些对象属于任务生命周期数据，会随任务状态和清理策略被删除。不要把它和 `<data_dir>/sequence_samples` 混淆；`sequence_samples` 是单独的样本归档目录，不参与普通任务 TTL 自动清理。

后续可替换为：

- S3
- MinIO
- OSS
- COS

### 11.2 PostgreSQL 持久化

当前已可选使用 PostgreSQL 存储：

- 视频任务
- 序列任务
- 用户账户
- API Key
- 钱包
- 钱包流水
- 充值记录
- 运行配置
- 后台审计日志
- 后台统计快照
- 账单订单
- 支付记录
- 任务事件

### 11.3 兼容策略

当前策略是：

- 没有 `GAIT_DB_DSN` 时，回退到本地文件模式
- 配置 `GAIT_DB_DSN` 后，启用 SQL 仓库

这样便于：

- 单机快速开发
- 平滑切换到数据库模式

## 12. 运行时配置与清理策略

### 12.1 配置来源

运行时策略由两部分组成：

- 环境变量默认值
- 运行时配置文件/数据库覆盖值

当前运行时配置支持：

- 计费参数
- 清理时长

### 12.2 清理时长

配置项包括：

- 上传未完成保留时长
- 一期支付等待时长
- 二期支付等待时长
- 成功结果保留时长
- 失败任务保留时长
- 已删除记录保留时长

管理后台页面已统一按“分钟”配置，不再混用 `h/m/s` 文本。

### 12.3 清理逻辑

当达到：

- `expire_at`：任务进入 `expired`
- `delete_after_at`：删除对象资产，任务变为 `deleted`

SQL 模式下当前保留：

- 子任务表记录会删掉
- 父任务 `tasks` 行做软删除保留
- `billing_orders`
- `payments`
- `task_events`

从而保证审计与对账能力。

## 13. 后台管理设计

### 13.1 管理后台页面

当前后台已具备：

- 登录页
- 左侧导航
- 运营看板
- 用户管理
- 财务管理
- 计费与清理设置
- 审计日志

### 13.2 看板内容

当前看板展示：

- 用户总数
- 活跃用户数
- 收入
- 视频处理量
- 序列处理量
- 硬件负载
- 钱包余额

### 13.3 图表

当前图表支持：

- 最近 24 小时
- 最近 7 天
- 最近 30 天

图表类别包括：

- 业务状态
- 视频处理量
- 序列处理量
- 硬件负载
- 资金概览

后续可继续增强：

- 直接基于 `task_events` 做事件序列图
- 更细的匿名 Agent 来源分析
- 地域/IP/设备维度统计

### 13.4 审计

后台操作审计记录包括：

- 修改计费设置
- 修改清理设置
- 用户补款
- 充值确认

后续可继续补充：

- 维护人员登录/退出
- API Key 批量禁用
- 匿名支付人工干预

## 14. 用户门户设计

当前用户门户已实现：

- 统一顶部导航：首页、产品能力、API 接入、Agent 接入、余额与充值、API Key 管理、计费方式、使用记录、Demo 下载
- 未登录首页试玩：以单行控件选择能力、文件、文字需求并发起免注册试用。图搜万物的文字需求提示示例统一为“猫、公交车、穿红衣服的人”；选择文件后在控件内显示文件名，单图搜万物只显示文件名，多文件能力显示首个文件名和总数。
- 产品说明页：身份识别、人体 2D/3D 关节点、图搜万物、API 接入、Agent 接入、计费方式和 Demo 下载
- 邮箱注册
- 邮箱密码登录
- 余额展示
- 充值入口
- 充值记录
- API Key 管理
- 消费记录

消费记录不再依赖任务文件本身。系统启用数据库后，所有 API 调用扣费都会写入 `usage_records`：

- 注册用户调用：钱包扣费成功后写入 `usage_records`
- 匿名 public 调用：x402 等匿名支付确认后写入 `usage_records`
- 免注册试用调用：试用成功后写入 `usage_records`，金额为 0，来源为 `trial`
- 任务、视频、图片过期清理时，不删除 `usage_records`
- 管理后台消费记录和导出优先读取 `usage_records`

设计原则：

- 门户用用户名/密码登录
- API Key 只用于接口调用，不用于门户登录
- 登录前后使用同一套导航语义；需要登录的菜单项在未登录时跳转登录，登录后进入对应用户中心 section
- 顶部左侧导航使用视口 fixed 定位，避免登录页、官网说明页、用户中心之间切换时因父容器 padding 或右侧账号宽度导致菜单左右抖动
- 支付方式不再是独立门户菜单；匿名 Agent 和 x402 支付路线归入 Agent 接入说明

## 15. 配置项设计

关键环境变量见 [internal/config/config.go](/home/watrix/tiandk/agent/gaitAgent/internal/config/config.go)。

常用项：

- `GAIT_API_ADDR`
- `GAIT_TEST_ADDR`
- `GAIT_ADMIN_ADDR`
- `GAIT_PUBLIC_BASE_URL`
- `GAIT_DATA_DIR`
- `GAIT_OBJECT_STORE_ROOT`
- `GAIT_WORKER_SOCKET`
- `GAIT_DB_DSN`
- `GAIT_ADMIN_EMAILS`
- `GAIT_ADMIN_TOKEN`
- `GAIT_PAYMENT_PROVIDER`
- `GAIT_CHECKOUT_DEFAULT_PROVIDER`

支付相关：

- `GAIT_STRIPE_*`
- `GAIT_PADDLE_*`
- `GAIT_WECHAT_PAY_*`
- `GAIT_ALIPAY_*`
- `GAIT_X402_*`

## 16. 当前实现状态总结

当前已经完成的主线能力：

- 视频解析接口
- 序列解析接口
- 用户注册/登录/API Key
- 钱包与充值
- 匿名支付基础能力
- 后台管理页面
- SQL 持久化
- 对象存储抽象
- 任务事件落库
- 后台统计 SQL 聚合优先

## 17. 已知限制

当前仍有限制：

- Worker 仍按单机模式设计
- 视频分布式调度尚未实现
- AP2 只保留接口规划，未正式接入
- 正式国际化语言包未落地
- 正式全球支付编排未全部完成
- 后台统计的 `timeseries` 仍主要基于快照采样，不是全量事件重建

## 18. 后续建议

建议后续按以下顺序推进：

1. 完成正式微信/支付宝接入
2. 完成多语言门户与支付方式自适配
3. 将 `timeseries` 进一步基于 `task_events`、`billing_orders`、`payments` 重建
4. 引入 worker lease 与多 worker 争抢机制
5. 引入对象存储云后端
6. 引入更严格的限流、幂等与风控
