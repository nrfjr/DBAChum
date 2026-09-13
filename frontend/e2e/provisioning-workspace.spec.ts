import { expect, test } from '@playwright/test'

import { installMockApi } from './helpers/mockApi'

test('provisioning remains attached to the database Create User flow', async ({ page }) => {
  await installMockApi(page, { provisioningProfile: true })

  await page.goto('/databases/conn-oracle')
  await page.getByRole('button', { name: 'Users / Access', exact: true }).click()
  await page.getByRole('button', { name: /^Create/ }).click()
  await page.getByRole('menuitem', { name: 'Create user' }).click()

  const dialog = page.getByRole('dialog', { name: 'Create Oracle user' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('1 · Identity')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Provisioning' })).toHaveCount(0)
})

test('standalone provisioning workspace is no longer exposed', async ({ page }) => {
  await installMockApi(page, { provisioningProfile: true })
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Provisioning' })).toHaveCount(0)
})
