import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from '@playwright/test'

interface TestUser {
  id: number
  username: string
  email: string
  password: string
}

interface TicketRecord {
  id: number
  ticket_no: string
  title: string
  description: string
  status: string
  priority: string
  assignee: { id: number; username: string } | null
}

const SUPPORT_EMAIL = 'support-e2e@example.com'
const SUPPORT_PASSWORD = 'e2e-support-only-password1'

function uniqueSuffix(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function makeUser(usernamePrefix = 'e2e'): TestUser {
  const suffix = uniqueSuffix()
  return {
    id: 0,
    username: `${usernamePrefix}_${suffix}`,
    email: `e2e-${suffix}@example.com`,
    password: 'E2ePass123!',
  }
}

function authHeaders(token: string): { Authorization: string } {
  return { Authorization: `Bearer ${token}` }
}

async function registerUser(
  request: APIRequestContext,
  user: TestUser,
): Promise<TestUser> {
  const response = await request.post('/api/v1/auth/register', {
    data: {
      username: user.username,
      email: user.email,
      password: user.password,
    },
  })
  expect(response.status()).toBe(201)
  const body = (await response.json()) as { id: number }
  return { ...user, id: body.id }
}

async function loginViaApi(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<string> {
  const response = await request.post('/api/v1/auth/login', {
    data: { email, password },
  })
  expect(response.status()).toBe(200)
  return ((await response.json()) as { access_token: string }).access_token
}

async function loginViaUi(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('邮箱', { exact: true }).fill(email)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/notifications$/)
}

async function createTicketViaApi(
  request: APIRequestContext,
  token: string,
  title: string,
  description = 'E2E 工单描述',
): Promise<TicketRecord> {
  const response = await request.post('/api/v1/tickets', {
    headers: authHeaders(token),
    data: {
      title,
      description,
      category: 'hardware',
      priority: 'medium',
    },
  })
  expect(response.status()).toBe(201)
  return (await response.json()) as TicketRecord
}

async function getTicketViaApi(
  request: APIRequestContext,
  token: string,
  ticketId: number,
): Promise<TicketRecord> {
  const response = await request.get(`/api/v1/tickets/${ticketId}`, {
    headers: authHeaders(token),
  })
  expect(response.status()).toBe(200)
  return (await response.json()) as TicketRecord
}

async function expectTicketRow(page: Page, title: string) {
  const row = page.getByRole('row').filter({ hasText: title }).first()
  await expect(row).toBeVisible()
  return row
}

async function getFirstAssigneeId(
  request: APIRequestContext,
  token: string,
): Promise<number> {
  const response = await request.get('/api/v1/tickets/assignees', {
    headers: authHeaders(token),
  })
  expect(response.status()).toBe(200)
  const assignees = (await response.json()) as Array<{ id: number }>
  expect(assignees.length).toBeGreaterThan(0)
  return assignees[0].id
}

test.describe('IT 工单流程', () => {
  test('T-01 普通员工创建工单并查看详情', async ({ page, request }) => {
    const user = await registerUser(request, makeUser())
    const title = `电脑故障-${uniqueSuffix()}`

    await loginViaUi(page, user.email, user.password)
    await page.goto('/tickets/new')
    await expect(page.getByRole('heading', { name: '新建工单' })).toBeVisible()

    await page.getByLabel('工单标题', { exact: true }).fill(title)
    await page
      .getByLabel('问题描述', { exact: true })
      .fill('电脑在启动时持续黑屏')
    await page.getByRole('combobox', { name: '分类', exact: true }).selectOption('hardware')
    await page.getByRole('combobox', { name: '优先级', exact: true }).selectOption('high')
    await page.getByRole('button', { name: '创建工单', exact: true }).click()

    await expect(page).toHaveURL(/\/tickets\/\d+$/)
    await expect(page.getByRole('heading', { name: '工单详情' })).toBeVisible()
    await expect(page.locator('.detail-grid strong')).toContainText(title)
    await expect(page.locator('.detail-content p')).toContainText('黑屏')
    await expect(page.locator('.alert.error')).toHaveCount(0)
  })

  test('T-02 员工只能看到自己的工单', async ({ page, request }) => {
    const userA = await registerUser(request, makeUser())
    const userB = await registerUser(request, makeUser())
    const titleA = `A-工单-${uniqueSuffix()}`
    const titleB = `B-工单-${uniqueSuffix()}`
    const ticketA = await createTicketViaApi(
      request,
      await loginViaApi(request, userA.email, userA.password),
      titleA,
    )
    const tokenB = await loginViaApi(request, userB.email, userB.password)
    await createTicketViaApi(request, tokenB, titleB)

    await loginViaUi(page, userA.email, userA.password)
    await page.goto('/tickets')
    await expect(page.getByRole('heading', { name: '我的工单' })).toBeVisible()
    await expectTicketRow(page, titleA)
    await expect(page.getByText(titleB, { exact: true })).toHaveCount(0)

    const response = await request.get(`/api/v1/tickets/${ticketA.id}`, {
      headers: authHeaders(tokenB),
    })
    expect(response.status()).toBe(404)
  })

  test('T-03 员工不能访问 IT 支持页面', async ({ page, request }) => {
    const user = await registerUser(request, makeUser())
    const token = await loginViaApi(request, user.email, user.password)
    const created = await createTicketViaApi(
      request,
      token,
      `越权检查-${uniqueSuffix()}`,
    )

    await loginViaUi(page, user.email, user.password)
    await page.goto('/support/tickets')
    await expect(page.locator('.alert.error')).toContainText(
      '无权限访问 IT 支持页面',
    )

    const response = await request.post(
      `/api/v1/tickets/${created.id}/assign`,
      {
        headers: authHeaders(token),
        data: { assignee_id: 1 },
      },
    )
    expect(response.status()).toBe(403)
  })

  test('T-04 IT 支持人员可以查看全部工单', async ({ page, request }) => {
    const user = await registerUser(request, makeUser())
    const token = await loginViaApi(request, user.email, user.password)
    const title = `支持全量-${uniqueSuffix()}`
    await createTicketViaApi(request, token, title)
    const supportToken = await loginViaApi(
      request,
      SUPPORT_EMAIL,
      SUPPORT_PASSWORD,
    )
    expect(supportToken).toBeTruthy()

    await loginViaUi(page, SUPPORT_EMAIL, SUPPORT_PASSWORD)
    await page.goto('/support/tickets')
    await expect(page.getByRole('heading', { name: '支持工作台' })).toBeVisible()
    await expectTicketRow(page, title)
  })

  test('T-05 IT 支持人员分配工单', async ({ page, request }) => {
    const user = await registerUser(request, makeUser())
    const token = await loginViaApi(request, user.email, user.password)
    const created = await createTicketViaApi(
      request,
      token,
      `待分配-${uniqueSuffix()}`,
    )

    await loginViaUi(page, SUPPORT_EMAIL, SUPPORT_PASSWORD)
    await page.goto(`/tickets/${created.id}`)
    await page.getByRole('combobox', { name: '处理人', exact: true }).selectOption({ index: 1 })
    await page.getByRole('button', { name: '分配工单', exact: true }).click()

    await expect(page.locator('.alert.success')).toContainText('工单已分配')
    await expect(page.locator('.detail-grid')).toContainText('support-e2e')
  })

  test('T-06 IT 支持人员更新工单状态', async ({ page, request }) => {
    const user = await registerUser(request, makeUser())
    const token = await loginViaApi(request, user.email, user.password)
    const created = await createTicketViaApi(
      request,
      token,
      `状态处理-${uniqueSuffix()}`,
    )

    await loginViaUi(page, SUPPORT_EMAIL, SUPPORT_PASSWORD)
    await page.goto(`/tickets/${created.id}`)
    await page.getByRole('combobox', { name: '更新状态', exact: true }).selectOption('in_progress')
    await page.getByRole('button', { name: '更新状态', exact: true }).click()

    await expect(page.locator('.alert.success')).toContainText('工单状态已更新')
    await expect(page.locator('.ticket-status-in_progress')).toBeVisible()
    const supportToken = await loginViaApi(
      request,
      SUPPORT_EMAIL,
      SUPPORT_PASSWORD,
    )
    expect(
      (await getTicketViaApi(request, supportToken, created.id)).status,
    ).toBe('in_progress')
  })

  test('T-07 IT 支持人员添加处理备注', async ({ page, request }) => {
    const user = await registerUser(request, makeUser())
    const token = await loginViaApi(request, user.email, user.password)
    const created = await createTicketViaApi(
      request,
      token,
      `备注处理-${uniqueSuffix()}`,
    )

    await loginViaUi(page, SUPPORT_EMAIL, SUPPORT_PASSWORD)
    await page.goto(`/tickets/${created.id}`)
    await page
      .getByLabel('处理备注', { exact: true })
      .fill('已联系用户，安排上门检查')
    await page.getByRole('button', { name: '添加备注', exact: true }).click()

    await expect(page.locator('.alert.success')).toContainText('处理备注已添加')
    await expect(page.locator('.comment-list')).toContainText(
      '已联系用户，安排上门检查',
    )
  })

  test('T-08 员工可以查看工单处理历史和备注', async ({ page, request }) => {
    const user = await registerUser(request, makeUser())
    const token = await loginViaApi(request, user.email, user.password)
    const title = `可见记录-${uniqueSuffix()}`
    const created = await createTicketViaApi(request, token, title)
    const supportToken = await loginViaApi(
      request,
      SUPPORT_EMAIL,
      SUPPORT_PASSWORD,
    )
    const assigneeId = await getFirstAssigneeId(request, supportToken)
    await request.post(`/api/v1/tickets/${created.id}/assign`, {
      headers: authHeaders(supportToken),
      data: { assignee_id: assigneeId },
    })
    await request.patch(`/api/v1/tickets/${created.id}/status`, {
      headers: authHeaders(supportToken),
      data: { status: 'in_progress' },
    })
    await request.post(`/api/v1/tickets/${created.id}/comments`, {
      headers: authHeaders(supportToken),
      data: { content: '员工可见的处理备注' },
    })

    await loginViaUi(page, user.email, user.password)
    await page.goto(`/tickets/${created.id}`)
    await expect(page.locator('.timeline')).toContainText('状态变更')
    await expect(page.locator('.comment-list')).toContainText(
      '员工可见的处理备注',
    )
  })

  test('T-09 员工收到工单状态通知', async ({ page, request }) => {
    const user = await registerUser(request, makeUser())
    const token = await loginViaApi(request, user.email, user.password)
    const title = `通知状态-${uniqueSuffix()}`
    const created = await createTicketViaApi(request, token, title)
    const supportToken = await loginViaApi(
      request,
      SUPPORT_EMAIL,
      SUPPORT_PASSWORD,
    )
    await request.patch(`/api/v1/tickets/${created.id}/status`, {
      headers: authHeaders(supportToken),
      data: { status: 'in_progress' },
    })

    await loginViaUi(page, user.email, user.password)
    await page.goto('/notifications')
    const row = page.getByRole('row').filter({ hasText: title }).first()
    await expect(row).toBeVisible()
    await expect(row).toContainText('工单状态已更新')
  })

  test('T-10 员工向另一位员工发送站内通知', async ({
    page,
    request,
  }) => {
    const sender = await registerUser(request, makeUser())
    const recipient = await registerUser(request, makeUser('000'))
    const title = `同事通知-${uniqueSuffix()}`

    await loginViaUi(page, sender.email, sender.password)
    await page.goto('/send')
    await page
      .getByRole('textbox', { name: '搜索接收人', exact: true })
      .fill(recipient.email)
    await page.getByRole('combobox', { name: '接收人', exact: true }).selectOption(
      `${recipient.username}（${recipient.email}）`,
    )
    await page.getByRole('button', { name: '手动填写', exact: true }).click()
    await page.getByRole('textbox', { name: '标题', exact: true }).fill(title)
    await page
      .getByRole('textbox', { name: '内容', exact: true })
      .fill('这是一条定向同事通知')
    await page.getByRole('button', { name: '发送通知', exact: true }).click()
    await expect(page.locator('.alert.success')).toContainText('已创建')

    await page.getByRole('button', { name: '退出登录', exact: true }).click()
    await expect(page).toHaveURL(/\/login$/)
    await loginViaUi(page, recipient.email, recipient.password)
    await page.goto('/notifications')
    const row = page.getByRole('row').filter({ hasText: title }).first()
    await expect(row).toBeVisible()
  })

  test('T-11 接收人标记通知已读', async ({ page, request }) => {
    const sender = await registerUser(request, makeUser())
    const recipient = await registerUser(request, makeUser())
    const title = `未读通知-${uniqueSuffix()}`
    const token = await loginViaApi(request, sender.email, sender.password)
    const response = await request.post('/api/v1/notifications', {
      headers: authHeaders(token),
      data: {
        recipient_user_id: recipient.id,
        title,
        content: '需要标记为已读',
      },
    })
    expect(response.status()).toBe(201)

    await loginViaUi(page, recipient.email, recipient.password)
    await page.goto('/notifications')
    const row = page.getByRole('row').filter({ hasText: title }).first()
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: '标为已读', exact: true }).click()
    await expect(row.getByRole('button', { name: '标为已读' })).toHaveCount(0)
  })

  test('T-12 员工查看自己的工单统计', async ({ page, request }) => {
    const user = await registerUser(request, makeUser())
    const token = await loginViaApi(request, user.email, user.password)
    await createTicketViaApi(request, token, `统计工单-${uniqueSuffix()}`)

    await loginViaUi(page, user.email, user.password)
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name: '工单统计' })).toBeVisible()
    await expect(page.getByText('工单总数')).toBeVisible()
    await expect(page.getByText('我的工单概览')).toBeVisible()
  })

  test('T-13 IT 支持人员查看全局统计', async ({ page }) => {
    await loginViaUi(page, SUPPORT_EMAIL, SUPPORT_PASSWORD)
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name: '工单统计' })).toBeVisible()
    await expect(page.getByText('全局 IT 服务台运营数据')).toBeVisible()
    await expect(page.getByText('未分配')).toBeVisible()
  })

  test('T-14 工单详情展示超时 SLA', async ({ page, request }) => {
    const user = await registerUser(request, makeUser())
    const token = await loginViaApi(request, user.email, user.password)
    const created = await createTicketViaApi(
      request,
      token,
      `超时标识-${uniqueSuffix()}`,
    )
    const supportToken = await loginViaApi(
      request,
      SUPPORT_EMAIL,
      SUPPORT_PASSWORD,
    )
    const past = new Date(Date.now() - 60 * 60 * 1000).toISOString()
    const updated = await request.patch(`/api/v1/tickets/${created.id}`, {
      headers: authHeaders(supportToken),
      data: { due_at: past },
    })
    expect(updated.status()).toBe(200)

    await loginViaUi(page, user.email, user.password)
    await page.goto(`/tickets/${created.id}`)
    await expect(page.locator('.detail-grid')).toContainText('已超时')
  })
})
