import { expect, test } from '@playwright/test'

import { installMockApi } from './helpers/mockApi'

test('creates a provisioning profile from Oracle metadata mappings', async ({ page }) => {
  const state = await installMockApi(page)

  await page.goto('/settings/provisioning')
  await page.getByRole('button', { name: 'Add profile' }).click()

  const dialog = page.getByRole('dialog', { name: 'Add provisioning profile' })
  await dialog.getByLabel('Profile name').fill('ORMS User')
  await dialog.getByLabel('Description').fill('ORM application user')
  await dialog.getByLabel('Parent database connection (monitored)').selectOption('conn-oracle')
  await dialog.getByRole('button', { name: 'Add table step' }).click()

  const step = dialog.locator('.provisioning-step-card').first()
  const stepName = step.getByLabel('Step name')
  await stepName.fill('')
  await stepName.click()
  await page.keyboard.type('Insert USER_MASTER')
  await expect(step.getByLabel('Step name')).toHaveValue('Insert USER_MASTER')
  await step.getByLabel('Application provisioning connection for this step').selectOption('conn-oracle')
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
    table_steps: [
      {
        name: 'Insert USER_MASTER',
        connection_id: 'conn-oracle',
        owner: 'ORMS',
        table_name: 'USER_MASTER',
        mappings: [
          { column_name: 'ID', value_kind: 'sequence', value_key: 'USER_MASTER_SEQ' },
          { column_name: 'USERNAME', value_kind: 'generated', value_key: 'username' },
          { column_name: 'PASSWORD', value_kind: 'generated', value_key: 'password' },
          { column_name: 'STATUS', value_kind: 'custom', custom_value: 'ACTIVE' },
        ],
        match_columns: ['USERNAME'],
      },
    ],
  })

  await page.getByRole('button', { name: 'Edit' }).click()
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

test('migrates the existing LDAP entry into an editable/testable profile', async ({ page }) => {
  const state = await installMockApi(page)

  await page.goto('/settings/ldap')

  await expect(page.getByText('Default LDAP')).toBeVisible()
  await expect(page.getByText(/Migrated from your previous global LDAP settings/)).toBeVisible()

  await page.getByRole('button', { name: 'Test' }).click()
  await expect(page.locator('.connection-test-result.success')).toContainText('Base DN lookup succeeded')
  expect(state.ldapProfileTests).toEqual(['global'])

  await page.getByRole('button', { name: 'Edit' }).click()
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
