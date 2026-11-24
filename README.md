# S4-FIN-010 · 企业开票资料的维护、校验与脱敏

ClawHunt 工单 **#2874** 交付候选。本仓库实现会员空间平台「回款与开票对接」模块中的
**企业开票资料（company_invoice_profiles）** 管理接口，包括：

- 开票资料模型与 Alembic 迁移（含业务表通用字段、软删除）；
- GET / POST / PATCH / DELETE 四组接口（列表、详情、创建、修改、删除）；
- 纳税人识别号校验器（15 / 18 / 20 位；18 位按统一社会信用代码校验位规则）；
- 专票四项必填校验、抬头与 CRM 企业名不一致需填写原因；
- 一家企业多份资料、唯一默认（部分唯一索引兜底）；
- 银行账号脱敏（列表只显示后 4 位，完整账号仅财务角色可见）；
- 每次修改写审计（前后快照 + 字段级差异，同事务落库）；
- 校验单元测试、接口测试、数据库约束测试、OpenAPI 描述与 README。

- 数据库：PostgreSQL 16（本次实测见 `evidence/test-results.txt` 末尾版本行）
- 运行环境：Python 3.12（要求 3.11+）
- 测试结果：**94 passed**（真实 PostgreSQL，见 `evidence/test-results.txt`）
- 迁移证据：upgrade → downgrade → upgrade → `alembic check` 零漂移，见
  `evidence/migration-check.txt`
- 运行时冒烟：真实 HTTP 验证四条验收标准，见 `evidence/runtime-smoke.txt`
- OpenAPI：`docs/openapi.json`（2 个路径 / 5 个操作）

> **边界声明（先读）**
>
> 1. 本单只做**开票资料的维护、校验与脱敏**。开票申请、发票开具、红冲、
>    回款核销均不在本单范围。
> 2. S2-CRM（企业对象）按工单允许的方式用**接口桩**先行：`app/crm.py` 从
>    JSON 名册读取企业名与租户归属，生产替换为 CRM 内部接口，详见 §7。
> 3. S2-AUDIT（审计日志）同样用**本地桩**先行：`app/audit.py` 把审计写入
>    本模块的 `finance_invoice_profile_change_log` 表（同事务），生产替换为
>    审计服务客户端，载荷形状不变，详见 §7。
> 4. 身份与角色（财务角色判定）来自网关注入的受信头（S2-IAM 桩），
>    生产替换为 IAM introspection，详见 §7。
> 5. 全部测试数据为虚构 UUID、虚构企业名与虚构账号，不含客户名称、真实
>    企业或个人信息；不引入任何向境外发送数据的第三方 SDK；配置与连接串
>    只从环境变量读取。
> 6. 工程骨架（分层结构、通用字段 mixin、测试基建）复制自同项目
>    S3-SALES-016 交付模板，业务代码按本单需求实现。

---

## 1. 范围

| 做 | 不做 |
|---|---|
| `company_invoice_profiles` 模型、迁移、四组接口 | 开票申请 / 发票开具 / 红冲流程 |
| 税号 15/18/20 位校验，18 位 USCC 校验位 | 税号真实性核验（工商 / 税务接口） |
| 专票四项必填、抬头不一致需原因 | 抬头 OCR、发票影像识别 |
| 唯一默认（应用层 + 部分唯一索引） | 多默认优先级策略 |
| 列表脱敏、财务角色看全量 | 字段级加密存储、KMS |
| 修改审计（前后差异，同事务） | 审计查询接口、归档（S2-AUDIT 范围） |
| OpenAPI、pytest、README | 前端页面、小程序、部署流水线 |

依赖 S2-CRM / S2-AUDIT / S2-IAM 的部分用接口桩先行，对接点见 §7。

## 2. 快速开始

```bash
# 1) PostgreSQL 16 测试库（库名必须含 test，测试会重建 public schema）
docker compose -f docker-compose.test.yml up -d --wait
export TEST_DATABASE_URL='postgresql+psycopg://clawhunt:clawhunt@127.0.0.1:55474/clawhunt_2874_test'
export DATABASE_URL="$TEST_DATABASE_URL"

# 2) 安装依赖
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3) 建表
.venv/bin/alembic upgrade head

# 4) 跑测试（94 个用例）
.venv/bin/python -m pytest

# 5) 起服务 + 真实 HTTP 冒烟（可选）
.venv/bin/uvicorn app.main:app --port 8874 &
.venv/bin/python scripts/smoke.py
```

## 3. 接口

身份来自受信头（网关内注入，见 §7）：`X-User-Id`、`X-Org-Id`、`X-Site-Id`、
`X-Role`（`finance` / `admin` / `ops` / `sales`）。缺失或非法 → 401。
所有读写按 `org_id` 隔离；企业不在本租户或不存在 → 404。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/finance/companies/{company_id}/invoice-profiles` | 列表（未删除），**银行账号一律只显示后 4 位** |
| POST | 同上 | 创建；首份资料自动成为默认 |
| GET | `…/invoice-profiles/{profile_id}` | 详情；**完整银行账号仅 `finance` 角色** |
| PATCH | 同上 | 部分更新；只触碰载荷中出现的字段 |
| DELETE | 同上 | 软删除（`deleted_at`），204 |

脱敏规则：`bank_account` 显示为 `****` + 后 4 位；不足 5 位时全部隐藏为
`****`；响应带 `bank_account_masked` 标记。列表接口对财务角色同样脱敏，
完整账号只能走详情接口（便于审计「谁看过全量账号」）。

错误约定：业务校验失败返回 422，`detail` 为
`[{"field", "code", "message"}]`；请求体形状错误走 FastAPI 默认 422。

## 4. 校验规则

- **纳税人识别号**：去空白、转大写后长度须为 15 / 18 / 20 位。
  - 18 位按 GB 32100-2015：字符集 `0-9A-Z` 去除 `I O Z S V`，
    加权因子 `Wi = 3^i mod 31`，校验位 `C18 = 31 − Σ(Ci×Wi) mod 31`（31 记 0）。
    校验位错误 → 422 `tax_id_check_digit`（验收标准 1）。
  - 15 位（老税务登记号）/ 20 位（临时登记）校验长度与大写字母数字形状，
    无国家校验位。
- **专票四项必填**：`default_invoice_type = special` 时注册地址、注册电话、
  开户行、银行账号缺一不可 → 422 `special_invoice_required`（验收标准 2）。
  POST 与 PATCH（含把普票改为专票、清空某一项）都按**合并后的完整状态**校验；
  数据库另有同名 CHECK 约束兜底。
- **抬头不一致**：抬头与 CRM 企业名不一致时允许保存，但必须填写
  `name_mismatch_reason` → 否则 422 `name_mismatch_reason_required`；
  改回一致时自动清空原因。
- 银行账号：去空格后须为 8–32 位数字；邮箱 / 电话做格式校验。
- `title` / `tax_id` / `default_invoice_type` 为必填，PATCH 显式置 null → 422。

## 5. 唯一默认

- 一家企业可有多份资料（如分支机构），**未删除的资料中至多 1 份默认**，
  由部分唯一索引 `uq_company_invoice_profiles_default`
  （`org_id, company_id WHERE is_default AND deleted_at IS NULL`）兜底。
- 首份资料自动成为默认（忽略载荷中的 `is_default=false`）。
- 创建 / PATCH 设 `is_default=true`：同事务降级现默认（行级锁防并发）。
- 不允许直接取消默认（422 `default_transfer_required`），默认只能通过
  「把另一份设为默认」转移。
- 删除默认资料时自动提升**最早创建**的剩余资料为默认。

## 6. 审计（验收标准 4）

每次成功修改在**同一事务**写审计，回滚的变更不会留下审计：

- 表：`finance_invoice_profile_change_log`（S2-AUDIT 本地桩，见 §7）；
- 每份被改动的资料各写 1 行：`action`（create / update / delete）、
  `old_value` / `new_value` 全量前后快照、`diff` 字段级
  `{field: {old, new}}`、`operator_id`、时间；
- 普通 PATCH 恰好 1 行；默认转移 / 删除默认会触碰两份资料，各写 1 行；
- 无实际变化的 PATCH（no-op）不写审计；
- 审计快照保留**全量**银行账号（财务追溯需要）；审计表的读取权限属于
  S2-AUDIT / 财务管理员范围，不经本模块接口暴露。

## 7. 依赖对接点（桩 → 生产）

| 依赖 | 桩实现 | 生产替换点（只改一处） |
|---|---|---|
| S2-CRM 企业对象 | `app/crm.py` 读 `fixtures/crm_companies.json`（可用 `CRM_COMPANIES_FILE` 指向其他文件） | `GET /internal/crm/companies/{id}` → `{id, org_id, name}` |
| S2-AUDIT 审计 | `app/audit.py: LocalChangeLogSink` 写本地表 | `POST /internal/audit/events`（载荷 = 现审计行形状） |
| S2-IAM 身份/角色 | `app/iam.py: get_principal` 解析受信头 | 网关 token introspection；**本服务不得直接暴露公网** |

`company_id` 不带跨模块外键（CRM 表属另一工单），存在性经 CRM 对接点校验。

## 8. 目录与证据

```
app/            FastAPI 应用（模型 / 校验器 / 接口 / 桩）
migrations/     Alembic（0001 建两张表 + 约束 + 部分唯一索引）
fixtures/       虚构 CRM 企业名册
tests/          94 个用例（校验单测 / 接口 / 默认不变量 / 审计 / 库约束 / OpenAPI）
scripts/smoke.py  真实 HTTP 冒烟（四条验收标准）
docs/openapi.json
evidence/       test-results.txt · migration-check.txt · runtime-smoke.txt · uvicorn.log
```

测试需要真实 PostgreSQL 16（`TEST_DATABASE_URL`，库名必须含 `test`，
fixture 会重建 `public` schema，切勿指向共享库）。