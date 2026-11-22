import {
  expect,
  test,
  type APIRequestContext,
  type Locator,
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

interface TemplateRecord extends TemplatePayload {
  id: number
  created_at: string
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
    title: `标题-${suffix}`,
    content: `模板内容-${suffix}`,
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

async function createTemplateViaApi(
  request: APIRequestContext,
  token: string,
  template: TemplatePayload,
): Promise<TemplateRecord> {
  const response = await request.post('/api/v1/templates', {
    headers: authHeaders(token),
    data: template,
  })
  expect(response.status()).toBe(201)
  return (await response.json()) as TemplateRecord
}

async function loginViaUi(page: Page, user: TestUser): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('邮箱', { exact: true }).fill(user.email)
  await page.getByLabel('密码', { exact: true }).fill(user.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/notifications$/)
}

async function openTemplates(page: Page, user: TestUser): Promise<void> {
  await loginViaUi(page, user)
  await page.goto('/templates')
  await expect(
    page.getByRole('heading', { name: '通知模板', exact: true }),
  ).toBeVisible()
}

function templateRow(page: Page, name: string): Locator {
  return page.getByRole('row').filter({
    has: page.getByRole('button', { name, exact: true }),
  })
}

test.describe('模板管理', () => {
  test('D-01 新建模板、列表展示和展开详情', async ({ page, request }) => {
    const user = makeUser()
    const template = makeTemplate()
    await registerUser(request, user)

    await loginViaUi(page, user)
    await page.goto('/templates')

    await expect(
      page.getByRole('heading', { name: '通知模板', exact: true }),
    ).toBeVisible()
    await expect(
      page.getByText('还没有模板，点击右上角新建一个吧。', { exact: true }),
    ).toBeVisible()

    await page.getByRole('button', { name: '新建模板', exact: true }).click()
    await expect(
      page.getByRole('heading', { name: '新建模板', exact: true }),
    ).toBeVisible()

    await page.getByRole('textbox', { name: '模板名称', exact: true }).fill(template.name)
    await page.getByRole('textbox', { name: '通知标题', exact: true }).fill(template.title)
    await page.getByRole('textbox', { name: '通知内容', exact: true }).fill(template.content)
    await page.getByRole('button', { name: '保存', exact: true }).click()

    await expect(
      page.getByRole('heading', { name: '新建模板', exact: true }),
    ).toHaveCount(0)

    const row = templateRow(page, template.name)
    await expect(row).toBeVisible()
    await expect(
      row.getByRole('button', { name: template.name, exact: true }),
    ).toBeVisible()
    await expect(row).toContainText(template.title)

    await row
      .getByRole('button', { name: template.name, exact: true })
      .click()

    await expect(page.locator('.detail-panel')).toBeVisible()
    await expect(page.locator('.detail-panel')).toContainText(template.content)
    await expect(page.locator('.alert.error')).toHaveCount(0)
  })

  test('D-02 编辑模板', async ({ page, request }) => {
    const user = makeUser()
    const template = makeTemplate('edit')
    await registerUser(request, user)
    const token = await loginViaApi(request, user)
    await createTemplateViaApi(request, token, template)

    await openTemplates(page, user)

    let row = templateRow(page, template.name)
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: '编辑', exact: true }).click()

    await expect(
      page.getByRole('heading', { name: '编辑模板', exact: true }),
    ).toBeVisible()
    await expect(page.getByRole('textbox', { name: '模板名称', exact: true })).toHaveValue(
      template.name,
    )
    await expect(page.getByRole('textbox', { name: '通知标题', exact: true })).toHaveValue(
      template.title,
    )
    await expect(page.getByRole('textbox', { name: '通知内容', exact: true })).toHaveValue(
      template.content,
    )

    const newTitle = `新标题-${uniqueSuffix()}`
    const newContent = `新内容-${uniqueSuffix()}`
    await page.getByRole('textbox', { name: '通知标题', exact: true }).fill(newTitle)
    await page.getByRole('textbox', { name: '通知内容', exact: true }).fill(newContent)
    await page.getByRole('button', { name: '保存', exact: true }).click()

    await expect(
      page.getByRole('heading', { name: '编辑模板', exact: true }),
    ).toHaveCount(0)

    row = templateRow(page, template.name)
    await expect(row).toBeVisible()
    await expect(row).toContainText(newTitle)
    await expect(row).toContainText(newContent)
    await expect(page.locator('.alert.error')).toHaveCount(0)
  })

  test('D-03 删除模板（取消和确认）', async ({ page, request }) => {
    const user = makeUser()
    const template = makeTemplate('delete')
    await registerUser(request, user)
    const token = await loginViaApi(request, user)
    await createTemplateViaApi(request, token, template)

    await openTemplates(page, user)

    const row = templateRow(page, template.name)
    await expect(row).toBeVisible()

    const confirmMessage = `确定删除模板「${template.name}」吗？`
    let cancelMessage = ''
    page.once('dialog', async (dialog) => {
      cancelMessage = dialog.message()
      await dialog.dismiss()
    })
    await row.getByRole('button', { name: '删除', exact: true }).click()
    await expect.poll(() => cancelMessage).toContain(confirmMessage)
    await expect(row).toBeVisible()

    let acceptMessage = ''
    page.once('dialog', async (dialog) => {
      acceptMessage = dialog.message()
      await dialog.accept()
    })
    await row.getByRole('button', { name: '删除', exact: true }).click()
    await expect.poll(() => acceptMessage).toContain(confirmMessage)

    await expect(row).toHaveCount(0)
    await expect(
      page.getByText('还没有模板，点击右上角新建一个吧。', { exact: true }),
    ).toBeVisible()
    await expect(page.locator('.alert.error')).toHaveCount(0)
  })

  test('D-04 模板用户隔离', async ({ request }) => {
    const userA = makeUser()
    const userB = makeUser()
    const template = makeTemplate('isolated')

    await registerUser(request, userA)
    await registerUser(request, userB)
    const tokenA = await loginViaApi(request, userA)
    const tokenB = await loginViaApi(request, userB)

    const created = await createTemplateViaApi(request, tokenA, template)
    expect(created.id).toBeGreaterThan(0)

    const listB = await request.get('/api/v1/templates', {
      headers: authHeaders(tokenB),
    })
    expect(listB.status()).toBe(200)
    expect(await listB.json()).toEqual([])

    const detailB = await request.get(`/api/v1/templates/${created.id}`, {
      headers: authHeaders(tokenB),
    })
    expect(detailB.status()).toBe(404)

    const updateB = await request.put(`/api/v1/templates/${created.id}`, {
      headers: authHeaders(tokenB),
      data: { title: '越权修改' },
    })
    expect(updateB.status()).toBe(404)

    const deleteB = await request.delete(`/api/v1/templates/${created.id}`, {
      headers: authHeaders(tokenB),
    })
    expect(deleteB.status()).toBe(404)

    const detailA = await request.get(`/api/v1/templates/${created.id}`, {
      headers: authHeaders(tokenA),
    })
    expect(detailA.status()).toBe(200)

    const bodyA = (await detailA.json()) as TemplateRecord
    expect(bodyA.name).toBe(template.name)
    expect(bodyA.title).toBe(template.title)
    expect(bodyA.content).toBe(template.content)
  })
})
