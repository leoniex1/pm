// Default `npm run test:e2e` entry point.
//
// Playwright's own webServer config only knows how to start a bare `next
// dev` (see playwright.config.ts), which has no backend behind it - every
// frontend fetch call is a relative path, and unauthenticated-redirect
// behavior lives only in the FastAPI backend, not in the Next app. So the
// zero-config default has to build the real app and run it through the
// real backend, exactly the way it's actually deployed.
//
// If E2E_BASE_URL is already set (e.g. pointed at a Docker container, or a
// manually-run `npm run dev:full`), this script gets out of the way and
// just runs Playwright directly against it.
import { spawnSync } from "node:child_process";
import { rmSync } from "node:fs";

import {
  FRONTEND_ROOT,
  buildFrontend,
  cleanBackendStatic,
  copyFrontendIntoBackendStatic,
  createScratchDatabaseUrl,
  shellQuote,
  startBackend,
  stopBackend,
  waitForHealth,
} from "./full-stack.mjs";

const PORT = 8000;

function runPlaywright(env) {
  const extraArgs = process.argv.slice(2).map(shellQuote);
  const command = ["npx", "playwright", "test", ...extraArgs].join(" ");
  const result = spawnSync(command, {
    cwd: FRONTEND_ROOT,
    stdio: "inherit",
    shell: true,
    env,
  });
  return result.status ?? 1;
}

async function main() {
  if (process.env.E2E_BASE_URL) {
    console.log(
      `[e2e] E2E_BASE_URL is set (${process.env.E2E_BASE_URL}); running Playwright against it directly.`
    );
    process.exitCode = runPlaywright(process.env);
    return;
  }

  buildFrontend();
  copyFrontendIntoBackendStatic();

  const { url: databaseUrl, dir: scratchDir } = createScratchDatabaseUrl();
  const backend = startBackend({ port: PORT, databaseUrl });

  try {
    await waitForHealth(`http://127.0.0.1:${PORT}/api/health`);

    console.log("[e2e] Running Playwright end-to-end suite against the full application...");
    process.exitCode = runPlaywright({
      ...process.env,
      E2E_BASE_URL: `http://127.0.0.1:${PORT}`,
    });
  } finally {
    stopBackend(backend);
    cleanBackendStatic();
    rmSync(scratchDir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error("[e2e]", error);
  process.exitCode = 1;
});
