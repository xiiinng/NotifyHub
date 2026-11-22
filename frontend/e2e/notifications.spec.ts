import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from '@playwright/test'

interface TestUser {
  username: string
  email: string
  password: string
}

interface TemplatePayload {
  name: string
  title: string
  content: string
}

interface NotificationPayload {
  title: string
  content: string
}

interface NotificationRecord {
  id: number
  template_id: number | null
  title: string
  content: string
  status: 'pending' | 'processing' | 'success' | 'failed'
  retry_count: number
  error_message: string | null
  created_at: string
  updated_at: string
}

interface NotificationPage {
  items: NotificationRecord[]
  total: number
  page: number
  page_size: number
  pages: number
}

function uniqueSuffix(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function makeUser(): TestUser {
  const suffix = uniqueSuffix()
  return {
    username: `e2e_${suffix}`,
    email: `e2e-${suffix}@example.com`,
    password: 'E2ePass123!',
  }
}

function makeTemplate(prefix = 'tpl'): TemplatePayload {
  const suffix = uniqueSuffix()
  return {
    name: `${prefix}-${suffix}`,
    title: `${prefix}-标题-${suffix}`,
    content: `${prefix}-内容-${suffix}`,
  }
}

function makeNotification(prefix = 'notice'): NotificationPayload {
  const suffix = uniqueSuffix()
  return {
    title: `${prefix}-标题-${suffix}`,
    content: `${prefix}-内容-${suffix}`,
  }
}

function authHeaders(token: string): { Authorization: string } {
  return { Authorization: `Bearer ${token}` }
}

async function registerUser(
  request: APIRequestContext,
  user: TestUser,
): Promise<void> {
  const response = await request.post('/api/v1/auth/register', { data: user })
  expect(response.status()).toBe(201)
}

async function loginViaApi(
  request: APIRequestContext,
  user: TestUser,
): Promise<string> {
  const response = await request.post('/api/v1/auth/login', {
    data: { email: user.email, password: user.password },
  })
  expect(response.status()).toBe(200)

  const body = (await response.json()) as { access_token: string }
  expect(body.access_token).toBeTruthy()
  return body.access_token
}

async function loginViaUi(page: Page, user: TestUser): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('邮箱', { exact: true }).fill(user.email)
  await page.getByLabel('密码', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/notifications$/)
}

async function createTemplateViaApi(
  request: APIRequestContext,
  token: string,
  template: TemplatePayload,
): Promise<{ id: number }> {
  const response = await request.post('/api/v1/templates', {
    headers: authHeaders(token),
    data: template,
  })
  expect(response.status()).toBe(201)
  return (await response.json()) as { id: number }
}

async function createNotificationViaApi(
  request: APIRequestContext,
  token: string,
  payload: NotificationPayload | { template_id: number },
): Promise<NotificationRecord> {
  const response = await request.post('/api/v1/notifications', {
    headers: authHeaders(token),
    data: payload,
  })
  expect(response.status()).toBe(201)
  return (await response.json()) as NotificationRecord
}

async function waitForNotificationStatus(
  request: APIRequestContext,
  token: string,
  notificationId: number,
  expectedStatus: NotificationRecord['status'],
): Promise<void> {
  let lastStatus = 'unknown'

  try {
    await expect
      .poll(
        async () => {
          const response = await request.get(
            `/api/v1/notifications/${notificationId}`,
            { headers: authHeaders(token) },
          )
          expect(response.status()).toBe(200)

          const body = (await response.json()) as NotificationRecord
          lastStatus = body.status
          return body.status
        },
        {
          timeout: 30_000,
          intervals: [250, 500, 1000, 2000],
          message: `等待通知 ${notificationId} 进入 ${expectedStatus}`,
        },
      )
      .toBe(expectedStatus)
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    throw new Error(
      `通知 ${notificationId} 未在超时时间内进入 ${expectedStatus}，最后状态=${lastStatus}；${detail}`,
    )
  }
}

function notificationIdFromUrl(page: Page): number {
  const match = new URL(page.url()).pathname.match(/^\/notifications\/(\d+)$/)
  expect(match).not.toBeNull()
  return Number(match?.[1])
}

test.describe('通知流程', () => {
  test('N-01 手动发送通知并查看详情', async ({ page, request }) => {
    const user = makeUser()
    const notification = makeNotification('manual')
    await registerUser(request, user)
    const token = await loginViaApi(request, user)

    await loginViaUi(page, user)

    await page.goto('/notifications')
    await expect(page.getByText('暂无通知，去')).toBeVisible()

    await page.goto('/send')
    await page.getByRole('button', { name: '手动填写', exact: true }).click()

    await page
      .getByRole('textbox', { name: '标题', exact: true })
      .fill(notification.title)
    await page
      .getByRole('textbox', { name: '内容', exact: true })
      .fill(notification.content)
    await page.getByRole('button', { name: '发送通知', exact: true }).click()

    await expect(page.locator('.alert.success')).toBeVisible()
    await expect(page.locator('.alert.success')).toContainText('已创建')

    await page.getByRole('link', { name: '查看详情' }).click()
    await expect(page).toHaveURL(/\/notifications\/\d+$/)

    const notificationId = notificationIdFromUrl(page)
    await expect(
      page.getByRole('heading', { name: '通知详情', exact: true }),
    ).toBeVisible()
    await expect(page.locator('.detail-grid strong')).toHaveText(
      notification.title,
    )
    await expect(page.locator('.detail-content p')).toHaveText(
      notification.content,
    )
    await expect(page.getByText('无（手动创建）')).toBeVisible()

    await waitForNotificationStatus(request, token, notificationId, 'success')
    await expect(page.locator('.detail-grid .badge')).toHaveText('成功')
    await expect(page.locator('.alert.error')).toHaveCount(0)
  })

  test('N-02 使用模板发送并验证内容快照', async ({ page, request }) => {
    const user = makeUser()
    const template = makeTemplate('send')
    await registerUser(request, user)
    const token = await loginViaApi(request, user)
    const createdTemplate = await createTemplateViaApi(request, token, template)

    await loginViaUi(page, user)
    await page.goto('/send')

    await expect(
      page.getByRole('combobox', { name: '选择模板', exact: true }),
    ).toBeVisible()
    await expect(page.locator('.preview')).toContainText(template.title)
    await expect(page.locator('.preview')).toContainText(template.content)
    await expect(
      page.getByRole('textbox', { name: '标题', exact: true }),
    ).toHaveCount(0)
    await expect(
      page.getByRole('textbox', { name: '内容', exact: true }),
    ).toHaveCount(0)

    await page.getByRole('button', { name: '发送通知', exact: true }).click()
    await expect(page.locator('.alert.success')).toBeVisible()
    await expect(page.locator('.alert.success')).toContainText('已创建')

    await page.getByRole('link', { name: '查看详情' }).click()
    await expect(page).toHaveURL(/\/notifications\/\d+$/)
    const notificationId = notificationIdFromUrl(page)

    await expect(page.locator('.detail-grid strong')).toHaveText(
      template.title,
    )
    await expect(page.locator('.detail-content p')).toHaveText(
      template.content,
    )
    await expect(
      page.getByText(`#${createdTemplate.id}`, { exact: true }),
    ).toBeVisible()

    const newTitle = `模板修改后标题-${uniqueSuffix()}`
    const newContent = `模板修改后内容-${uniqueSuffix()}`
    const updateResponse = await request.put(
      `/api/v1/templates/${createdTemplate.id}`,
      {
        headers: authHeaders(token),
        data: { title: newTitle, content: newContent },
      },
    )
    expect(updateResponse.status()).toBe(200)

    await page.reload()
    await expect(page.locator('.detail-grid strong')).toHaveText(
      template.title,
    )
    await expect(page.locator('.detail-content p')).toHaveText(
      template.content,
    )

    await waitForNotificationStatus(request, token, notificationId, 'success')
    await expect(page.locator('.detail-grid .badge')).toHaveText('成功')
    await expect(page.locator('.alert.error')).toHaveCount(0)
  })

  test('N-03 通知历史分页和状态筛选', async ({ page, request }) => {
    const user = makeUser()
    await registerUser(request, user)
    const token = await loginViaApi(request, user)

    const notifications: NotificationRecord[] = []
    for (let index = 0; index < 11; index += 1) {
      notifications.push(
        await createNotificationViaApi(request, token, makeNotification(`list-${index}`)),
      )
    }

    await Promise.all(
      notifications.map((item) =>
        waitForNotificationStatus(request, token, item.id, 'success'),
      ),
    )

    await loginViaUi(page, user)
    await page.goto('/notifications')

    await expect(
      page.getByRole('heading', { name: '通知历史', exact: true }),
    ).toBeVisible()
    await expect(
      page.getByText('第 1-10 条，共 11 条', { exact: true }),
    ).toBeVisible()
    await expect(page.locator('.table-wrap tbody tr')).toHaveCount(10)

    await page.getByRole('button', { name: '下一页', exact: true }).click()
    await expect(
      page.getByText('第 11-11 条，共 11 条', { exact: true }),
    ).toBeVisible()
    await expect(page.locator('.table-wrap tbody tr')).toHaveCount(1)
    await expect(page.getByText('2 / 2', { exact: true })).toBeVisible()

    await page.getByRole('combobox').selectOption({ label: '成功' })
    await expect(
      page.getByText('第 1-10 条，共 11 条', { exact: true }),
    ).toBeVisible()
    await expect(page.locator('.table-wrap tbody tr')).toHaveCount(10)
    await expect(page.locator('.alert.error')).toHaveCount(0)
  })

  test('N-04 通知详情越权访问和无效编号', async ({ page, request }) => {
    const userA = makeUser()
    const userB = makeUser()
    const notification = makeNotification('private')
    await registerUser(request, userA)
    await registerUser(request, userB)
    const tokenA = await loginViaApi(request, userA)
    const created = await createNotificationViaApi(request, tokenA, notification)

    await loginViaUi(page, userB)

    await page.goto(`/notifications/${created.id}`)
    await expect(page.locator('.alert.error')).toContainText('通知不存在')
    await expect(page.locator('.detail-card')).toHaveCount(0)
    await expect(
      page.getByText(notification.title, { exact: true }),
    ).toHaveCount(0)
    await expect(
      page.getByText(notification.content, { exact: true }),
    ).toHaveCount(0)
    await expect(page).toHaveURL(new RegExp(`/notifications/${created.id}$`))

    await page.goto('/notifications/not-a-number')
    await expect(page.locator('.alert.error')).toContainText('无效的通知编号')
    await expect(page.locator('.detail-card')).toHaveCount(0)
    await expect(page).toHaveURL(/\/notifications\/not-a-number$/)
  })

  test('N-05 通知用户隔离', async ({ request }) => {
    const userA = makeUser()
    const userB = makeUser()
    const notification = makeNotification('isolation')
    await registerUser(request, userA)
    await registerUser(request, userB)

    const tokenA = await loginViaApi(request, userA)
    const tokenB = await loginViaApi(request, userB)
    const created = await createNotificationViaApi(request, tokenA, notification)

    const listB = await request.get('/api/v1/notifications', {
      headers: authHeaders(tokenB),
    })
    expect(listB.status()).toBe(200)
    const listBBody = (await listB.json()) as NotificationPage
    expect(listBBody.items).toEqual([])
    expect(listBBody.total).toBe(0)

    const detailB = await request.get(
      `/api/v1/notifications/${created.id}`,
      { headers: authHeaders(tokenB) },
    )
    expect(detailB.status()).toBe(404)

    const detailA = await request.get(
      `/api/v1/notifications/${created.id}`,
      { headers: authHeaders(tokenA) },
    )
    expect(detailA.status()).toBe(200)
    const bodyA = (await detailA.json()) as NotificationRecord
    expect(bodyA.id).toBe(created.id)
    expect(bodyA.title).toBe(notification.title)
    expect(bodyA.content).toBe(notification.content)
  })
})
