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
    enabled: true,
  })
})
