import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

interface TestUser {
  username: string
  email: string
  password: string
}

function makeUser(): TestUser {
  const suffix = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
  return {
    username: `e2e_${suffix}`,
    email: `e2e-${suffix}@example.com`,
    password: 'E2ePass123!',
  }
}

async function createUserViaApi(request: APIRequestContext, user: TestUser): Promise<void> {
  const response = await request.post('/api/v1/auth/register', { data: user })
  expect(response.status()).toBe(201)
}

async function fillLoginForm(page: Page, user: TestUser): Promise<void> {
  await page.getByLabel('邮箱', { exact: true }).fill(user.email)
  await page.getByLabel('密码', { exact: true }).fill(user.password)
}

async function loginViaUi(page: Page, user: TestUser): Promise<void> {
  await page.goto('/login')
  await fillLoginForm(page, user)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/notifications$/)
}

async function expectLoggedInAs(page: Page, user: TestUser): Promise<void> {
  await expect(page).toHaveURL(/\/notifications$/)
  await expect(page.getByRole('heading', { name: '通知历史', exact: true })).toBeVisible()

  const token = await page.evaluate(() => localStorage.getItem('notifyhub_token'))
  expect(token).toBeTruthy()

  await expect(page.locator('.user-meta strong')).toHaveText(user.username)
  await expect(page.locator('.user-meta span')).toHaveText(user.email)
  await expect(page.getByRole('button', { name: '退出登录', exact: true })).toBeVisible()
}

test.describe('认证流程', () => {
  test('C-01 注册成功并自动登录', async ({ page }) => {
    const user = makeUser()

    await page.goto('/register')
    await expect(page.getByRole('heading', { name: '创建账号', exact: true })).toBeVisible()

    await page.getByLabel('用户名', { exact: true }).fill(user.username)
    await page.getByLabel('邮箱', { exact: true }).fill(user.email)
    await page.getByLabel('密码', { exact: true }).fill(user.password)
    await page.getByLabel('确认密码', { exact: true }).fill(user.password)
    await page.getByRole('button', { name: '注册并登录', exact: true }).click()

    await expectLoggedInAs(page, user)
  })

  test('C-02 登录成功', async ({ page, request }) => {
    const user = makeUser()
    await createUserViaApi(request, user)

    await loginViaUi(page, user)
    await expectLoggedInAs(page, user)
  })

  test('C-03 错误密码登录', async ({ page, request }) => {
    const user = makeUser()
    await createUserViaApi(request, user)

    await page.goto('/login')
    await page.getByLabel('邮箱', { exact: true }).fill(user.email)
    await page.getByLabel('密码', { exact: true }).fill('WrongPass123!')
    await page.getByRole('button', { name: '登录', exact: true }).click()

    await expect(page).toHaveURL(/\/login$/)
    await expect(page.locator('.alert.error')).toHaveText('邮箱或密码错误')
    expect(await page.evaluate(() => localStorage.getItem('notifyhub_token'))).toBeNull()
  })

  test('C-04 登出和刷新状态', async ({ page, request }) => {
    const user = makeUser()
    await createUserViaApi(request, user)
    await loginViaUi(page, user)

    await page.getByRole('button', { name: '退出登录', exact: true }).click()
    await expect(page).toHaveURL(/\/login$/)
    expect(await page.evaluate(() => localStorage.getItem('notifyhub_token'))).toBeNull()

    await page.reload()
    await expect(page).toHaveURL(/\/login$/)

    await page.goto('/notifications')
    await expect(page).toHaveURL(/\/login$/)
    await expect(page.getByRole('button', { name: '退出登录', exact: true })).toHaveCount(0)
  })

  test('C-05 未登录访问受保护页面并返回原页面', async ({ page, request }) => {
    const user = makeUser()
    await createUserViaApi(request, user)

    await page.goto('/notifications')
    await expect(page).toHaveURL(/\/login$/)

    await fillLoginForm(page, user)
    await page.getByRole('button', { name: '登录', exact: true }).click()

    await expectLoggedInAs(page, user)
  })

  test('C-06 已登录访问公开认证页面', async ({ page, request }) => {
    const user = makeUser()
    await createUserViaApi(request, user)
    await loginViaUi(page, user)

    await page.goto('/login')
    await expect(page).toHaveURL(/\/notifications$/)
    await expect(page.getByRole('heading', { name: '通知历史', exact: true })).toBeVisible()

    await page.goto('/register')
    await expect(page).toHaveURL(/\/notifications$/)
    await expect(page.getByRole('heading', { name: '通知历史', exact: true })).toBeVisible()
  })
})
