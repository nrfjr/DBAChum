import { expect, test } from '@playwright/test'

import { installMockApi } from './helpers/mockApi'

test('shows database status and opens the database workspace', async ({ page }) => {
  await installMockApi(page)

  await page.goto('/databases')

  const oracleCard = page.locator('.database-card').filter({
    hasText: 'ERP Production',
  })

  await expect(oracleCard).toContainText('Online')
  await expect(oracleCard).toContainText('18 ms')
  await expect(oracleCard).toContainText('42')

  const sqlCard = page.locator('.database-card').filter({
    hasText: 'Reporting SQL',
  })

  await expect(sqlCard).toContainText('Unreachable')

  await oracleCard.click()

  await expect(page).toHaveURL(/\/databases\/conn-oracle$/)
  await expect(page.getByRole('heading', { name: 'ERP Production' })).toBeVisible()
  await expect(page.locator('.database-detail-header')).toContainText('Online')
  await expect(page.getByText('Oracle Database 19c')).toBeVisible()
  await expect(page.getByText('Oracle Server 01')).toBeVisible()
})

test('loads historical monitoring and changes metric and time range', async ({ page }) => {
  const state = await installMockApi(page)

  await page.goto('/databases/conn-oracle')
  await page.getByRole('button', { name: 'History' }).click()

  await expect(page.getByRole('heading', { name: 'Historical monitoring' })).toBeVisible()

  const sampleSummary = page.locator('.database-history-summary span').filter({
    hasText: 'Samples',
  })
  const rangeSummary = page.locator('.database-history-summary span').filter({
    hasText: 'Range',
  })

  await expect(sampleSummary).toContainText('3')
  await expect(rangeSummary).toContainText('24 hours')
  await expect(page.locator('.database-history-chart canvas')).toBeVisible()
  await expect.poll(() => state.historyHours.includes(24)).toBe(true)

  for (const metric of ['Connections', 'Blocked', 'Latency']) {
    await page.getByRole('button', { name: metric, exact: true }).click()
    await expect(page.getByRole('button', { name: metric, exact: true })).toHaveClass(/active/)
  }

  await page.getByRole('button', { name: '1h' }).click()
  await expect(rangeSummary).toContainText('1 hour')
  await expect(sampleSummary).toContainText('1')
  await expect.poll(() => state.historyHours.includes(1)).toBe(true)

  await page.getByRole('button', { name: '6h' }).click()
  await expect(rangeSummary).toContainText('6 hours')
  await expect.poll(() => state.historyHours.includes(6)).toBe(true)

  await page.getByRole('button', { name: '7d' }).click()
  await expect(rangeSummary).toContainText('7 days')
  await expect.poll(() => state.historyHours.includes(168)).toBe(true)
})

test('shows a useful history error without breaking the database page', async ({ page }) => {
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))

  await installMockApi(page, { historyFailure: true })

  await page.goto('/databases/conn-oracle')
  await page.getByRole('button', { name: 'History' }).click()

  await expect(page.getByText('Historical metrics unavailable.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Overview' })).toBeVisible()
  expect(pageErrors).toEqual([])
})


test('shows Oracle users and schemas with filtering', async ({ page }) => {
  await installMockApi(page)

  await page.goto('/databases/conn-oracle')
  await page.getByRole('button', { name: 'Users & Schemas' }).click()

  await expect(page.getByRole('heading', { name: 'Users & Schemas' })).toBeVisible()
  await expect(page.getByText('APP_USER', { exact: true })).toBeVisible()
  await expect(page.getByText('LOCKED_USER', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: /Locked/ }).click()
  await expect(page.getByText('LOCKED_USER', { exact: true })).toBeVisible()
  await expect(page.getByText('APP_USER', { exact: true })).not.toBeVisible()

  await page.getByPlaceholder('Username, status, tablespace or profile').fill('archive')
  await page.getByRole('button', { name: /Expired/ }).click()

  await expect(page.getByText('OLD_USER', { exact: true })).toBeVisible()
})
