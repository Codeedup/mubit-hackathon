import { expect, test } from '@playwright/test'

test('direct OpenRouter inference is labelled separately from Mubit and fixtures', async ({
  page,
  request,
}) => {
  const incident = await (await request.get('/api/incidents/DEV-001')).json()
  let saved = false
  const record = {
    id: 'openrouter-contract-check',
    incident_id: incident.id,
    incident,
    diagnosis: {
      cause_label: 'wheel obstruction',
      supporting_evidence: [
        {
          field: 'readings[1].value',
          explanation: 'High current with no wheel motion.',
        },
      ],
      alternative: 'motor power/driver path',
      next_check: 'Isolate power and inspect the wheel.',
      uncertainty: 'medium',
    },
    created_at: new Date().toISOString(),
    request_reference: 'gen_mock_contract_check',
    model_id: 'deepseek/deepseek-v4.1-flash-1017',
    provider_kind: 'openrouter',
    raw_response: 'wheel obstruction',
    model_label: 'wheel obstruction',
    advisory_source: 'application_rules',
  }
  await page.route('**/api/metrics', async (route) => {
    const response = await route.fetch()
    await route.fulfill({
      json: { ...(await response.json()), provider_status: 'openrouter' },
    })
  })
  await page.route('**/api/diagnoses', (route) =>
    route.fulfill({ json: saved ? [record] : [] }),
  )
  await page.route('**/api/diagnose', async (route) => {
    saved = true
    await route.fulfill({ status: 201, json: record })
  })
  await page.goto('/')
  await page
    .getByRole('button', { name: 'Diagnose through OpenRouter', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Wheel obstruction', exact: true }),
  ).toBeVisible()
  await expect(page.locator('.by-line')).toContainText(
    'through OpenRouter directly',
  )
  await expect(page.locator('.provenance')).toContainText('OpenRouter request')
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
  await page
    .getByRole('button', { name: 'History & evaluation', exact: true })
    .click()
  await expect(page.locator('.ledger')).toContainText('OpenRouter')
  await expect(page.locator('.ledger')).not.toContainText('Fixture')
})

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
