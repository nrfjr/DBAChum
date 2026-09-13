import { expect, test } from '@playwright/test'

import { installMockApi } from './helpers/mockApi'

test('creates and edits a provisioning profile from the current connections workspace', async ({ page }) => {
  const state = await installMockApi(page)

  await page.goto('/settings/connections?type=provisioning')
  await page.getByRole('button', { name: 'Add profile' }).click()

  const dialog = page.getByRole('dialog', { name: 'Add provisioning profile' })
  await dialog.getByLabel('Profile name').fill('ORMS User')
  await dialog.getByLabel('Description').fill('ORM application user')
  await dialog.getByLabel('Parent database connection').selectOption('conn-oracle')
  await dialog.getByRole('button', { name: 'Add table step' }).click()

  const step = dialog.locator('.provisioning-step-card').first()
  const stepName = step.getByLabel('Step name')
  await stepName.fill('Insert USER_MASTER')
  await step.getByLabel('Application provisioning connection').selectOption('conn-oracle')
  await step.getByLabel('Schema').selectOption('ORMS')
  await step.getByLabel('Table').selectOption('USER_MASTER')

  const idRow = step.locator('.provisioning-mapping-row[data-column="ID"]')
  await idRow.locator('select').first().selectOption('sequence')
  await idRow.getByLabel('Oracle sequence').selectOption('USER_MASTER_SEQ')

  const usernameRow = step.locator('.provisioning-mapping-row[data-column="USERNAME"]')
  await usernameRow.locator('select').selectOption('generated:username')
  await step.getByLabel('USERNAME', { exact: true }).check()

  const passwordRow = step.locator('.provisioning-mapping-row[data-column="PASSWORD"]')
  await passwordRow.locator('select').selectOption('generated:password')

  const statusRow = step.locator('.provisioning-mapping-row[data-column="STATUS"]')
  await statusRow.locator('select').selectOption('custom')
  await statusRow.getByPlaceholder('Custom value').fill('ACTIVE')

  await dialog.getByRole('button', { name: 'Create profile' }).click()
  await expect(dialog).toHaveCount(0)

  expect(state.createdProvisioningProfiles).toHaveLength(1)
  expect(state.createdProvisioningProfiles[0]).toMatchObject({
    name: 'ORMS User',
    schema_connection_id: 'conn-oracle',
    ldap_enabled: false,
  })

  await page.getByRole('button', { name: 'Actions for ORMS User' }).click()
  await page.getByRole('menuitem', { name: 'Edit' }).click()
  const editDialog = page.getByRole('dialog', { name: 'Edit provisioning profile' })
  await expect(editDialog.getByLabel('Step name')).toHaveValue('Insert USER_MASTER')
  await editDialog.getByLabel('Description').fill('Updated ORMS application user')
  await editDialog.getByRole('button', { name: 'Save profile' }).click()
  await expect(editDialog).toHaveCount(0)

  expect(state.updatedProvisioningProfiles).toHaveLength(1)
  expect(state.updatedProvisioningProfiles[0]).toMatchObject({
    name: 'ORMS User',
    description: 'Updated ORMS application user',
  })
})

test('loads, tests and edits the migrated LDAP profile from the connections workspace', async ({ page }) => {
  const state = await installMockApi(page)

  await page.goto('/settings/connections?type=ldap')

  await expect(page.getByText('Default LDAP')).toBeVisible()
  await expect(page.getByText('Migrated automatically from the previous global LDAP settings.')).toBeVisible()

  await page.getByRole('button', { name: 'Actions for Default LDAP' }).click()
  await page.getByRole('menuitem', { name: 'Test connection' }).click()
  await expect(page.getByText('LDAP connection test passed')).toBeVisible()
  expect(state.ldapProfileTests).toEqual(['global'])

  await page.getByRole('button', { name: 'Actions for Default LDAP' }).click()
  await page.getByRole('menuitem', { name: 'Edit' }).click()
  const dialog = page.getByRole('dialog', { name: 'Edit LDAP profile' })
  await dialog.getByLabel('Profile name').fill('Oracle Retail LDAP')
  await dialog.getByLabel('Host').fill('ldap.example.local')
  await dialog.getByRole('button', { name: 'Save LDAP profile' }).click()
  await expect(dialog).toHaveCount(0)

  expect(state.ldapProfileUpdates).toHaveLength(1)
  expect(state.ldapProfileUpdates[0]).toMatchObject({
    name: 'Oracle Retail LDAP',
    enabled: true,
    host: 'ldap.example.local',
  })
})
