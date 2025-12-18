const { test, expect, chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const envExecutable = process.env.CHROMIUM_PATH || process.env.PLAYWRIGHT_CHROMIUM_PATH;
const chromiumPath = envExecutable || chromium.executablePath();
const chromiumExists = chromiumPath && fs.existsSync(chromiumPath);

test.skip(!chromiumExists, 'Chromium binary unavailable; skipping UI smoke until browsers are installed.');

test('UI smoke: nav, API key, alerts, and tables', async ({ page }) => {
  const apiBase = 'http://localhost:9999';
  const indexUrl =
    'file://' +
    path.join(__dirname, '..', 'index.html') +
    `?api=${apiBase}&allow_url_api_key=1&api_key=devtoken`;

  const mockRuns = [
    {
      id: 'run-1',
      preset: 'health',
      hardware_target: 'sim_local',
      created_at: 1_700_000_000,
      kpis: { fidelity: 0.973, latency_us: 17.2, status: 'ok', shots_used: 1200, shot_budget: 2000 },
    },
    {
      id: 'run-2',
      preset: 'backend_compare',
      hardware_target: 'aws_braket',
      created_at: 1_700_000_100,
      kpis: { fidelity: 0.94, latency_us: 28.4, status: 'warn', shots_used: 800, shot_budget: 2000 },
      error_detail: { code: 'err_conn', message: 'Connectivity warning' },
    },
  ];

  let receivedApiKey;

  await page.route('**/health', async (route) => {
    receivedApiKey = route.request().headers()['x-api-key'];
    await route.fulfill({
      status: 200,
      json: {
        env: 'test',
        max_shots_per_experiment: 4096,
        default_shot_budget: 1024,
        allow_remote_hardware: true,
      },
    });
  });

  await page.route('**/hardware/targets', (route) =>
    route.fulfill({
      status: 200,
      json: {
        targets: [
          { id: 'sim_local', name: 'Local simulator', kind: 'sim', description: 'Local dev simulator' },
          { id: 'aws_braket', name: 'AWS Braket', kind: 'remote', description: 'Remote backend' },
        ],
      },
    })
  );

  await page.route('**/experiments/recent?limit=50', (route) =>
    route.fulfill({ status: 200, json: mockRuns })
  );

  await page.route('**/experiments/run', (route) =>
    route.fulfill({ status: 400, json: { detail: { code: 'mock_fail', message: 'Mock failure' } } })
  );

  await page.route('**/experiments/*', (route) => {
    const id = route.request().url().split('/').pop();
    const run = mockRuns.find((r) => r.id === id) || mockRuns[0];
    route.fulfill({ status: 200, json: run });
  });

  await page.goto(indexUrl);

  await expect(page.locator('#runStatus')).toHaveText(/Backend: connected/);
  expect(receivedApiKey).toBe('devtoken');

  await page.getByRole('button', { name: 'Experiments' }).click();
  await expect(page.locator('#view-experiments')).toHaveClass(/active/);

  const experimentsRows = page.locator('#experimentsBody tr');
  await expect(experimentsRows).toHaveCount(mockRuns.length);
  await expect(experimentsRows.nth(1)).toContainText('err_conn');

  await experimentsRows.first().click();
  await expect(page.locator('#view-details')).toHaveClass(/active/);
  await expect(page.locator('#detailsHeader')).toContainText(mockRuns[0].id);
  await page.getByRole('button', { name: 'Back' }).click();

  await page.getByRole('button', { name: 'Run preset' }).click();
  await expect(page.locator('#runStatus')).toContainText('Run failed');
  const alert = page.locator('#runAlert');
  await expect(alert).toBeVisible();
  await expect(alert).toContainText('Mock failure');
  await expect(page.locator('#runPresetBtn')).toBeEnabled();

  await page.getByRole('button', { name: 'Hardware' }).click();
  await expect(page.locator('#hardwareList .hardware-item')).toHaveCount(2);

  await page.getByRole('button', { name: 'Console' }).click();
  await expect(page.locator('#historyBody tr')).toHaveCount(mockRuns.length);
  await expect(page.locator('#historyBody tr').nth(1)).toContainText('err_conn');
});
