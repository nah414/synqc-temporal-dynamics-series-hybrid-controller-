# Archives and optional bundles

This directory groups historical or optional SynQc TDS assets that previously lived in the repository root. Use the subfolders below to find hosted deployment bundles, add-ons, and reference materials without cluttering the main code paths.

## Layout
- `hosted/`
  - Hosted deployment bundles and overlays, including compose files, templates, and nginx/oauth2-proxy guidance.
- `addons/`
  - Optional feature packs such as the Shor RSA add-on, with backend and frontend assets.
- `patches/`
  - One-off patch packs (for example, the physics contract patch).
- `crypto/`
  - Supporting cryptography scaffolds.

Each bundle retains its original README and docs. Start with the README inside a bundle for setup details.
