// `npm run dev:full` - builds the frontend and serves it through the real
// FastAPI backend on a scratch database, for manual full-stack local
// testing without Docker. `npm run dev` alone only runs the Next.js dev
// server, which has no backend behind it (see scripts/e2e.mjs for why).
import {
  buildFrontend,
  copyFrontendIntoBackendStatic,
  createScratchDatabaseUrl,
  startBackend,
  stopBackend,
  waitForHealth,
} from "./full-stack.mjs";

const PORT = Number(process.env.PORT) || 8000;

async function main() {
  buildFrontend();
  copyFrontendIntoBackendStatic();

  const { url: databaseUrl } = createScratchDatabaseUrl();
  const backend = startBackend({ port: PORT, databaseUrl });

  const shutdown = () => {
    stopBackend(backend);
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  await waitForHealth(`http://127.0.0.1:${PORT}/api/health`);
  console.log(`\n[serve] Full application running at http://127.0.0.1:${PORT}`);
  console.log("[serve] Login with user / password.");
  console.log(
    "[serve] Using a scratch database (not backend/data/kanban.db) - changes here do not persist. Press Ctrl+C to stop.\n"
  );
}

main().catch((error) => {
  console.error("[serve]", error);
  process.exitCode = 1;
});
