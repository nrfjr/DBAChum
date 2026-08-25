import { expect, test } from '@playwright/test'

import { installMockApi } from './helpers/mockApi'

test('creates a provisioning profile from Oracle metadata mappings', async ({ page }) => {
  const state = await installMockApi(page)

  await page.goto('/settings/provisioning')
  await page.getByRole('button', { name: 'Add profile' }).click()

  const dialog = page.getByRole('dialog', { name: 'Add provisioning profile' })
  await dialog.getByLabel('Profile name').fill('ORMS User')
  await dialog.getByLabel('Description').fill('ORM application user')
  await dialog.getByLabel('Schema creation connection').selectOption('conn-oracle')
  await dialog.getByRole('button', { name: 'Add table step' }).click()

  const step = dialog.locator('.provisioning-step-card').first()
  const stepName = step.getByLabel('Step name')
  await stepName.fill('')
  await stepName.click()
  await page.keyboard.type('Insert USER_MASTER')
  await expect(step.getByLabel('Step name')).toHaveValue('Insert USER_MASTER')
  await step.getByLabel('Oracle connection used for this insert').selectOption('conn-oracle')
  await step.getByLabel('Schema').selectOption('ORMS')
  await step.getByLabel('Table').selectOption('USER_MASTER')

  const idRow = step.locator('.provisioning-mapping-row[data-column="ID"]')
  await idRow.locator('select').first().selectOption('sequence')
  await idRow.getByLabel('Oracle sequence').selectOption('USER_MASTER_SEQ')

  const usernameRow = step.locator('.provisioning-mapping-row[data-column="USERNAME"]')
  await usernameRow.locator('select').selectOption('generated:username')

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

test('keeps LDAP independent and saves its global settings', async ({ page }) => {
  const state = await installMockApi(page)

  await page.goto('/settings/ldap')

  await page.getByLabel('Enable LDAP provisioning').check()
  await page.getByLabel('Host').fill('ldap.example.local')
  await page.getByLabel('Base DN').fill('dc=example,dc=local')
  await page.getByLabel('Bind DN').fill('cn=dbachum,dc=example,dc=local')
  await page.getByLabel('Bind password').fill('secret123')
  await page.getByRole('button', { name: 'Save LDAP settings' }).click()

  await expect(page.locator('.connection-test-result.success')).toHaveText('LDAP settings saved.')
  expect(state.ldapUpdates).toHaveLength(1)
  expect(state.ldapUpdates[0]).toMatchObject({
    enabled: true,
    host: 'ldap.example.local',
    port: 636,
    use_ssl: true,
    base_dn: 'dc=example,dc=local',
    bind_dn: 'cn=dbachum,dc=example,dc=local',
    bind_password: 'secret123',
  })
})
