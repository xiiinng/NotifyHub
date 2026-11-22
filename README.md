# NotifyHub — 企业 IT 工单管理与异步通知平台

基于 **FastAPI + PostgreSQL + Redis + Celery + React + TypeScript** 的内部 IT 服务台：员工提交工单，IT 支持人员分配和处理工单，系统自动记录处理历史、计算 SLA，并通过现有 Celery 异步通知体系向相关人员发送站内通知。

## 技术栈

- 后端：Python 3.11、FastAPI、SQLAlchemy 2.x、Alembic、Pydantic v2
- 数据与队列：PostgreSQL 16、Redis 7、Celery 5、Celery Beat
- 认证与安全：JWT、Argon2、登录限流、RBAC
- 前端：React 19、TypeScript、Vite、React Router、Axios
- 部署：Nginx、Docker Compose
- 测试：Pytest、Playwright
- CI：GitHub Actions（backend / frontend / e2e）

## 核心功能

- 用户注册、登录、JWT 身份认证
- 角色权限：普通员工（employee）和 IT 支持人员（it_support）
- IT 工单：创建、列表、详情、编辑、删除
- 工单分类、优先级、状态流转
- IT 支持人员分配/重新分配工单
- 工单处理历史和独立处理备注
- SLA 自动计算、手工截止时间调整和超时标识
- 员工工单统计和 IT 支持全局统计
- 通知模板、手动通知、员工间定向通知
- 通知已读、全部已读、未读数量
- Celery 异步通知、失败重试、Beat 补偿
- 工单事件通知幂等和 SLA 定时提醒
- Docker Compose 开发环境和独立 E2E 环境
- Pytest 后端测试、Playwright E2E 测试和 GitHub Actions CI

## 角色权限

| 能力 | employee | it_support |
|---|---|---|
| 创建工单 | 是 | 是 |
| 查看自己的工单 | 是 | 是 |
| 查看全部工单 | 否 | 是 |
| 修改自己未关闭工单的基本信息 | 是 | 是 |
| 修改优先级/截止时间 | 否 | 是 |
| 分配工单 | 否 | 是 |
| 更新工单状态 | 否 | 是 |
| 添加处理备注 | 否 | 是 |
| 查看工单历史/备注 | 仅自己的 | 全部 |
| 查看个人统计 | 是 | 是 |
| 查看全局统计 | 否 | 是 |
| 向其他员工发送站内通知 | 是 | 是 |
| 向工单创建者发送关联通知 | 否 | 是 |
| 查看自己的通知 | 是 | 是 |
| 标记自己的通知已读 | 是 | 是 |

所有权限由后端强制校验。前端只根据角色显示入口，不能替代后端授权。

## 工单业务流程

```text
员工创建工单
  -> pending
  -> IT 支持人员查看/分配
  -> in_progress
  -> IT 支持人员添加处理备注
  -> resolved
  -> 员工收到状态通知
  -> closed
```

状态机：

```text
pending -> in_progress
pending -> resolved
in_progress -> resolved
resolved -> in_progress
resolved -> closed
```

`closed` 是终态，不允许重新打开。员工不能自行变更工单状态。

## SLA 规则

| 优先级 | 默认处理时限 |
|---|---|
| low | 72 小时 |
| medium | 24 小时 |
| high | 8 小时 |
| urgent | 2 小时 |

- 创建工单时自动按优先级计算 `due_at`；
- 所有时间统一使用 UTC；
- IT 支持人员可手工调整截止时间；
- 手工调整后，优先级变化不会静默覆盖人工截止时间；
- 工单详情返回是否超时和剩余时间；
- 已解决/已关闭工单不再产生临近到期提醒；
- Celery Beat 每 5 分钟检查一次临近到期和超时工单。

## 通知和异步处理

通知事件包括：

- 工单创建
- 工单分配/重新分配
- 工单状态变化
- 添加处理备注
- 工单即将到期
- 工单超时
- 员工向其他员工定向发送
- IT 支持人员向工单创建者发送关联通知

可靠性设计：

1. 业务数据和通知事件记录在同一数据库事务中写入；
2. 业务事务提交后才投递 Celery 任务；
3. Redis/Celery 暂时不可用时不会回滚工单；
4. 未投递通知保留 `pending`，由现有 Beat 补偿任务恢复；
5. `ticket_notification_events.event_key` 和 `notifications.dedupe_key` 提供数据库级幂等；
6. Worker 任务重试不会重复创建通知；
7. 临近到期和超时事件使用不同事件键，分别保证只生成一次。

通知状态：

```text
pending -> processing -> success
                     -> pending（重试）
                     -> failed（超过重试预算）
```

## 数据模型

- `users`：用户、邮箱、Argon2 密码哈希、角色
- `notification_templates`：用户通知模板
- `notifications`：收件人、发送者、标题/内容快照、状态、已读时间、幂等键
- `tickets`：工单编号、创建者、处理人、分类、优先级、状态、SLA 截止时间
- `ticket_history`：工单创建、分配、状态变化、优先级/截止时间调整等审计记录
- `ticket_comments`：IT 支持人员的处理备注
- `ticket_notification_events`：工单通知事件幂等记录

数据库迁移位于 `backend/migrations/versions/`，历史 migration 不修改。

## API 概览

认证：

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

工单：

- `POST /api/v1/tickets`
- `GET /api/v1/tickets`
- `GET /api/v1/tickets/{id}`
- `PATCH /api/v1/tickets/{id}`
- `DELETE /api/v1/tickets/{id}`
- `POST /api/v1/tickets/{id}/assign`
- `PATCH /api/v1/tickets/{id}/status`
- `GET /api/v1/tickets/{id}/history`
- `GET /api/v1/tickets/{id}/comments`
- `POST /api/v1/tickets/{id}/comments`
- `POST /api/v1/tickets/{id}/notify`
- `GET /api/v1/tickets/stats`
- `GET /api/v1/tickets/assignees`（仅 IT 支持）

通知：

- `POST /api/v1/notifications`
- `GET /api/v1/notifications`
- `GET /api/v1/notifications/{id}`
- `PATCH /api/v1/notifications/{id}/read`
- `POST /api/v1/notifications/read-all`
- `GET /api/v1/notifications/unread-count`
- `GET /api/v1/users/directory`
- 模板 CRUD：`/api/v1/templates`

## 目录结构

```text
NotifyHub/
├── backend/
│   ├── app/
│   │   ├── core/          配置、安全、异常、限流
│   │   ├── models/        用户、通知、模板、工单、历史、备注
│   │   ├── schemas/       Pydantic 请求/响应模型
│   │   ├── routers/       auth、users、tickets、notifications、templates
│   │   ├── services/      用户、工单、SLA、通知、投递
│   │   ├── tasks/         Celery Worker、补偿、SLA 定时任务
│   │   ├── cli.py         IT 支持账号初始化
│   │   └── main.py        FastAPI 入口
│   ├── migrations/        Alembic 迁移
│   ├── tests/             Pytest
│   └── requirements*.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── components/
│   │   ├── pages/         登录、工单、通知、模板、统计
│   │   └── types/
│   └── e2e/               Playwright E2E
├── docker-compose.yml
├── docker-compose.integration.yml
├── docker-compose.e2e.yml
└── .github/workflows/ci.yml
```

## 环境变量

根目录 `.env.example` 和 `backend/.env.example` 提供模板。复制后填写：

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

关键变量：

- `JWT_SECRET_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `POSTGRES_*`
- `REDIS_PASSWORD`
- `CORS_ORIGINS`
- Celery 重试/超时/SLA 相关配置

IT 支持账号 CLI 额外读取：

- `IT_SUPPORT_EMAIL`
- `IT_SUPPORT_USERNAME`
- `IT_SUPPORT_PASSWORD`

密码不会打印到日志中。

## 本地开发

### 1. 启动基础设施

```bash
docker compose up -d postgres redis
```

### 2. 后端

```bash
cd backend
python -m pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. Celery Worker

Linux/macOS：

```bash
cd backend
celery -A app.tasks.celery_app:celery_app worker --loglevel=INFO
```

Windows 本地建议：

```powershell
cd backend
celery -A app.tasks.celery_app:celery_app worker --loglevel=INFO --pool=solo
```

### 4. Celery Beat

```bash
cd backend
celery -A app.tasks.celery_app:celery_app beat --loglevel=INFO --schedule=/tmp/celerybeat-schedule
```

Beat 调度包括：

- 每 60 秒通知补偿
- 每 300 秒工单 SLA 检查

### 5. 前端

```bash
cd frontend
npm install
npm run dev
```

Vite 默认开发地址和代理配置见 `frontend/vite.config.ts`。

## Docker 启动

```bash
cp .env.example .env
# 编辑 .env，填写必填密码和 JWT 密钥
docker compose up -d --build
```

Compose 服务：

- PostgreSQL
- Redis
- Alembic migrate
- FastAPI backend
- Celery worker
- Celery beat
- Nginx + React frontend

不要使用开发 Compose 数据卷做 E2E 测试。

## 数据库迁移

```bash
cd backend
alembic upgrade head
```

查看当前版本：

```bash
cd backend
alembic current
```

迁移原则：

- 不修改已执行历史 migration；
- 新增 migration 可回滚；
- 现有用户默认角色为 `employee`；
- 不重置数据库、不删除现有数据。

## 初始化 IT 支持账号

不提供公开注册 IT 支持账号的 API。

交互式：

```bash
cd backend
python -m app.cli create-it-support
```

或使用环境变量：

```powershell
$env:IT_SUPPORT_EMAIL="support@example.com"
$env:IT_SUPPORT_USERNAME="support"
$env:IT_SUPPORT_PASSWORD="请使用强密码"
python -m app.cli create-it-support
```

行为：

- 邮箱不存在：创建 IT 支持账号；
- 邮箱已存在：只提升为 `it_support`，不重置密码；
- 幂等；
- 不批量升级普通用户；
- 不打印明文密码。

Docker 环境：

```bash
docker compose exec backend python -m app.cli create-it-support
```

E2E 环境由 `docker-compose.e2e.yml` 的一次性 `seed-it-support` 服务自动创建测试账号。

## 后端测试

```bash
cd backend
python -m pytest -q
```

测试使用独立测试数据库，名称必须以 `_test` 结尾；不会使用开发数据库。

## 前端构建和检查

```bash
cd frontend
npm run lint
npm run build
```

## Playwright E2E

E2E 使用独立 Compose 项目 `notifyhub-e2e` 和独立数据库。

```bash
docker compose -f docker-compose.e2e.yml up -d --build
cd frontend
npx playwright install --with-deps chromium
npm run test:e2e
```

E2E 地址：

```text
http://127.0.0.1:13001
```

可通过 `E2E_BASE_URL` 覆盖。

清理仅针对 E2E 项目：

```bash
docker compose -f docker-compose.e2e.yml down -v --remove-orphans
```

注意：不要对开发 Compose 使用 `down -v`。

## GitHub Actions CI

工作流：`.github/workflows/ci.yml`

三个 Job：

1. `backend`
   - Python 3.11
   - PostgreSQL 16 Service
   - 运行全部 Pytest
2. `frontend`
   - Node.js 22
   - `npm install`
   - `npm run lint`
   - `npm run build`
3. `e2e`
   - 依赖 backend/frontend
   - 安装 Chromium
   - 启动隔离 E2E Compose
   - 等待 migrate/backend/worker/frontend healthy
   - 运行全部 Playwright 测试
   - 失败时上传 HTML 报告、trace、截图、视频和 Docker 日志
   - 最后清理 E2E 项目

## 安全说明

- 密码使用 Argon2 哈希；
- JWT 只保存用户 ID，角色每次从数据库读取；
- 注册接口不能指定角色；
- 工单、通知、模板查询均按当前 JWT 用户隔离；
- IT 支持权限由后端依赖统一校验；
- 工单通知使用数据库唯一约束幂等；
- 日志不输出密码或 JWT；
- E2E 测试账号和凭据仅用于独立测试环境。

## 已知限制

- 系统定位为站内通知，暂未接入邮件、短信或 WebSocket；
- 未实现自动分配、智能负载均衡、团队/部门组织架构；
- 工单删除仅允许删除未分配且待处理的工单，并采用软删除保留历史、备注和通知事件；
- 处理备注不支持编辑或删除，以保留审计记录；
- SLA 不计算工作日、节假日和办公时间；
- 通知已读为手动操作，不自动标记；
- 前端未引入图表库，统计以卡片和表格展示；
- IT 支持账号只能通过 CLI 创建/提升，不提供公开注册。
