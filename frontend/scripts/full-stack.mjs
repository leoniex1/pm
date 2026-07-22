// Shared helpers for running the real full application (built frontend +
// FastAPI backend) locally for e2e tests or manual full-stack dev, without
// ever touching the real persistent backend/data/kanban.db.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, rmSync, mkdirSync, cpSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const FRONTEND_ROOT = path.resolve(__dirname, "..");
export const REPO_ROOT = path.resolve(FRONTEND_ROOT, "..");
export const BACKEND_STATIC_DIR = path.join(REPO_ROOT, "backend", "static");
export const FRONTEND_OUT_DIR = path.join(FRONTEND_ROOT, "out");

export function resolvePython() {
  const winPython = path.join(REPO_ROOT, ".venv", "Scripts", "python.exe");
  const posixPython = path.join(REPO_ROOT, ".venv", "bin", "python");
  if (existsSync(winPython)) return winPython;
  if (existsSync(posixPython)) return posixPython;
  return process.platform === "win32" ? "python" : "python3";
}

// Node's shell:true does not reliably/safely quote an argv array (see
// Node's own DEP0190 warning) - so any command run through a shell is built
// as a single, explicitly-quoted string instead of an argv array.
export function shellQuote(arg) {
  if (/^[A-Za-z0-9_\-./:@]+$/.test(arg)) {
    return arg;
  }
  return `"${arg.replace(/"/g, '\\"')}"`;
}

export function buildFrontend() {
  console.log("[full-stack] Building frontend static export...");
  const result = spawnSync("npm run build", {
    cwd: FRONTEND_ROOT,
    stdio: "inherit",
    shell: true,
  });
  if (result.status !== 0) {
    throw new Error("Frontend build failed.");
  }
}

export function copyFrontendIntoBackendStatic() {
  console.log("[full-stack] Copying static export into backend/static...");
  rmSync(BACKEND_STATIC_DIR, { recursive: true, force: true });
  mkdirSync(BACKEND_STATIC_DIR, { recursive: true });
  cpSync(FRONTEND_OUT_DIR, BACKEND_STATIC_DIR, { recursive: true });
}

export function cleanBackendStatic() {
  rmSync(BACKEND_STATIC_DIR, { recursive: true, force: true });
}

// Always a fresh scratch database in the OS temp directory - never the real
// backend/data/kanban.db - so building/running/testing locally can never
// lose or corrupt real board data.
export function createScratchDatabaseUrl() {
  const dir = mkdtempSync(path.join(tmpdir(), "pm-mvp-fullstack-"));
  const dbPath = path.join(dir, "fullstack.db");
  const normalized = dbPath.split(path.sep).join("/");
  return { url: `sqlite:///${normalized}`, dir };
}

export function startBackend({ port, databaseUrl }) {
  const python = resolvePython();
  console.log(`[full-stack] Starting backend on 127.0.0.1:${port} (scratch database)...`);
  return spawn(
    python,
    ["-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", String(port)],
    {
      cwd: REPO_ROOT,
      env: { ...process.env, DATABASE_URL: databaseUrl },
      stdio: "inherit",
    }
  );
}

export function stopBackend(child) {
  if (!child || child.exitCode !== null) {
    return;
  }
  console.log("[full-stack] Stopping backend...");
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"]);
  } else {
    child.kill("SIGTERM");
  }
}

export async function waitForHealth(url, { timeoutMs = 30000, intervalMs = 300 } = {}) {
  const deadline = Date.now() + timeoutMs;
  let lastError;

  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  throw new Error(
    `Backend did not become healthy at ${url} within ${timeoutMs}ms${lastError ? `: ${lastError}` : ""}`
  );
}
