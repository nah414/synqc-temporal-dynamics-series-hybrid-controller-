# UI hardening for hosted mode: disable URL-seeded credentials

Your `index.html` currently supports dev convenience:

- reads `?api_key=...` / `?token=...`
- stores into `localStorage`
- then removes from the URL

For hosted SaaS, this is risky:
- URLs can leak via referrers, browser history, screenshots, shared links, logging, etc.
- `localStorage` is accessible to any JS that runs in your origin (XSS blast radius)

## Recommended change

Only allow URL-seeded credentials when running locally (localhost/127.0.0.1) or `file://`.

### Drop-in patch

Find the block:

```js
const params = new URLSearchParams(window.location.search);

const fromBearer = params.get('token') || params.get('bearer');
const fromApiKey = params.get('api_key') || params.get('key');

if (fromBearer) { ... }
if (fromApiKey) { ... }
...
```

Wrap it with a guard:

```js
const isLocalDev =
  location.protocol === 'file:' ||
  location.hostname === 'localhost' ||
  location.hostname === '127.0.0.1';

const params = new URLSearchParams(window.location.search);

const fromBearer = params.get('token') || params.get('bearer');
const fromApiKey = params.get('api_key') || params.get('key');

if (isLocalDev) {
  if (fromBearer) { try { localStorage.setItem('synqc_bearer_token', fromBearer); } catch (_) {} }
  if (fromApiKey) { try { localStorage.setItem('synqc_api_key', fromApiKey); } catch (_) {} }
} else {
  // Hosted mode: strip these params WITHOUT persisting them
  if (fromBearer || fromApiKey) {
    console.warn('Ignoring token/api_key query params in hosted mode.');
  }
}

if (fromBearer || fromApiKey) {
  // keep your existing URL cleanup (params.delete(...), replaceState, etc)
}
```

Leaving the URL cleanup in place is still good: it prevents accidental sharing.

## Why this matters even with oauth2-proxy

If you deploy OIDC (oauth2-proxy) and rely on cookies, the UI does not need any API key at all.
Removing URL key support makes your hosted product:
- safer
- simpler for non-technical users
- easier to support (one auth mechanism)
