import { expect, test } from '@playwright/test'

import { installMockApi } from './helpers/mockApi'

test('redirects unauthenticated users to login and returns them after sign in', async ({
  page,
}) => {
  await installMockApi(page, { authenticated: false })

  await page.goto('/databases')

  await expect(page).toHaveURL(/\/login\?redirect=/)
  expect(new URL(page.url()).searchParams.get('redirect')).toBe('/databases')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()

  await page.getByLabel('Username').fill('admin')
  await page.getByLabel('Password').fill('secret')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/databases$/)
  await expect(page.locator('.database-card')).toHaveCount(2)
})

test('blocks direct access to permission-protected settings routes', async ({ page }) => {
  await installMockApi(page, { role: 'viewer' })

  await page.goto('/settings/connections')

  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('link', { name: 'Settings' })).toHaveCount(0)
})
