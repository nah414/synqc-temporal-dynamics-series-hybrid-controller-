// @ts-check
const { defineConfig } = require('@playwright/test');
const fs = require('fs');

function resolveExecutablePath() {
  const envPath = process.env.CHROMIUM_PATH || process.env.PLAYWRIGHT_CHROMIUM_PATH;
  const candidates = [
    envPath,
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      if (fs.existsSync(candidate)) return candidate;
    } catch (_) {
      /* ignore */
    }
  }
  return null;
}

const executablePath = resolveExecutablePath();

module.exports = defineConfig({
  testDir: './tests',
  fullyParallel: false,
  reporter: 'list',
  use: {
    headless: true,
    launchOptions: executablePath ? { executablePath } : {},
  },
});
