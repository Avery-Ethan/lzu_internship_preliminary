# 测试 / 质量保障方向 · 第一轮摸底作业

> **校园好物市集** —— 对一个能跑起来的电商服务做质量检查  
> 开卷 48 小时 · 允许使用 AI 

## 0. 作业概览

| 层级 | 内容 | 预计用时 | 分值 |
|---|---|---|---|
| **L0 基础** | 测试计划、至少 15 条用例、至少 4 条缺陷、测试报告 | 3～4 小时 | **40 分** |
| **L1 进阶** | 至少 8 条自动化测试、至少 5 条代码审查意见 | 3～4 小时 | **15 分** |
| **L2 挑战，选做** | 安全专项、并发测试、CI、UI 自动化，任选 1～2 项 | 2～3 小时 | **10 分** |
| **表达与设计** | 报告质量、`DESIGN.md` | — | **15 分** |
| **AI 使用** | `AI_USAGE.md`、平台调用日志 | — | **20 分** |

**L0、L1 均需完成，L2 为选做。总分 100 分，及格线为 60 分。**

优先完成 L0，再推进 L1。设计说明和 AI 使用也会计入总分，L2 不做也有机会达到及格线。

服务中预埋了十几个问题，分布在认证、商品、订单、支付、评价五个模块。无需找全，先完成至少 4 条有证据的缺陷报告，找到 8 条已经非常优秀。

**每个缺陷都要有可复现的操作和真实返回，说明预期结果与实际结果的差异。**

## 1. 提交内容与目录

每人使用独立分支提交作业。文档和脚本直接放在 `testing/` 下，自动化脚本放在 `testing/自动化/` 下。

```text
你的分支
└── testing/
    ├── README.md          ← 题目（别删别改）
    ├── sut/               ← 被测服务（别改）
    ├── legacy/            ← 待审查代码（别改）
    ├── 测试计划.md
    ├── 测试用例.md
    ├── 缺陷报告.md
    ├── 测试报告.md
    ├── 代码审查.md
    ├── 自动化/
    ├── SUBMISSION.md
    ├── DESIGN.md
    └── AI_USAGE.md
```

评审时会切换到你的分支，独立检查你的作业。请按上述结构提交，避免增加 `testing/<学号>/` 这一层目录。

三份统一说明文档的用途如下。

| 文件 | 填写内容 |
|---|---|
| `SUBMISSION.md` | 环境、启动方式、完成情况、自检结果、未完成事项 |
| `DESIGN.md` | 工作拆分、实现思路、取舍和排错过程 |
| `AI_USAGE.md` | 模型选择、使用场景、验证过程和大致花费 |

具体填写要求见仓库 `templates/` 下的对应模板。

## 2. 第一个 30 分钟

```bash
# ① 起服务（零依赖，不用装任何东西）
python3 testing/sut/app.py
#   看到 "服务已启动: http://127.0.0.1:8080" 就行

# ② 健康检查
curl -s http://127.0.0.1:8080/health

# ③ 登录拿 token
curl -s -X POST http://127.0.0.1:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"Alice@123"}'

# ④ 用 token 查自己的资料
curl -s http://127.0.0.1:8080/api/users/2 -H 'Authorization: Bearer tk_2'

# ⑤ 关键一步：把 URL 里的 2 改成 3，再执行一次
```

第 ⑤ 步如果返回了"别人的真实姓名和手机号"——第一个问题找到了。
**记下命令、返回、预期、实际。** 这就是一份缺陷报告。

---

## 3. 怎么想测试点（方法比技巧重要）

拿到任何接口，先问这 6 个问题。**照着做，一个接口至少能想出 6 条用例：**

| # | 问题 | 电商场景的例子 |
|---|---|---|
| 1 | **正常**能不能用？ | 用正确参数下单，订单创建、库存减 1 |
| 2 | **少传/不传参数**？ | 不带 token、不带 productId、不带 quantity |
| 3 | **类型/格式不对**？ | `id=abc`、`quantity="两件"`、`price=19.9`（要整数分） |
| 4 | **边界值**？ | 库存 0 时下单、`quantity=1` / `库存+1`、`pageSize=0/51` |
| 5 | **该拦的人拦住了吗**？ | 没登录、看别人的订单、改别人的商品 |
| 6 | **重复操作**？ | 同一订单付两次款、重复提交订单、重复退款 |

> 第 2~6 条就是"异常"和"边界"。**只写第 1 条的人，用例数量再多也不及格。**
> **电商题特别提示**：金额和数量是重灾区——负数、0、小数、超大值，每个都要试。

---

## 4. 被测服务

### 4.1 启动与依赖

被测服务简称 **SUT（System Under Test）**，入口为 `testing/sut/app.py`。

在仓库根目录执行以下命令。

```bash
python3 testing/sut/app.py                # 默认 8080
python3 testing/sut/app.py --port 8090    # 换端口
```

服务仅使用 Python 标准库。启动时会自动重建数据库并写入种子数据，重启后恢复初始状态。

自动化测试需要安装 `pytest` 和 `requests`。以下两条命令任选一条，若提示 `pip` 命令不存在，使用 `pip3`。

```bash
pip install pytest requests
# 或
pip3 install pytest requests
```

安装遇到网络问题时，可在命令末尾添加 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。

### 4.2 缺陷证据要求

允许查看源码。每条 SUT 缺陷报告必须附上以下证据。

- 可直接复制执行的 curl 命令。
- 实际运行得到的真实返回片段。

只有源码推测、没有运行证据的缺陷报告不计分。并发超卖、支付回调、重复支付等问题需要通过实际执行确认。

L1-6 的 legacy 代码审查按该项要求提交文件行号、问题分析和建议。

### 4.3 种子数据

| 用户名 | 密码 | 角色 | userId |
|---|---|---|---|
| `admin` | `Admin@123` | admin | 1 |
| `alice` | `Alice@123` | user | 2 |
| `bob` | `Bob@123` | user | 3 |
| `carol` | `Carol@123` | user | 4 |
| `dave` | `Dave@123` | user | 5 |

初始商品共 12 个，ID 为 1～12，分类为数码、图书、服饰、食品、文具。

- id=5 的商品库存为 1，可用于并发测试。
- id=7 的商品已下架。
- 其余商品库存位于 3～50 范围内。
- 价格单位统一为分。

商品列表不传 `status` 时，默认只返回 11 个在售商品。

## 5. 接口文档

Base：`http://127.0.0.1:8080`，统一返回 `{ "code": 0, "message": "ok", "data": ... }`。
需要登录的接口带 `Authorization: Bearer <token>`。

### 5.1 `POST /api/auth/login`

```json
{ "username": "alice", "password": "Alice@123" }
// 200
{ "code": 0, "data": { "token": "tk_2", "userId": 2, "username": "alice", "role": "user", "expiresAt": "…" } }
```

### 5.2 `POST /api/auth/logout`（需登录）

```json
{
  "code": 0,
  "data": {
    "message": "已退出登录"
  }
}
```
> 文档承诺：登出后原 token **应失效**。

### 5.3 `GET /api/users/{id}`（需登录）

```json
{
  "id": 2,
  "username": "alice",
  "realName": "张爱丽",
  "phone": "13800138002",
  "role": "user"
}
```
> 文档承诺：**只能看自己**，看别人应 403。

### 5.4 `GET /api/admin/orders`（管理端，需登录）

```json
{
  "total": 1,
  "items": [
    {
      "id": 1,
      "orderNo": "SO…",
      "userId": 2,
      "userName": "alice",
      "productTitle": "…",
      "quantity": 2,
      "totalAmount": 3980,
      "status": "created",
      "receiverPhone": "…",
      "address": "…"
    }
  ]
}
```
> 文档承诺：**仅 admin 可访问**，普通用户应 403。

### 5.5 `GET /api/products?keyword=&status=&page=1&pageSize=10`

```json
{
  "total": 12,
  "page": 1,
  "pageSize": 10,
  "items": [
    {
      "id": 1,
      "title": "…",
      "price": 19900,
      "stock": 12,
      "category": "数码",
      "status": "on",
      "sellerId": 2,
      "sellerPhone": "13800138002",
      "createdAt": "…"
    }
  ]
}
```
> 文档承诺：`pageSize` 范围 **1~50**，超出应 400。

### 5.6 `GET /api/products/{id}`

返回单条；不存在 404 + `40401`。
> 文档承诺：`id` 不是数字时返回 **400**，不是 500。

### 5.7 `POST /api/products`（需登录）

`{ "title": "…", "price": 1990, "stock": 10, "category": "文具", "description": "…" }` → 201
校验：title 1~50 字、price 正整数分、stock 0~999、category 五选一。

### 5.8 `PATCH /api/products/{id}/status`（需登录）

`{ "status": "off" }` → `{"id":1,"status":"off"}`
> 文档承诺：**只能上下架自己发布的商品**，别人的应 403。

### 5.9 `POST /api/orders`（需登录，核心）

```json
// 请求（注意：文档里只有这两个字段）
{ "productId": 1, "quantity": 2 }
// 201
{ "code": 0, "data": { "id": 1, "orderNo": "SO202611190001", "productId": 1, "productTitle": "…",
  "quantity": 2, "unitPrice": 19900, "totalAmount": 39800, "status": "created",
  "receiverPhone": "13800138002", "address": "…", "createdAt": "…" } }
```

> 文档承诺：
> - 金额由**服务端**按商品价格 × 数量计算；
> - 库存不足 409；商品不存在 404；商品已下架 409；
> - **库存永远不能小于 0**；`quantity` 必须是正整数。

### 5.10 `GET /api/orders/{id}`（需登录）

```json
{
  "id": 1,
  "orderNo": "SO…",
  "userId": 2,
  "userName": "alice",
  "productTitle": "…",
  "quantity": 2,
  "unitPrice": 19900,
  "totalAmount": 39800,
  "status": "created",
  "receiverPhone": "…",
  "address": "…",
  "paidAt": null
}
```
> 文档承诺：**只能看自己的订单**，别人的应 403。

### 5.11 `GET /api/orders/mine`（需登录）

`{ "total": n, "items": [ … ] }`，按 id 倒序。

### 5.12 `POST /api/payments`（需登录）

```json
{ "orderId": 1, "method": "alipay" }
```

`method` 可选 `alipay` 或 `wechat`。
→ `{ "paymentId": "PAY…", "orderId": 1, "amount": 39800, "status": "paid", "paidAt": "…" }`
> 文档承诺：**同一订单只能支付一次**，重复支付应 409；订单不存在应 404。

### 5.13 `POST /api/payments/callback`（**公开**）

`{ "orderId": 1, "paymentId": "PAY…", "result": "success" }` → `{"orderId":1,"status":"paid"}`
> 文档承诺：**回调必须验签**（只接受平台签发的 paymentId 与正确签名），伪造请求应被拒绝。

### 5.14 `GET /api/product-reviews?productId=1`（返回网页）

`text/html` 的评价列表页，展示 username / rating 星 / content / 时间。
> 文档承诺：用户内容**必须做 HTML 转义**。

### 5.15 `POST /api/product-reviews`（需登录）

`{ "productId": 1, "content": "…", "rating": 5 }` → 201
> 文档承诺：`content` ≤200 字，`rating` 1~5。

### 5.16 `GET /health`

```json
{
  "status": "up",
  "uptime": 12.3
}
```

---


## 6. 各项要求

### L0-1 测试计划，一页

说明以下四项内容。

1. 测什么，覆盖哪些接口和测试方面。
2. 哪些内容暂不测试，以及原因。
3. 使用什么方法和工具，例如 curl、Postman 或脚本。
4. 达到什么条件可以结束本轮测试。

评审会关注范围选择及完成情况。计划应与实际执行相符。

### L0-2 测试用例，至少 15 条

按以下字段整理，示例行仅用于说明填写格式。

| 用例 ID | 模块 | 标题 | 类型 | 优先级 | 前置条件 | 步骤 | 测试数据 | 预期结果 |
|---|---|---|---|---|---|---|---|---|
| TC-001 | 认证 | 正确账号密码登录成功 | 正常 | P0 | SUT 已启动，存在 alice 用户 | 向登录接口发送 POST 请求，检查响应 | `username=alice`、`password=Alice@123` | HTTP 200，业务码为 0，返回 token，userId 为 2 |

验收要求如下。

- [ ] 正常、异常、边界三类都有，各至少 3 条。
- [ ] 每个接口至少 1 条。
- [ ] 测试数据具体，例如 `quantity=0`、`quantity=-1`、`quantity=999`。
- [ ] 优先级覆盖 P0、P1、P2。
- [ ] 至少 5 条涉及金额或库存。

### L0-3 缺陷报告，至少 4 条

参考以下格式填写。

````markdown
## BUG-01 普通用户可以查看其他用户的手机号

- **模块**　认证
- **严重程度**　S1 / S2 / S3 / S4
- **环境**　SUT 默认配置，8080 端口
- **前置条件**　使用 alice 登录，token 为 tk_2
- **复现步骤**　执行下面的请求命令
- **预期结果**　返回 HTTP 403，提示无权限
- **实际结果**　返回 HTTP 200，包含 bob 的 realName 和 phone
- **证据**

  ```bash
  curl -s http://127.0.0.1:8080/api/users/3 \
    -H 'Authorization: Bearer tk_2'
  ```

  ```text
  在此粘贴真实返回内容
  ```

- **影响**　登录用户可以通过修改用户 ID 获取其他用户的手机号
- **修复建议**　在处理函数中比对当前用户 ID 与路径 ID，无权限时返回 HTTP 403
````

验收要求如下。

- [ ] 每条都有可执行的 curl 命令和真实返回。
- [ ] 根据实际影响区分严重程度。
- [ ] 修复建议具体到修改位置或处理逻辑。
- [ ] 同根因问题合并为一条。

### L0-4 测试报告，一页

汇总以下内容。

- 测试用例数量和实际执行情况。
- 已测试的接口。
- 发现的问题数量，按模块和严重程度统计。
- 尚未覆盖的内容。
- 上线建议及主要依据。

### L1-5 自动化测试，至少 8 条

使用 `pytest` 和 `requests`，脚本放在 `testing/自动化/` 下。

从仓库根目录执行：

```bash
cd testing/自动化 && pytest -q
```

验收要求如下。

- 至少包含 3 条正常、3 条异常、2 条边界测试。
- 断言覆盖业务结果，包括响应中的业务码和数据字段。

断言示例：

```python
r = requests.get(f"{BASE}/api/products")

assert r.status_code == 200
assert r.json()["code"] == 0
assert r.json()["data"]["total"] == 12
```

断言应依据接口文档中的正确业务预期。因 SUT 缺陷导致的测试失败，需关联缺陷编号并说明原因。

提交前应排除依赖缺失、服务未启动、测试收集失败及脚本自身错误。业务预期与实际行为不一致的失败，应在测试结果中如实说明。

加分项为将端口、token 等通过 `conftest.py` 中的 fixture 管理，支持更换端口后执行。

### L1-6 代码审查，至少 5 条

审查 `testing/legacy/` 下的五个代码片段，涉及下单、支付、退款、数据库和缓存。

本项提交文件行号、问题分析、风险及建议，可通过静态阅读完成审查。

按以下格式整理。

| 序号 | 位置 | 问题类型 | 问题 | 风险 | 建议 |
|---|---|---|---|---|---|
| 1 | `payment_service.py:13` | 硬编码 | 商户密钥写在代码里 | 泄露后可伪造回调 | 移到配置或环境变量 |

验收要求如下。

- [ ] 位置必须写明文件名和行号。
- [ ] 至少覆盖 3 种问题类型，例如空指针、边界、异常被吞、硬编码、资源未释放、SQL 拼接、并发。

### L2 挑战，选做

任选 1～2 项，每项 6 分，两项合计最高 10 分。

| 编号 | 项目 | 要求 |
|---|---|---|
| L2-7 | 安全专项 | 认证、越权、输入、金额篡改四个方向，各至少 1 条实测记录 |
| L2-8 | 并发测试 | 10 个请求同时购买库存为 1 的商品 id=5，验证库存是否变负，并给出数字结论 |
| L2-9 | CI | 使用 GitHub Actions 启动 SUT 并运行 pytest，将结果贴到 PR |
| L2-10 | UI 自动化 | 使用 Playwright 打开 `/api/product-reviews?productId=1`，验证内容是否被转义 |

CI 应能完成服务启动和测试执行。测试结果按 L1-5 的要求提交，因 SUT 缺陷导致的失败需关联缺陷报告并说明原因。

## 7. 我们怎么打分

| 项 | 分值 | 具体看什么 |
|---|---|---|
| **L0 基础** | 40 | 计划 8 / 用例 14 / **缺陷 14** / 报告 4 |
| **L1 进阶** | 15 | 自动化 9 / 代码审查 6 |
| **L2 挑战** | 10 | 每个 6 分，两个封顶 10 |
| **表达与设计** | 15 | 缺陷写得清不清、报告有没有结论、`DESIGN.md` 实不实 |
| **AI 使用** | 20 | 见 README 第 10 节 |

**缺陷项给分（14 分）：**

| 有效缺陷数（有证据） | 分数 |
|---|---|
| 1~2 | 4~7 |
| 3 | 8~10 |
| 4~5 | 11~13（及格线） |
| 6~7 | 13~14 |
| ≥8 | 14（封顶） |

扣分：全填 S1（-1）、同根因拆多条（-1）、建议太笼统（-1）。
加分：找到必须动手跑才能发现的问题（并发、重复支付、回调伪造）单独记一笔。

---

## 8. 提交

L0、L1 均需完成，L2 为选做。以下为完整作业要求，未完成也应按时提交，并在 `SUBMISSION.md` 中写明完成情况和未完成事项。

### 8.1 开始作业时

在仓库根目录创建自己的提交分支，并复制说明模板。分支名中的学号和拼音替换为自己的信息。

```bash
git checkout -b submit/qa-<学号>-<拼音>
cp templates/SUBMISSION.md templates/DESIGN.md templates/AI_USAGE.md testing/
```

如果已经创建并处于自己的提交分支，继续在该分支完成作业。

### 8.2 完成后提交

文档直接放在 `testing/` 下，自动化脚本放在 `testing/自动化/` 下。填写三份说明文档后，提交并推送。

```bash
git add testing
git commit -m "test: 认证与商品接口用例集"
git push -u origin submit/qa-<学号>-<拼音>
```

推送后创建 PR，标题格式为 `[QA] 姓名 学号`，例如 `[QA] 张三 320210912345`。

### 8.3 提交前自检

以下清单用于核对完整作业的完成情况，未完成的项目在 `SUBMISSION.md` 中如实说明。

- [ ] 测试计划、测试用例、缺陷报告、测试报告和代码审查文档已完成。
- [ ] 已提交至少 8 条自动化测试，包含 3 条正常、3 条异常、2 条边界测试。
- [ ] 按 `SUBMISSION.md` 中的环境和启动步骤，能够从零启动被测服务。
- [ ] 缺陷报告包含必要的前置步骤、可复制执行的 curl 命令和真实返回，能够复现问题。
- [ ] 在服务运行时，从仓库根目录执行 `cd testing/自动化 && pytest -q`，并将真实测试结果记录到 `SUBMISSION.md`。
- [ ] 已排除运行环境和脚本自身问题。因 SUT 缺陷导致的测试失败已关联缺陷报告并说明原因。
- [ ] `SUBMISSION.md`、`DESIGN.md`、`AI_USAGE.md` 三份说明文档均已填写完整。