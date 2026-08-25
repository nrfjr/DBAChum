import { expect, test } from '@playwright/test'

import { installMockApi } from './helpers/mockApi'

test('provisioning profile is derived from the current database Create User flow', async ({ page }) => {
  const state = await installMockApi(page, { provisioningProfile: true })

  await page.goto('/databases/conn-oracle')
  await page.getByRole('button', { name: 'Users & Schemas' }).click()
  await page.getByRole('button', { name: 'Create user' }).click()

  const dialog = page.getByRole('dialog', { name: 'Create Oracle user' })
  await expect(dialog.getByLabel('Application provisioning')).toContainText('ORMS User')
  await dialog.getByLabel('Application provisioning').selectOption('profile-orms')

  await dialog.getByText('Generate from employee details').click()
  await dialog.getByLabel('First name').fill('José')
  await dialog.getByLabel('Middle name').fill('Peña')
  await dialog.getByLabel('Last name').fill('Niño')
  await dialog.getByLabel('ID', { exact: true }).fill('12-345')
  await dialog.getByRole('button', { name: 'Generate username' }).click()
  await expect(dialog.getByLabel('Username')).toHaveValue('JPNINO12345')

  await dialog.getByLabel('Initial password').fill('abc12345')
  await dialog.getByLabel('Reference user').fill('APP_USER')
  await dialog.getByLabel('Remarks').fill('RMS access request')
  await dialog.getByRole('button', { name: 'Review' }).click()

  await expect(dialog.getByText('Phase 4A preview only — no database, application-table or LDAP changes were made.')).toBeVisible()
  await expect(dialog.getByText('Existing → ALTER / reconcile')).toBeVisible()
  await expect(dialog.getByText('UPDATE', { exact: true })).toBeVisible()
  await expect(dialog.getByText(/Matched 1 row by USERNAME/)).toBeVisible()
  await expect(dialog.getByText('ORMS.USER_MASTER_SEQ.NEXTVAL')).toBeVisible()
  await expect(dialog.getByText('JPNINO12345.ldif')).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Provision JPNINO12345 (Phase 4B)' })).toBeDisabled()

  expect(state.provisioningPreviewRequests).toHaveLength(1)
  expect(state.provisioningPreviewRequests[0]).toMatchObject({
    username: 'JPNINO12345',
    employee_id: '12345',
    reference_user: 'APP_USER',
    remarks: 'RMS access request',
  })
})

test('standalone provisioning workspace is no longer exposed', async ({ page }) => {
  await installMockApi(page, { provisioningProfile: true })
  await page.goto('/')
  await expect(page.getByRole('link', { name: 'Provisioning' })).toHaveCount(0)
})
