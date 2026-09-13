import { expect, test } from '@playwright/test'

import { installMockApi } from './helpers/mockApi'

test('shows database reachability and opens the database workspace', async ({ page }) => {
  await installMockApi(page)

  await page.goto('/databases')

  const oracleCard = page.locator('.database-card').filter({
    hasText: 'ERP Production',
  })
  await expect(oracleCard.locator('.database-reachability-dot')).toHaveClass(/database-reachability-dot--online/)

  const sqlCard = page.locator('.database-card').filter({
    hasText: 'Reporting SQL',
  })
  await expect(sqlCard.locator('.database-reachability-dot')).toHaveClass(/database-reachability-dot--unreachable/)

  await oracleCard.click()

  await expect(page).toHaveURL(/\/databases\/conn-oracle/)
  await expect(page.getByRole('heading', { name: 'ERP Production' })).toBeVisible()
  await expect(page.locator('.database-resource-context').getByLabel('Online')).toBeVisible()
  await expect(page.locator('.database-resource-context')).toContainText('ora01.example.local:1521')
})

test('opens the database Metrics tab and preserves route state', async ({ page }) => {
  await installMockApi(page)

  await page.goto('/databases/conn-oracle')

  const metricsButton = page.locator('.database-tabs').getByRole('button', {
    name: 'Metrics',
    exact: true,
  })

  await expect(metricsButton).toBeVisible()
  await metricsButton.click()

  await expect(metricsButton).toHaveClass(/active/)
  await expect(page.locator('.resource-breadcrumbs strong')).toHaveText('Metrics')
  await expect(page).toHaveURL(/(?:\?|&)tab=metrics(?:&|$)/)
  await expect(page.getByRole('heading', { name: 'ERP Production' })).toBeVisible()
})

test('switches between Metrics and Overview without breaking the database workspace', async ({ page }) => {
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  await installMockApi(page)

  await page.goto('/databases/conn-oracle')

  const tabs = page.locator('.database-tabs')
  const metricsButton = tabs.getByRole('button', { name: 'Metrics', exact: true })
  const overviewButton = tabs.getByRole('button', { name: 'Overview', exact: true })

  await metricsButton.click()
  await expect(metricsButton).toHaveClass(/active/)
  await expect(page.locator('.resource-breadcrumbs strong')).toHaveText('Metrics')

  await overviewButton.click()
  await expect(overviewButton).toHaveClass(/active/)
  await expect(page.locator('.resource-breadcrumbs strong')).toHaveText('Overview')
  await expect(page).not.toHaveURL(/(?:\?|&)tab=metrics(?:&|$)/)
  await expect(page.getByRole('heading', { name: 'ERP Production' })).toBeVisible()
})

test('shows Oracle users and schemas with filtering', async ({ page }) => {
  await installMockApi(page)

  await page.goto('/databases/conn-oracle')
  await page.getByRole('button', { name: 'Users / Access', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Users & Schemas' })).toBeVisible()
  await expect(page.getByText('APP_USER', { exact: true })).toBeVisible()
  await expect(page.getByText('LOCKED_USER', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: /Locked/ }).click()
  await expect(page.getByText('LOCKED_USER', { exact: true })).toBeVisible()
  await expect(page.getByText('APP_USER', { exact: true })).not.toBeVisible()

  await page.getByPlaceholder('Find username, status, tablespace or profile').fill('archive')
  await page.getByRole('button', { name: /Expired/ }).click()

  await expect(page.getByText('OLD_USER', { exact: true })).toBeVisible()
})

test('opens the current Oracle create-user wizard and generates a username', async ({ page }) => {
  await installMockApi(page)

  await page.goto('/databases/conn-oracle')
  await page.getByRole('button', { name: 'Users / Access', exact: true }).click()
  await page.getByRole('button', { name: /^Create/ }).click()
  await page.getByRole('menuitem', { name: 'Create user' }).click()

  const dialog = page.getByRole('dialog', { name: 'Create Oracle user' })
  await expect(dialog).toBeVisible()

  await dialog.getByLabel('Employee ID').fill('12345')
  await dialog.getByLabel('First name').fill('José')
  await dialog.getByLabel(/Middle name/).fill('Peña')
  await dialog.getByLabel('Last name').fill('Niño')
  await dialog.getByRole('button', { name: 'Generate username' }).click()

  await expect(dialog.locator('.username-generation-block input')).toHaveValue('JPNINO12345')
  await expect(dialog.getByRole('button', { name: 'Next' })).toBeEnabled()
})
