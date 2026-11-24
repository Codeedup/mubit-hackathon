import { expect, test } from '@playwright/test'

test('a fresh case can be diagnosed, corrected, reloaded, and exported', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await expect(
    page.getByRole('heading', { name: 'Turn a fault into a next step.' }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'New demo case', exact: true }).click()
  await page
    .getByRole('button', {
      name: 'Stopped wheel Zero speed with high motor current.',
    })
    .click()
  await expect(page.locator('.case-id')).toHaveText(/^DEMO-/)
  const caseId = (await page.locator('.case-id').innerText()).trim()
  expect(caseId).toMatch(/^DEMO-/)
  await page
    .getByRole('button', { name: 'Run offline diagnosis', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Wheel obstruction', exact: true }),
  ).toBeVisible()
  await page
    .getByRole('radio', { name: 'motor power/driver path', exact: true })
    .check()
  await page
    .getByLabel('Fix performed', { exact: true })
    .fill('Restored the simulated driver connection.')
  await page
    .getByLabel('What you found', { exact: true })
    .fill('The simulated driver wiring was disconnected; the wheel was free.')
  await page.getByLabel('Your name', { exact: true }).fill('Demo technician')
  await page
    .getByRole('button', { name: 'Record outcome', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Corrected: the cause was different' }),
  ).toBeVisible()
  await page
    .getByRole('button', { name: 'History & evaluation', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Request ledger', exact: true }),
  ).toBeVisible()
  await page.reload()
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
  const row = page
    .getByRole('row')
    .filter({ has: page.getByRole('button', { name: caseId, exact: true }) })
  await expect(row).toContainText('Was motor power/driver path')
  await row.getByRole('button', { name: caseId, exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Corrected: the cause was different' }),
  ).toBeVisible()
  const downloadPromise = page.waitForEvent('download')
  await page
    .getByRole('link', { name: 'Export workspace', exact: true })
    .click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('robo-medic-workspace.json')
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
  expect(errors).toEqual([])
})

test('ambiguous readings stay uncertain and setup reports missing integration', async ({
  page,
}) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'New demo case', exact: true }).click()
  await page
    .getByRole('button', {
      name: 'Missing evidence An ambiguous case that needs another measurement.',
    })
    .click()
  await page
    .getByRole('button', { name: 'Run offline diagnosis', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Cause unknown', exact: true }),
  ).toBeVisible()
  await expect(page.getByLabel('Uncertainty high')).toBeVisible()
  await page.getByRole('button', { name: 'Setup', exact: true }).click()
  await page
    .getByRole('button', { name: 'Check Mubit status', exact: true })
    .click()
  await expect(page.getByRole('status')).toContainText(
    'Connect a management key and task ID',
  )
  await page
    .getByRole('button', { name: 'Switch to dark theme', exact: true })
    .click()
  await page.reload()
  await expect(
    page.getByRole('button', { name: 'Switch to light theme', exact: true }),
  ).toBeVisible()
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
})
