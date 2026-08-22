import { expect, test } from '@playwright/test'

import { installMockApi } from './helpers/mockApi'

test('updates user role and active state with the backend contract', async ({ page }) => {
  const state = await installMockApi(page)

  await page.goto('/settings/users')

  const row = page
  .getByRole('cell', { name: 'operator', exact: true })
  .locator('..')

  await expect(row).toContainText('Enabled')

  await row.locator('select').selectOption('viewer')

  await expect.poll(() => state.updatedUsers.length).toBe(1)
  expect(state.updatedUsers[0]).toEqual({
    role: 'viewer',
    is_active: true,
  })

  await row.locator('input[type="checkbox"]').uncheck()

  await expect.poll(() => state.updatedUsers.length).toBe(2)
  expect(state.updatedUsers[1]).toEqual({
    role: 'viewer',
    is_active: false,
  })

  await expect(row).toContainText('Disabled')
})
