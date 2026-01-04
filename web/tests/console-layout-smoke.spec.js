const { test, expect, chromium } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const envExecutable = process.env.CHROMIUM_PATH || process.env.PLAYWRIGHT_CHROMIUM_PATH;
const chromiumPath = envExecutable || chromium.executablePath();
const chromiumExists = chromiumPath && fs.existsSync(chromiumPath);

test.skip(!chromiumExists, 'Chromium binary unavailable; skipping console layout smoke check until browsers are installed.');

test('Grover console layout smoke check', async ({ page }) => {
  const apiBase = 'http://localhost:9999';
  const indexUrl =
    'file://' +
    path.join(__dirname, '..', 'index.html') +
    `?api=${apiBase}&allow_url_api_key=1&api_key=devtoken`;

  await page.route('**/health', async (route) => {
    await route.fulfill({ status: 200, json: { env: 'test' } });
  });

  await page.route('**/hardware/targets', (route) =>
    route.fulfill({ status: 200, json: { targets: [] } })
  );

  await page.route('**/experiments/recent?limit=50', (route) =>
    route.fulfill({ status: 200, json: [] })
  );

  await page.route('**/agent/chat', async (route) => {
    const body = await route.request().postDataJSON();
    const reply = `ack:${body?.prompt || 'ok'}`;
    await route.fulfill({ status: 200, json: { reply } });
  });

  await page.goto(indexUrl);

  await page.getByRole('button', { name: 'Console' }).click();

  const backlogBtn = page.locator('#agentBacklogBtn');
  const backlogDrawer = page.locator('#agentBacklogDrawer');
  const clearBtn = page.locator('#agentClearBtn');
  const chatLog = page.locator('#agentChatLog');

  await expect(backlogDrawer).toHaveAttribute('data-open', 'false');
  await backlogBtn.click();
  await expect(backlogDrawer).toHaveAttribute('data-open', 'true');
  await backlogBtn.click();
  await expect(backlogDrawer).toHaveAttribute('data-open', 'false');

  await page.getByRole('button', { name: 'Setup' }).click();
  await expect(backlogDrawer).toBeHidden();
  await page.getByRole('button', { name: 'Agent' }).click();

  const initialUserMessages = await page.locator('#agentChatLog .msg-user').count();
  const initialScrollHeight = await chatLog.evaluate((el) => el.scrollHeight);
  const initialBodyHeight = await page.evaluate(() => document.body.scrollHeight);

  for (let i = 0; i < 5; i += 1) {
    await page.fill('#agentInput', `smoke ${i}`);
    const [response] = await Promise.all([
      page.waitForResponse((res) => res.url().includes('/agent/chat')),
      page.click('#agentSend'),
    ]);
    expect(response.ok()).toBeTruthy();
    await expect(page.locator('#agentSend')).toBeEnabled();
  }

  const finalUserMessages = await page.locator('#agentChatLog .msg-user').count();
  const finalScrollHeight = await chatLog.evaluate((el) => el.scrollHeight);
  const finalBodyHeight = await page.evaluate(() => document.body.scrollHeight);

  expect(finalUserMessages - initialUserMessages).toBe(5);
  expect(finalScrollHeight).toBeGreaterThan(initialScrollHeight);
  expect(finalBodyHeight - initialBodyHeight).toBeLessThan(150);

  if (await clearBtn.isVisible()) {
    await clearBtn.click();
    await expect(page.locator('#agentChatLog .msg-user')).toHaveCount(initialUserMessages);
  }
});
