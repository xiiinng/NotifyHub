import { expect, test } from '@playwright/test'

test('登录页面能够正常加载', async ({ page }) => {
  await page.goto('/login')

  await expect(page.getByRole('heading', { name: 'NotifyHub' })).toBeVisible()
  await expect(page.getByLabel('邮箱')).toBeVisible()
  await expect(page.getByLabel('密码')).toBeVisible()
  await expect(page.getByRole('button', { name: '登录' })).toBeVisible()
  await expect(page.getByRole('link', { name: '立即注册' })).toBeVisible()
})
