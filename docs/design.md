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

本项目基于 `algorithms/sdk` 对外提供一个可公开访问的步态解析服务，支持以下核心能力：

- 解析步态序列
- Gait Pose 单独解析

其中步态序列解析和 Gait Pose 均以已跟踪完成的人体序列作为输入。

服务同时支持两种使用方式：

- 注册用户模式：邮箱注册、密码登录、预充值、生成 API Key，后续按调用扣费
- 匿名 Agent 模式：不注册账号，通过匿名任务创建与单次支付完成调用

接口边界上只保留两类公开调用路径：

- 注册用户走私有接口 `/v1/sequences`
- 匿名用户或 Agent 走公开接口 `/v1/public/sequences`

当前已经不再支持“匿名但非 public”的私有任务模式。

系统设计目标：

- SDK 只在本机 worker 进程中加载，不暴露在 HTTP 进程中
- HTTP 服务支持公网访问
- 任务、计费、支付、用户、后台管理等能力可以独立演进
- 当前先保证单机可用，后续可演进到 API/Worker 分离部署

## 2. 功能范围

### 2.1 步态序列解析

用户上传一个已经跟踪完成的单序列图片集合，返回：

- 步态特征
- 人脸特征
- ReID 特征
- ReID 结构化属性
- 步态图
- 人脸图

序列任务流程：

1. 创建任务
2. 获取每帧 `object_key` 和可解析 `upload_token` 的 `upload_url`
3. 通过 `/uploads/batch` 一次性上传该序列的全部帧图片
4. 发起解析
5. 支付费用
6. 同步返回结果
7. 到期自动删除资产与记录

### 2.2 Gait Pose 单独解析

Gait Pose 是从完整步态序列解析里拆出来的独立能力，底层调用 SDK 的 `agentGaitGetSeqGaitPose` 接口。

输入仍然是已经跟踪完成的单序列图片集合，返回：

- 每帧对齐信息
- 2D 人体关节点
- 3D 人体关节点
- 情绪输出字段

Gait Pose 不返回 gait、face、ReID 特征，也不复用完整步态识别结果。它是单独接口、单独扣费，计费为“人体关节点每个序列费用 + 可选序列帧费用”。当后台 `sequence_per_k_frames` 非 0 时，人体关节点和步态序列解析会按序列帧数向上取整到 100 帧后叠加帧费；为 0 时不收这部分费用。

### 2.3 单图特征接口

系统还提供两个同步单图特征接口：

- 人脸识别：`POST /v1/features/face`，输入一张已经矫正的人脸图片，worker 调 SDK `GetFaceFeature` 返回 512 维人脸特征。
- ReID识别：`POST /v1/features/reid`，输入一张人体图片，worker 调 SDK `GetReidFeature` 返回 512 维 ReID 特征。

这两个接口不创建 sequence/video 任务，不把 512 维特征写入任务表；API 进程负责鉴权、计费、钱包扣费和使用流水，worker 只负责 SDK 计算。计费按独立的每千帧配置项计算，单张图片按 1 帧向上取整到 0.01 元。

官网首页的人脸识别/ReID识别体验上传图片 1、图片 2，在浏览器侧生成候选框并裁剪选中的候选区域，再调用对应单图特征接口计算点积相似度。人脸识别首页使用于诗琪 `libfacedetection` 编译出的 `facedet_wasm.js/.wasm` 做人脸框和 5 点关键点检测，并用双眼关键点在浏览器 Canvas 中矫正成 112x112 人脸图；ReID 首页使用现有 `persondet` 人体检测代码生成人体候选框。人脸检测在浏览器 Worker 中执行，输入图最长边按 1280 缩放；ReID 人体检测也优先在 Worker 中执行，输入图最长边按 640 缩放。服务端 API 只接收已经准备好的单张人脸或人体图片，不在服务端做检测、矫正或裁剪。

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
- API 与 worker 必须共享同一份对象存储根目录（`GAIT_OBJECT_STORE_ROOT`，未设置时为 `<GAIT_DATA_DIR>/objects`），否则 worker 读不到 API 接收的上传文件，API 也读不到 worker 生成的结果资产
- 当前账户、钱包和任务处理仍按单实例 API/单机 worker 运行边界设计；钱包余额事务只由单个 API 进程处理，worker 不创建账户服务、不缓存钱包、不做充值结算或扣款。多 API 实例或多机 worker 需要补数据库行锁/版本控制、worker lease、任务抢占和远程对象存储。

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
- `internal/trialusage`：免注册试用额度计数，按 IP + 算法分桶累计试用金额；图搜万物、人体关节点、步态序列各自拥有独立试用额度
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

worker 进程不负责钱包和账户资金状态：不装配 `accounts.Service`，不调用钱包扣款、充值结算、后台补款/扣款或套餐续费入口；这些事务统一由 API 进程执行。

注册用户 gait 特征旋转也属于用户隔离逻辑，由 API 进程负责。worker 只产出和保存 SDK 原始特征，不读取用户 seed、不缓存用户旋转矩阵；完整结果 JSON 存对象文件，任务表只保存 `result_object_key` 和结构化小字段。API 在返回注册用户序列结果前按用户稳定 seed 生成或复用 512x512 旋转矩阵并执行旋转。

## 5. 对外接口设计

接口总说明见 [api.md](/home/watrix/tiandk/agent/gaitAgent/docs/api.md)。

这里给出设计层面的接口分类。

### 5.1 公开解析接口

匿名或 Agent 可用：

- `POST /v1/public/sequences`
- `POST /v1/public/sequences/{task_id}/uploads/batch`
- `POST /v1/sequences/{task_id}/uploads/batch`
- `POST /v1/public/sequences/{task_id}/parse`
- `POST /v1/public/sequences/{task_id}/gait-pose`
- `POST /v1/public/sequences/{task_id}/settle`
- `GET /v1/public/sequences/{task_id}`
- `GET /v1/public/sequences/{task_id}/result`

### 5.2 注册用户接口

门户与 API Key 模式：

注册用户任务接口包括：

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
- `POST /v1/admin/users/batch`
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

- 序列图片批量上传依赖从 `upload_url` 中解析出的 `token=...`
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

步态序列解析使用 SDK 的 `GetSplitSeqFeature`。一个输入跟踪序列可能拆分成多个单人输出序列，用于处理串框、前后不同人或中间混入其他人的情况；SDK 可能丢弃不稳定帧。HTTP 响应通过 `sequences` 返回全部拆分后的单人序列，`sequence_count` 是返回数量。
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
<data_dir>/sequence_samples/<YYYY-MM-DD>/user/<user_id>/<task_id>/
<data_dir>/sequence_samples/<YYYY-MM-DD>/anonymous/<anonymous_owner_id>/<task_id>/
```

步态序列解析接口会保存用户上传的人形小图帧。

每个归档目录包含 `frames/`、`metadata.json`、`result.json`。该目录由管理人员自行拷贝和删除，业务清理任务不会删除它。
`<YYYY-MM-DD>` 使用任务创建时间所在服务器本地日期；管理人员可以直接按日期目录拷贝或删除一天的数据。

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
- 英文页面只在展示层按 `cny_usd_exchange_rate` 折算美元估算；匿名 x402 支付按同一汇率把 CNY 订单金额折算成 USD/稳定币金额。CNY 转 USD 后统一按 USD cent 向上取整，任何正数美元金额至少显示或收取 `$0.01`。

### 9.2 序列计费

步态序列解析单次计费：

- 注册用户根据 SDK 输出序列个数计费
- 输入 1 个上传序列，如果 `GetSplitSeqFeature` 输出 3 个单人序列，注册用户按 3 个序列计费
- 注册用户输出为空时也按 1 个序列计费
- 匿名 x402 用户按输入序列个数计费；当前 Sequence API 一次输入 1 个序列，所以匿名调用按 1 个序列计费，不按拆分后的输出数量补扣费

### 9.3 单图特征计费

- 人脸识别使用 `face_per_k_frames`，默认 100 分/千帧，即 1 元/千帧；单张图片按 1 帧计费并向上取整到 1 分。
- ReID识别使用 `reid_per_k_frames`，默认 100 分/千帧，即 1 元/千帧；单张图片按 1 帧计费并向上取整到 1 分。
- 注册用户调用成功后写钱包扣费流水和 usage ledger，reason code 分别为 `face_feature_once`、`reid_feature_once`。
- 免注册试用路由为 `POST /v1/public/features/trial/face` 和 `POST /v1/public/features/trial/reid`，分别消耗 `face_feature`、`reid_feature` 独立试用额度桶，不扣注册用户钱包。

### 9.4 注册用户扣费

注册用户采用钱包预充值模式：

- 充值单保留实际支付币种和金额，例如 CNY/USD
- 充值到账时统一折算成人民币分并写入 CNY 钱包
- API 消费优先扣包月 CNY 额度，再扣充值 CNY 余额
- 购买包月套餐时，用户页默认勾选自动续费
- 微信、支付宝充值和购买套餐使用 CNY；不再支持 PayPal、国际卡、Apple Pay、Google Pay 等国际 checkout 通道
- 购买套餐必须按用户选择的支付方式执行：选择余额时立即从 CNY 余额扣款并发放套餐实例；选择第三方支付时，支付成功回调前不能改变现有套餐实例
- 充值和购买套餐的第三方支付订单必须复用同一个 checkout deposit 创建入口：统一解析 provider/channel、统一处理 CNY/USD、统一写 `account_deposits` 和 checkout session；业务差异只放在 `detail_json.purchase_kind` 以及支付成功后的后置动作
- 套餐可以同时订购多个；每次购买生成独立套餐实例，独立维护剩余额度、到期时间和自动续费状态
- 同一个套餐多次购买时可以有多个实例，但同一套餐 ID 最多一个实例开启自动续费；新实例开启自动续费会关闭同套餐其他实例的自动续费
- 自动续费只从 CNY 充值余额扣款；续费前 3 天发送提醒，余额不足时发送续费失败提醒
- 自动续费在到期前约 1 天开始尝试扣款；扣款成功后新套餐实例从原套餐到期时间继续顺延 30 天，避免提前扣费导致周期缩短
- 自动续费失败后按自然日重试：到期日前一天、到期日当天、到期日后一天最多各尝试一次，连续 3 次失败后才关闭该套餐实例的自动续费
- `renewal_key` 记录某个本地日期已经尝试过，例如 `2026-07-10`，用于防止同一天重复扣款；不能作为永久取消自动续费的标记
- API 消费按最早到期优先扣套餐实例额度，不足部分再扣 CNY 充值余额

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
- 财务管理页按“套餐购买收入 / 充值余额消费收入 / 匿名调用收入 / 充值现金流入 / 支出”分开展示
- 财务管理页支出当前只有“代理商费用”：按客户充值到账时代理商处于启用状态的充值金额和代理商分成比例计算预计应付佣金；该金额用于经营统计和线下结算参考，不表示系统已自动打款
- 周报、月报、年报营收报表也按相同口径展示“支出 / 代理商费用”，用于财务线下结算参考
- 财务管理页使用五张主表：“充值余额流水”展示充值余额增减，“套餐流水”展示套餐购买/发放/消费，“收入记录”只展示已确认收入事件，“充值记录”只展示充值申请、支付和到账状态，“匿名消费记录”单独展示匿名/x402 已支付调用；后台主要列表统一展示序号列，方便运营按当前筛选和分页位置沟通记录

### 9.5 代理商分成设计

代理商能力用于线下销售和渠道推广。系统第一版负责代理商账号、客户归属、充值统计、应得收入计算和短信通知，不在系统内做提现、自动打款或结算状态流转。

第一版设计口径：

- 后台账号分为超级管理员和代理商账号；现有 `admin` 是超级管理员，拥有全部权限
- 超级管理员可以创建、编辑、停用代理商账号
- 代理商账号字段包括邮箱、手机号、姓名、登录密码、4 位代理编号、分成比例和启用状态
- 代理商默认分成比例为 40%，可由超级管理员按代理商单独配置
- 代理商分成比例变更会写入费率历史；收益统计按客户充值到账时间取当时已生效费率，后续调高或调低比例不会回算历史充值
- 代理商使用手机号和密码登录运维后台
- 代理商只能查看自己发展的客户列表、客户充值明细、客户充值汇总和应得收入，不查看客户 API 消费明细
- 代理商不能访问系统配置、支付配置、全部用户、全部财务、任务管理、审计日志等超级管理员页面

用户注册页新增推荐码输入框：

- 不填写推荐码时，用户不绑定代理商
- 填写有效 4 位推荐码时，注册成功后用户绑定到对应代理商
- 填写无效推荐码时，前端提示用户确认；用户确认继续注册后，后端按空推荐码处理
- 用户绑定代理商后，成功充值在代理商启用分成周期内计入该代理商收益
- 停用或删除代理商后，历史客户归属保留，但老客户后续充值不再计入该代理商收益
- 重新启用代理商后，历史客户仍属于该代理商；重新启用后的客户充值会继续计入收益，停用期间的充值不补算
- 客户管理列表和导出需要展示推荐码、代理商姓名、代理商手机号或邮箱

代理商佣金按客户实际充值到账金额计算，不按客户 API 消费金额计算：

```text
代理商应得收入 = 代理商客户充值到账金额 * 充值到账时生效的代理商分成比例
```

统计口径：

- 当期注册客户数：统计周期内注册并绑定该代理商的客户数
- 当期付费客户数：统计周期内至少有一笔成功充值到账的去重客户数
- 当期充值总额：统计周期内该代理商客户成功充值到账金额合计，统一按实际入账 CNY 金额计算；外币充值优先使用充值明细中的 `credit_amount` / `credit_currency`
- 当期应得收入：每笔当期充值按到账时生效费率分别计算后汇总
- 上述统计按代理商状态事件判断充值到账时是否处于启用状态；停用期间和删除后的充值不会进入分成统计
- `account_deposits` 是充值记录快照，保存充值金额、渠道、状态和到账时间；代理商费率使用 `sales_agent_rate_events` 单独保存历史，避免调整当前费率影响历史报表

代理商看板展示两个摘要卡片：

- 客户：累计客户数、当期注册客户数、当期充值客户数
- 收入：累计收入、当期客户充值收入、当期应得收入
- 时间筛选支持手动开始/结束日期，以及“今年、上月、当月”快捷范围
- 客户列表和充值明细分页展示并带序号列；充值明细展示订单、用户 ID、手机号、邮箱、金额、渠道和到账时间

短信通知：

- 每月底自动发送一次月度收益短信
- 短信内容包含当月付费客户数和当月可获得收入
- 短信只做通知，具体结算和打款由财务线下处理
- 当前短信发送复用后台阿里云短信账号、签名和 Endpoint；代理商通知使用独立的通知模板 Code
- 代理商通知模板变量为 `customer_count`、`commission_amount`
- `commission_amount` 只传数字，不带 `元`

短信模板：

```text
本月收益统计：付费客户${customer_count}人，预计应得收益${commission_amount}元。
```

短信示例：

```text
本月收益统计：付费客户38人，预计应得收益3440.00元。
```

第一版不实现：

- 代理商提现
- 自动打款
- 已结算/未结算状态
- 系统内结算按钮
- 客户 API 消费明细给代理商查看

### 9.6 匿名支付

当前支付协议与网关支持：

- `x402`
- Hosted checkout: WeChat Pay, Alipay
- Crypto recharge: third-party crypto checkout provider

其中：

- `x402` 已接入匿名协议流
- WeChat Pay / Alipay 用于人民币充值和套餐购买
- Crypto recharge 只用于余额充值。用户选择金额、网络和币种后，服务端向第三方支付 provider 创建付款订单，provider 返回付款地址/金额/二维码信息，并通过已验签 webhook 通知到账；服务端复用 `SettleDeposit` 结算到 CNY 钱包。系统不使用固定收款地址扫链，也不保存钱包私钥，不做自动退款，不直接用于套餐购买。
- PayPal、国际卡、Apple Pay、Google Pay、Stripe、Paddle、Airwallex checkout 当前不支持，用户和管理页面不展示。

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

### 9.7 当前设计判断

## 10. 支付与充值设计

### 10.1 注册用户充值

当前系统已经具备：

- 充值订单创建
- Hosted mock checkout
- 后台手工确认到账
- 充值记录展示

充值和套餐购买不维护两套支付分支。两者都先创建 `account_deposits` 内部订单，再调用统一 checkout 创建逻辑：

- 普通充值：`purchase_kind` 为空，支付成功后把实际支付金额折算为 CNY 充值余额
- 套餐购买：`detail_json.purchase_kind=monthly_plan`，支付成功后先确认充值/支付订单，再按套餐 CNY 标价扣款并发放独立套餐实例
- 微信、支付宝走 CNY checkout，并记录 `checkout_amount`、`checkout_currency`
- 新增支付渠道时必须优先接入公共 checkout provider 和公共订单创建逻辑，避免充值与套餐购买出现不一致行为

当前注册用户在线支付方式：

- 微信支付
- 支付宝

### 10.2 国际化支付思路

PayPal、国际银行卡、Apple Pay、Google Pay 依赖境外收单主体或海外 PSP，当前产品不再规划支持。国际用户如需注册用户充值或购买套餐，也只展示支付宝、微信；匿名 API 仍可按 x402 路径支付。

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

当前服务强制使用 PostgreSQL 存储，API 和 worker 启动时都必须配置 `GAIT_DB_DSN` 并成功连接数据库：

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

### 11.3 启动约束

当前策略是：

- `GAIT_DB_DSN` 是必填项
- `GAIT_DB_DSN` 使用 PostgreSQL DSN 格式：`postgres://<用户名>:<密码>@<主机>:<端口>/<数据库名>?sslmode=disable`
- 本机部署示例：`postgres://gaitagent:<password>@127.0.0.1:5432/gaitagent?sslmode=disable`
- systemd 部署时分别写入 `/etc/gaitagent/gait-api.env` 和 `/etc/gaitagent/gait-worker.env`
- API 启动时如果 `GAIT_DB_DSN` 为空或数据库不可连接，会直接启动失败
- Worker 启动时如果 `GAIT_DB_DSN` 为空或数据库不可连接，也会直接启动失败
- 本地对象存储仍保存上传文件、结果资产和 Demo 静态资源；财务、账户、任务、统计、审计、运行配置等元数据不再回退到 JSON/文件存储
- API/worker 正常启动不会自动读取或导入本地账户 JSON；如需历史数据导入，必须使用单独的显式迁移工具

## 12. 运行时配置与清理策略

### 12.1 配置来源

运行时策略由两部分组成：

- 环境变量默认值
- 运行时配置文件/数据库覆盖值

当前运行时配置支持：

- 计费参数
- 清理时长
- 支付配置
- 包月套餐
- 免注册试用
- 注册用户策略
- 图搜万物
- 短信、报表和门户信息

### 12.2 清理时长

配置项包括：

- 上传未完成保留时长
- 一期支付等待时长
- 二期支付等待时长
- 成功结果保留时长
- 失败任务保留时长
- 过期任务转已删除摘要前的保留时长

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

用户管理列表展示用户 ID、邮箱、手机号、充值余额、套餐余额、累计充值、累计补款、累计扣款、最近消费、API Key 数量、活跃天数和注册时间。累计补款统计后台补款流水，累计扣款只统计后台扣款流水，不等同于用户正常 API 消费。搜索框支持按邮箱、手机号或用户 ID 过滤；用户详情页和导出 CSV 也包含手机号和用户 ID，便于排查短信注册用户和按账户定位旋转矩阵、钱包流水、使用记录。用户详情中的账户流水查询支持指定开始日期和结束日期，按该时间范围加载全部账户流水，并可导出 CSV 明细；账户变动记录展示扣费方式，并按套餐和充值余额分别展示余额。用户、钱包、API Key 和订阅作为热数据加载到内存；管理列表使用后端全量搜索和服务端分页，每次只返回当前页，避免浏览器解析几十万用户的 JSON。

网页客户端的人体检测优先使用官方 `onnxruntime-web` WASM 运行 `gait_detect.onnx`，模型固定输入为 `1x3x352x640`，浏览器端会把检测图缩放到该尺寸并把输出框映射回原图/视频坐标。Python 本地视频示例使用同一个 ONNX 模型和 `onnxruntime` CPU 推理；C++ 本地视频示例使用包内 Linux x64 CPU 版 ONNX Runtime 和同一个 ONNX 模型。人体关节点和步态识别的视频转序列流程共用该检测器。ONNX 后端不可用时，浏览器依次回退到原 C++ detector 编译的 WASM 和 JavaScript 权重 detector。`/portal/browser-assets` 提供 ORT JS、ORT WASM、ONNX 模型和旧 detector 资源；资源下载包也包含这些文件，保证示例包自洽。

财务管理页的主接口只返回收入、资金流入、支出等 summary。充值余额流水、套餐流水、消费记录、匿名收入和充值记录分别走独立分页接口；前端翻页和筛选只刷新对应表格，避免一次性把多类流水样本推给浏览器。

代理商管理第一版已接入管理后台。超级管理员视角可以创建代理商账号、配置推荐码和分成比例，并查看代理商客户数量、当月收入、累计收入、启停记录、客户、充值汇总和充值明细；代理商视角登录后只显示自己的客户、充值明细和两卡片摘要（客户、收入）。客户列表和充值明细分页展示，充值明细包含用户 ID、手机号和邮箱，便于代理商核对客户付款。所有代理商数据查询必须在后端按当前代理商 ID 做过滤，不能只依赖前端隐藏菜单。

### 13.2 看板内容

当前看板展示：

- 用户总数
- 活跃用户数
- 收入、支出、业务量
- 每日业务量图
- 每日确认收入图
- 活跃用户数图

运营中心当前是自动化运营的第一版数据底座，不单独写新的事件流，而是从现有事实表实时聚合近 30 天运营数据：

- 新增注册
- 免注册试用调用
- 注册 API 调用
- 匿名付费调用
- 创建充值与充值到账
- 套餐购买
- 低余额用户
- 7 天内套餐到期用户
- 视频/序列失败和过期任务
- 最近关键事件

### 13.3 图表

当前图表支持：

- 最近 7 天
- 最近 30 天
- 最近 90 天
- 最近 1 年
- 累计范围

横轴单位支持：

- 天
- 周
- 月

图表类别包括：

- 业务量：视频 K 帧、步态序列数、关节点序列数、图搜万物帧数
- 每日确认收入：匿名收入、注册用户收入、总收入、资金流入、代理商费用
- 用户：活跃用户数、新增用户数

后台不展示区间累计收入图。图表保留悬停查看点位数据和拖拽查看区间；鼠标滚轮不触发图表缩放，避免滚动页面时误缩放。

后续可继续增强：

- 直接基于 `task_events` 做事件序列图
- 更细的匿名 Agent 来源分析
- 地域/IP/设备维度统计

### 13.4 审计

后台操作审计记录包括：

- 修改计费设置
- 修改清理设置
- 用户补款、扣款
- 充值确认

后续可继续补充：

- 维护人员登录/退出
- API Key 批量禁用
- 匿名支付人工干预

## 14. 用户门户设计

当前用户门户已实现：

- 统一顶部导航：首页、产品&API、X402 支持、计费&充值、API Key 管理、资源下载
- 未登录首页试玩：按首页顺序提供图搜万物、人体2D/3D关节点、步态识别、人脸识别、ReID识别。图搜万物上传图片并输入目标文本后调用试用接口；人体关节点和步态识别在新页面打开浏览器客户端，支持示例视频和用户本地视频；人脸识别和 ReID识别上传两张图片，在浏览器侧检测候选目标，点击画面候选框或候选卡片选择目标后比对相似度。
- 试用计费提示：每个算法有独立免注册试用额度；试用额度不足时统一提示“当前算法免注册试用额度已用完，请「登录」后使用。”；批量调用提示跳转产品&API页并高亮对应能力。
- 首页示例资源：图搜万物示例图片、人体关节点/步态示例视频、人脸/ReID示例图片均从 `/portal/examples/` 读取；人脸/ReID示例图片点击后会自动加载为图片1/图片2并运行浏览器检测。
- 产品说明页：身份识别、人体 2D/3D 关节点、图搜万物、API 接入、Agent 接入、计费方式和资源下载
- 邮箱注册
- 邮箱密码登录
- 余额展示
- 充值入口
- 充值记录
- API Key 管理
- 消费记录

API Key 管理页不在列表中展示累计金额；每个 API Key 通过“查看”打开使用记录弹窗。弹窗展示 UTC 日期口径的日汇总，支持日期范围和类型筛选，筛选请求由后端按 `api_key_id`、UTC 日期范围和类型查询 `daily_api_key_usage_summary`，底部展示当前筛选条件下的累计金额。为避免长期历史数据导致单次查询过大，日汇总查询和导出单次时间跨度限制为不超过半年；导出必须提供开始日期和结束日期。导出文件不导出汇总行，而是按当前 API Key、日期范围和类型从 `account_wallet_ledger` 导出明细流水，按时间由近到远排列，便于核对每一次实际扣费。

消费记录不再依赖任务文件本身。系统启用数据库后，所有 API 调用扣费都会写入 `usage_records`：

- 注册用户调用：钱包扣费成功后写入 `usage_records`
- 匿名 public 调用：x402 等匿名支付确认后写入 `usage_records`
- 免注册试用调用：试用成功后写入 `usage_records`，金额为 0，来源为 `trial`
- 任务、视频、图片过期清理时，不删除 `usage_records`
- 管理后台消费记录和导出优先读取 `usage_records`

高容量使用记录采用三层存储策略：

- 热明细层：PostgreSQL 下 `usage_records` 按 `created_at` 做月度 range 分区，默认分区兜底接收异常日期数据，在线库默认只保留最近 3 个月
- 汇总层：`daily_usage_summary` 保存按天、来源、算法、币种聚合后的调用次数、金额、帧数和序列数；`daily_api_key_usage_summary` 保存按天、用户、API Key、算法、币种聚合后的调用次数、金额、套餐抵扣、帧数和序列数；周报、运营看板、财务总览和 API Key 使用统计优先读汇总表
- 冷归档层：旧月分区通过归档任务转移到归档 PostgreSQL 库；归档库可放在机械盘目录或单独机器上，按月保留完整原始明细，便于审计和追查
- `usage_record_keys` 保存全局去重键，避免 PostgreSQL 分区表唯一约束必须包含分区键导致跨月幂等失效
- 业务写入路径追加 `usage_records` 时同步更新 `daily_usage_summary` 和 `daily_api_key_usage_summary`

归档相关环境变量：

- `GAIT_USAGE_ARCHIVE_ENABLED`：是否启用使用记录归档执行器，默认 `false`
- `GAIT_USAGE_ARCHIVE_DSN`：归档 PostgreSQL DSN，例如指向机械盘上的归档库
- `GAIT_USAGE_ONLINE_RETENTION_MONTHS`：在线库保留月数，默认 `3`，必须大于 0

归档执行规则：

- 按月归档，不按天归档。因为 `usage_records` 是月度分区，整月导出、校验、`DETACH PARTITION`、`DROP TABLE` 的成本和风险都远低于在月分区内按天删除。
- API 进程启用归档后，每天 00:00 后检查一次到期分区；同一天只执行一次。
- 保留月数按“当前月 + 往前 N-1 个整月”计算。例如 2026-07-01 且保留 3 个月时，保留 2026-05 到 2026-07，归档 2026-04 及更早分区。
- 每个到期分区会复制到归档库同名表 `usage_records_YYYY_MM`，归档库同时维护 `usage_archive_manifests`，记录行数、时间范围和保留的幂等键数量。
- 归档成功后保留对应月份的 `usage_record_keys`，只 drop 已 detach 的月分区；`daily_usage_summary` 长期保留，周报和运营看板仍可展示历史汇总。
- 管理后台查询近期明细时查在线库 `usage_records`；查询历史明细时可以按月份定位归档库表，例如 `usage_records_2025_07`。
- 手动命令 `cmd/usagearchive` 支持 `-dry-run` 和 `-execute`，上线前应先 dry-run 确认只命中预期月份。

管理后台只应配置归档策略，例如保留月数和启停；归档库 DSN 属于部署参数，放在环境变量里。

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

- `GAIT_WECHAT_PAY_*`
- `GAIT_ALIPAY_*`
- `GAIT_X402_*`

## 16. 当前实现状态总结

当前已经完成的主线能力：

- 步态序列解析接口
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
