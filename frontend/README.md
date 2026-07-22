# Kanban Studio

## Run

```bash
npm install
npm run dev
```

`npm run dev` is UI-only: it starts the Next.js dev server with no backend behind it, so `/api/*` calls
will not resolve. For the real app locally, run `npm run dev:full` instead (builds the frontend and
serves it through the FastAPI backend on a scratch database).

## Tests

```bash
npm run test:unit
npm run test:e2e
```

`npm run test:e2e` builds the frontend, serves it through the real backend on a scratch database, runs
the full Playwright suite, and tears the backend down afterward. Set `E2E_BASE_URL` beforehand to run
against something else (e.g. a Docker container already running) instead.
