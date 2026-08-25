import { expect, test } from '@playwright/test'

import { installMockApi } from './helpers/mockApi'

test('tests an existing database connection', async ({ page }) => {
  await installMockApi(page)

  await page.goto('/settings/connections')

  const connection = page.locator('.connection-item').filter({
    hasText: 'ERP Production',
  })

  await connection.getByRole('button', { name: 'Test' }).click()

  await expect(connection).toContainText('Connection successful.')
  await expect(connection).toContainText('ERPPRD')
  await expect(connection).toContainText('Oracle Database 19c')
})

test('adds a SQL Server connection with the expected payload', async ({ page }) => {
  const state = await installMockApi(page)

  await page.goto('/settings/connections')
  await page.getByRole('button', { name: 'Add connection' }).click()

  const dialog = page.getByRole('dialog', { name: 'Add database connection' })

  await dialog.getByLabel('Connection name').fill('Warehouse SQL')
  await dialog.getByLabel('Database engine').selectOption('sqlserver')
  await expect(dialog.getByLabel('Port')).toHaveValue('1433')
  await dialog.getByLabel('Host').fill('warehouse-sql.example.local')
  await dialog.getByPlaceholder('Database name').fill('Warehouse')
  await dialog.getByLabel('Username').fill('dbachum_monitor')
  await dialog.getByLabel('Password').fill('secret')

  await dialog.getByRole('button', { name: 'Add connection' }).click()

  await expect(dialog).toHaveCount(0)
  await expect(page.locator('.connection-item').filter({ hasText: 'Warehouse SQL' })).toBeVisible()

  expect(state.createdConnections).toHaveLength(1)
  expect(state.createdConnections[0]).toMatchObject({
    name: 'Warehouse SQL',
    engine: 'sqlserver',
    host: 'warehouse-sql.example.local',
    port: 1433,
    username: 'dbachum_monitor',
    password: 'secret',
    database: 'Warehouse',
    oracle_identifier_type: null,
    oracle_identifier: null,
    oracle_auth_mode: null,
    active: true,
    monitor_enabled: true,
  })
})

test('adds an Oracle SYSDBA connection explicitly', async ({ page }) => {
  const state = await installMockApi(page)

  await page.goto('/settings/connections')
  await page.getByRole('button', { name: 'Add connection' }).click()

  const dialog = page.getByRole('dialog', { name: 'Add database connection' })

  await dialog.getByLabel('Connection name').fill('ERP SYS')
  await dialog.getByLabel('Host').fill('ora-sys.example.local')
  await dialog.getByPlaceholder('ORCLPDB1').fill('ERPPRD')
  await dialog.getByLabel('Oracle privilege mode').selectOption('sysdba')
  await dialog.getByLabel('Username').fill('SYS')
  await dialog.getByLabel('Password').fill('secret123')

  await expect(dialog).toContainText('unrestricted Oracle administrative access')

  await dialog.getByRole('button', { name: 'Add connection' }).click()

  expect(state.createdConnections.at(-1)).toMatchObject({
    engine: 'oracle',
    username: 'SYS',
    oracle_identifier_type: 'service_name',
    oracle_identifier: 'ERPPRD',
    oracle_auth_mode: 'sysdba',
  })
})



test('monitoring can be disabled without disabling the connection', async ({ page }) => {
  const state = await installMockApi(page)

  await page.goto('/settings/connections')
  await page.getByRole('button', { name: 'Add connection' }).click()

  const dialog = page.getByRole('dialog', { name: 'Add database connection' })
  await dialog.getByLabel('Connection name').fill('Provisioning Only')
  await dialog.getByLabel('Host').fill('ora-provision.example.local')
  await dialog.getByPlaceholder('ORCLPDB1').fill('ORMS')
  await dialog.getByLabel('Username').fill('SYS')
  await dialog.getByLabel('Password').fill('secret123')

  await expect(dialog.getByLabel('Connection enabled')).toBeChecked()
  await dialog.getByLabel('Monitor this connection').uncheck()
  await dialog.getByRole('button', { name: 'Add connection' }).click()

  expect(state.createdConnections.at(-1)).toMatchObject({
    name: 'Provisioning Only',
    active: true,
    monitor_enabled: false,
  })
})
