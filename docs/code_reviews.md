# Code Review Report

**Date:** 2026-07-21
**Scope:** Full repository — architecture, backend, frontend, authentication, database layer, AI integration, tests, configuration, documentation, security, error handling, maintainability, developer experience.
**Method:** Manual read of every application source file (backend `app/`, all backend tests, all frontend `src/` components/lib, all frontend tests, config files, Dockerfile, scripts, docs), plus direct verification of claims by running the test suites, `eslint`, and targeted reproduction commands rather than relying on documentation claims alone. No application code was modified.

---

## Executive summary

This is a small, well-scoped MVP with unusually good process discipline for its size: a locked-down structured-output contract for AI-driven board mutations, atomic all-or-nothing operation application, ownership isolation, and a documentation trail (`docs/PLAN.md`, `docs/DATABASE_DESIGN.md`, `docs/AI_STRUCTURED_OUTPUT_SCHEMA.md`) that was written and approved *before* the corresponding code. Backend test coverage is thorough and all 44 backend tests, 14 frontend unit tests, and 8 Playwright e2e tests pass.

The most important issues found are not in the "happy path" logic — they are in **operational safety** (a schema-drift check that silently drops and recreates the entire database on mismatch, with no migration path), **credential handling** (a column literally named `password_hash` that stores and compares plaintext), and **the reliability of the frontend's write path and its own test suite** (board saves are fire-and-forget with no error handling, and the documented default `npm run test:e2e` command cannot actually pass because Playwright's own bundled dev server has no backend behind it — verified by direct reproduction). None of these are exotic; they're all reachable by inspecting the code paths that already exist.

---

## Strengths

- **AI mutation safety is genuinely well engineered.** `structured_output.py` enforces a discriminated-union schema with `extra="forbid"`, per-operation required-field validation, duplicate-id rejection, position-bounds checking, and ownership-boundary checks — all validated against the current board snapshot *before* anything touches the database, then applied in one transaction. A validation failure anywhere aborts the whole batch. This is exactly the right shape for "let an LLM mutate state safely."
- **Documentation-first process.** The database schema and the AI output contract were written up and marked "approved" in `docs/` before implementation, and the docs are kept in sync with what's actually implemented (including an honest "gap analysis" section in `docs/DATABASE_DESIGN.md` and a documented "known residual risk" in `docs/PLAN.md` about intermittent strict-JSON-parse failures from the real model).
- **Path-traversal defense on static file serving.** `_resolve_static_file` in `main.py` resolves the requested path and explicitly checks it stays within the static root before serving — this is not a given for hand-rolled static serving and it's done correctly here.
- **Deterministic ordering model.** Using integer `position` columns with `(parent_id, position)` uniqueness constraints for both columns and cards gives a simple, testable, race-free ordering guarantee, and it's verified directly by DB-level constraint tests (`test_unique_position_constraints_enforced`, `test_uniqueness_constraints_and_indexes_exist`).
- **Backend test coverage is thorough and specific**, not just smoke tests: it covers auth flows, ownership isolation across two users, cascade-delete behavior, transaction rollback on a simulated write failure, and every rejection path in the AI operation validator (duplicate ids, invalid positions, unknown operation types, unknown fields, cross-board references).
- **No SQL injection surface** — every query goes through the SQLAlchemy ORM with bound parameters; no raw SQL string composition anywhere in the codebase.
- **Secrets hygiene is correct**: `.env` is gitignored, the OpenRouter API key is never echoed into logs, responses, or error messages, and `backend/data/*.db` is excluded from version control (confirmed empty via `git ls-files backend/data`).

---

## Findings

### Critical

**F1 — Schema-mismatch detection silently drops and recreates the entire database, with no migration path**
- **Affected files:** `backend/app/board_store.py` (`_schema_matches_expected`, `_ensure_schema`, called from `init_database()` at import time)
- **Issue:** On every app startup, `_ensure_schema()` inspects the live database; if it doesn't structurally match a small fixed checklist (specific tables, one unique constraint, a few index names), it calls `Base.metadata.drop_all(bind=ENGINE)` and recreates from scratch. There is no Alembic (or any) migration framework anywhere in the repo, and `docs/DATABASE_DESIGN.md`'s own "approved target schema" already lists columns (`created_at` on `users`/`boards`) that are **not** present in the current model — meaning the approved target schema itself would fail `_schema_matches_expected` and trigger a full drop the moment someone implements it as documented.
- **Why it matters:** `scripts/start-*.{ps1,sh}` explicitly bind-mount `backend/data` as a persistent volume specifically so board data survives container rebuilds. Any future schema change — even one already scoped and approved in the project's own docs — will silently wipe every user's board data on next deploy, with no backup, no warning, and no way to recover. This is the single highest-blast-radius latent defect in the codebase.
- **Recommended action:** Introduce a real migration tool (Alembic is the natural fit given SQLAlchemy is already in use) before making any further schema changes. At minimum, replace the silent `drop_all` with a hard failure (refuse to start, log clearly) so a schema mismatch is a loud deploy-time event an operator must act on, never a silent 3am data loss.

### High

**F2 — Passwords are stored and compared in plaintext behind a field literally named `password_hash`**
- **Affected files:** `backend/app/board_store.py` (`User.password_hash`, `authenticate_user`, `_ensure_user` calls with `"password"` as the literal argument)
- **Issue:** `authenticate_user` does `if user.password_hash != password: return None` — a direct plaintext string comparison, not a hash comparison, and not constant-time. The column is named as though hashing occurs; it does not. `docs/DATABASE_DESIGN.md` explicitly states "Password storage should be hash-only; no plaintext" as a design note for this exact table, so the implementation contradicts the project's own written requirement.
- **Why it matters:** For a single hardcoded local-only demo credential this has low practical exposure today, but the field name actively misleads any future maintainer into believing hashing is already handled, and multi-user support (an explicitly stated future goal in `AGENTS.md` and `docs/DATABASE_DESIGN.md`) cannot be safely built on top of this table as-is — a new user's password would be persisted in the clear.
- **Recommended action:** Either rename the column to reflect reality (`password_plaintext` is honest, if unappealing) with a comment explaining the accepted MVP tradeoff, or — better, since the cost is low — add `passlib`/`bcrypt` now and hash at `_ensure_user`/`authenticate_user` time so the multi-user foundation is actually sound before it's built on.

**F3 — Board writes from the frontend are fire-and-forget; no error handling or rollback on save failure**
- **Affected files:** `frontend/src/components/KanbanBoard.tsx` (`persistBoard`)
- **Issue:** `persistBoard` calls `setBoard(nextBoard)` (optimistic local update) and then `fetch("/api/board", { method: "PUT", ... })` — the response is never awaited for its status, never checked with `response.ok`, and there is no `catch`. Every mutation handler (`handleRenameColumn`, `handleAddCard`, `handleDeleteCard`, `handleDragEnd`) calls this via `void persistBoard(nextBoard)`, discarding the promise entirely.
- **Why it matters:** If the PUT fails (network blip, session expiry, a 422 from a malformed payload, a 500), the UI silently continues showing the optimistic state as if it had been saved. On reload, the user's most recent edit(s) can vanish with zero indication anything went wrong. This is a known, already-flagged gap — `docs/PLAN.md` Part 7 explicitly lists "Add optimistic or controlled update strategy with rollback/error UX" as unchecked — this review confirms it by reading the actual code path.
- **Recommended action:** At minimum, check `response.ok` in `persistBoard`, and on failure either revert to the last known-good board (refetch) or surface a visible error to the user. This does not need to be a full optimistic-UI framework — a single try/catch with a toast/banner and a re-fetch-on-failure would close the gap.

**F4 — The documented default `npm run test:e2e` cannot pass; verified by direct reproduction**
- **Affected files:** `frontend/playwright.config.ts`, `frontend/package.json` (`test:e2e` script), `frontend/tests/kanban.spec.ts`, `frontend/next.config.ts`, `frontend/src/app/page.tsx`
- **Issue:** `playwright.config.ts`'s `webServer` block runs plain `next dev` on port 3000 whenever `E2E_BASE_URL` is not set — which is the default, undocumented-elsewhere case (`frontend/README.md` and `frontend/AGENTS.md` both just say `npm run test:e2e`). But: (1) every frontend fetch call uses a relative path (`/api/board`, `/api/auth/login`, etc.), which in that mode resolves against the Next dev server itself — there is no backend on port 3000 and no proxy/rewrite configured anywhere (`next.config.ts` only sets `output: "export"`); and (2) the unauthenticated-redirect-to-`/login` behavior the very first test asserts is implemented **only** in FastAPI's catch-all route (`main.py`) — `frontend/src/app/page.tsx` renders `<KanbanBoard>` unconditionally with no client-side auth check at all. I reproduced this directly: running `npx playwright test -g "redirects unauthenticated"` without `E2E_BASE_URL` fails immediately (`Expected pattern: /\/login/, Received: "http://127.0.0.1:3000/"`). The full suite would fail the same way for every test that touches `/api/*`.
- **Why it matters:** This is the command every piece of documentation tells a new contributor to run. As shipped, it fails on the very first test, for reasons that have nothing to do with application correctness (the app itself is fine — I verified this in a prior session by building the static export, serving it through FastAPI, and pointing `E2E_BASE_URL` at that; all 8 tests passed). A new contributor following the README will conclude the app is broken.
- **Recommended action:** Either (a) document that e2e tests require `E2E_BASE_URL` pointed at a running backend-served build (and ideally provide a one-line script that builds the static export, copies it to `backend/static`, starts uvicorn, and runs Playwright against it — exactly the sequence used to validate this app in the previous test-running session), or (b) add a Next.js rewrite/proxy so `next dev` on 3000 actually forwards `/api/*` to a backend on 8000, making the zero-config path work as documented.

**F5 — `PUT /api/board` has no referential-integrity validation; malformed payloads either silently drop data or crash with an unhandled 500**
- **Affected files:** `backend/app/board_store.py` (`save_board`), `backend/app/main.py` (`update_board`)
- **Issue:** Beyond FastAPI's automatic Pydantic shape validation (field types/presence), there is no check that: cardIds referenced by a column actually exist in the `cards` dict (if not, `save_board` just `continue`s past them — silent data loss, not an error); card ids are unique across columns; or column ids are unique. Duplicate column/card ids in a submitted payload will fail the DB's own unique constraints inside `save_board`, raising an unhandled `IntegrityError` that FastAPI turns into a generic 500, rather than a clean validation error.
- **Why it matters:** `docs/PLAN.md` Part 6 already lists "Add error handling for invalid board/card/column operations" as unchecked — this review confirms the concrete failure modes. This endpoint is reachable by the authenticated frontend's own `PUT /api/board` calls (including AI-mutation-triggered saves), so a client-side bug or a manually crafted request can either corrupt board state invisibly or 500 the API with no actionable error message.
- **Recommended action:** Add an explicit validation pass in `save_board` (or a `model_validator` on `BoardData`) that rejects — with a clear 422 — any column referencing a card id not present in `cards`, and any duplicate column or card id, before touching the database.

### Medium

**F6 — No password-hashing library present anywhere in the dependency tree**
- **Affected files:** `backend/requirements.txt`
- **Issue:** Confirmed via `grep -ri "bcrypt|passlib|argon2|hashlib"` across the backend — no hashing dependency exists. Directly related to F2: there is currently no infrastructure to fix F2 without adding a dependency.
- **Why it matters:** Multi-user support is an explicit stated goal (`AGENTS.md`: "the database will support multiple users for future"); as it stands the schema is ready but the auth layer is not.
- **Recommended action:** Add `passlib[bcrypt]` (or similar) alongside the F2 fix.

**F7 — `pytest` is required by the test suite but declared nowhere in the repo**
- **Affected files:** `backend/requirements.txt` (missing), no `requirements-dev.txt` or `pyproject.toml` exists
- **Issue:** Verified directly this session: `pytest` was not installed in the project's `.venv`, nor in the system Python — despite `backend/tests/` containing 44 tests across 6 files, and a stale `.pytest_cache` at both repo root and `backend/` implying it was run previously via some undocumented ad hoc `pip install pytest`.
- **Why it matters:** A fresh clone (or CI runner) cannot run the backend test suite without first discovering and manually resolving this. There is also no CI configuration anywhere in the repo (`find . -iname "*.yml" -o -iname "*.yaml"` outside `node_modules` returns nothing) — so this has evidently never been caught by automation.
- **Recommended action:** Add a `backend/requirements-dev.txt` (or a `[test]` extra) pinning `pytest`, and consider adding a minimal CI workflow that installs it and runs both test suites — this would have caught F4 and F8 automatically.

**F8 — `npm run lint` currently fails**
- **Affected files:** `frontend/src/components/AiChatSidebar.tsx` (line 105)
- **Issue:** Verified directly by running `npm run lint`: two `react/no-unescaped-entities` errors on the literal straight quotes around the example prompt text ("Create a card in Backlog").
- **Why it matters:** This is a documented, always-available command (`frontend/AGENTS.md`, `package.json`) that is red right now. With no CI (see F7), nothing currently enforces it, so lint failures can accumulate silently.
- **Recommended action:** Replace the straight quotes with `&ldquo;`/`&rdquo;` (or a typographic `“…”`) at `AiChatSidebar.tsx:105`. Trivial fix; flagged here rather than silently patched because the task scope was review-only.

**F9 — CORS configuration implies a dev workflow that doesn't actually exist**
- **Affected files:** `backend/app/main.py` (`CORSMiddleware` config)
- **Issue:** CORS is configured to allow credentialed requests from `http://127.0.0.1:3000` and `http://localhost:3000` — clearly intended to support running the Next dev server separately from the FastAPI backend. But no frontend code ever constructs an absolute URL to the backend; every fetch call uses a relative path, so this configuration is never actually exercised by any code path in the repository. This is the same root cause as F4.
- **Why it matters:** Dead configuration that implies a supported workflow which doesn't work is worse than no configuration — it actively misleads whoever tries to use it (see F4's reproduction).
- **Recommended action:** Resolve alongside F4 — either wire up the proxy this CORS config is clearly meant to support, or remove it and document the actual required workflow.

**F10 — Inconsistent/missing length bounds on AI request input**
- **Affected files:** `backend/app/main.py` (`AIKanbanRequest.message`, `ConnectivityRequest.prompt`)
- **Issue:** `ConversationTurn.message` (used for history) is capped at 4000 chars via `Field(max_length=4000)`, but the *current* incoming `message`/`prompt` fields on the request models have no length constraint at all.
- **Why it matters:** The unbounded message is concatenated directly into the prompt sent to OpenRouter (`build_structured_prompt`) — an authenticated user (or a bug in the frontend) can send an arbitrarily large request body, inflating token cost with no server-side guard, inconsistent with how history turns are already bounded.
- **Recommended action:** Add the same `max_length=4000` (or similar) constraint to `AIKanbanRequest.message` and `ConnectivityRequest.prompt`.

**F11 — No rate limiting on AI endpoints**
- **Affected files:** `backend/app/main.py` (`/api/ai/respond`, `/api/ai/connectivity`)
- **Issue:** Any authenticated session can call these endpoints as fast as the client permits; there is no throttling.
- **Why it matters:** Each call is a real, billed OpenRouter request. For the current single-hardcoded-user local MVP this is low-risk, but it's a gap that needs to be closed before any multi-user or externally-reachable deployment (both explicitly floated as future directions).
- **Recommended action:** Not urgent for the current MVP scope; note it as a prerequisite for any deployment beyond local single-user use.

**F12 — Multi-user schema exists but the seeding logic only supports the one hardcoded account**
- **Affected files:** `backend/app/board_store.py` (`_ensure_board_for_user`)
- **Issue:** `_ensure_board_for_user` only seeds `INITIAL_BOARD_DATA` `if user.username == "user"`; any other user row would get a `Board` with zero columns and no code path to populate one (there is also no registration/user-creation endpoint at all currently).
- **Why it matters:** `docs/DATABASE_DESIGN.md` and `AGENTS.md` both frame the schema as multi-user-ready "for future" — this confirms that readiness is schema-only; the seeding/bootstrap logic is hardcoded to a single account and would need rework even to demo a second user.
- **Recommended action:** No action needed for current MVP scope; flag as a real prerequisite (not just a schema check) the day multi-user support is actually scheduled.

### Low

**F13 — Hardcoded session secret and `https_only=False` default**
- **Affected files:** `backend/app/main.py` (`SessionMiddleware`)
- **Issue:** `SESSION_SECRET` defaults to the literal string `"pm-mvp-dev-session-secret"` if unset, and `https_only=False` is hardcoded (not environment-driven).
- **Why it matters:** Fine for a local single-user Docker MVP; would need to change (a real secret, `https_only=True`) the moment this is exposed beyond localhost.
- **Recommended action:** No change needed now; worth a one-line comment noting these must change before any non-local deployment.

**F14 — Frontend card/column id generation uses `Math.random()`**
- **Affected files:** `frontend/src/lib/kanban.ts` (`createId`)
- **Issue:** IDs are `Math.random().toString(36)` plus a timestamp — not cryptographically random.
- **Why it matters:** Purely a display/identity id with no security role today (contrast with the AI path's stricter `^[a-zA-Z0-9_-]{1,64}$`-pattern ids), so this is cosmetic; flagging only because collision probability, while very low, is non-zero under rapid concurrent creation.
- **Recommended action:** No action needed; `crypto.randomUUID()` would be a trivial drop-in if ever revisited.

**F15 — Login page pre-fills the MVP credentials**
- **Affected files:** `frontend/src/app/login/page.tsx`
- **Issue:** The username/password inputs default to `useState("user")` / `useState("password")` — the actual working credentials are visibly pre-populated on page load.
- **Why it matters:** Convenient for local demoing; would hand out credentials immediately if this build were ever shown to anyone outside a trusted local session.
- **Recommended action:** No action needed for current MVP scope; remove the pre-fill before any wider demo/deployment.

**F16 — Unused default Next.js template assets not covered by the backend's public-path allowlist**
- **Affected files:** `frontend/public/{file,globe,next,vercel,window}.svg`, `backend/app/main.py` (`_FRONTEND_PUBLIC_PATHS`)
- **Issue:** These boilerplate assets are unreferenced by the current UI and, if requested directly while unauthenticated, would redirect to `/login` rather than 404 or serve — a minor inconsistency, not a functional bug since nothing currently links to them.
- **Why it matters:** Purely tidiness/maintainability; unused files add noise for future readers.
- **Recommended action:** Delete the unused SVGs during the next frontend cleanup pass.

---

## Test results / evidence reviewed

| Suite | Command | Result | Notes |
|---|---|---|---|
| Backend unit/integration | `pytest backend/tests` (from repo root, scratch SQLite DB) | **44/44 passed** | Run in a prior session this conversation continues from; `pytest` had to be installed manually into `.venv` first (see F7). |
| Frontend unit | `npm run test:unit` (Vitest) | **14/14 passed** | No server required. |
| Frontend e2e | `npm run test:e2e` equivalent, via built static export served by FastAPI + `E2E_BASE_URL` | **8/8 passed** | Required manually building the frontend, copying `frontend/out` into `backend/static`, and running the real backend — the zero-config default does not work (see F4). |
| Frontend e2e (default, no `E2E_BASE_URL`) | `npx playwright test -g "redirects unauthenticated"` | **1/1 failed** | Reproduced this session specifically to verify F4; test-results artifacts generated during this check were discarded and `git status` confirmed clean afterward. |
| Frontend lint | `npm run lint` | **2 errors** | `react/no-unescaped-entities` in `AiChatSidebar.tsx:105` (F8). |
| Static analysis | `grep` for `bcrypt\|passlib\|argon2\|hashlib`, `git ls-files backend/data`, search for CI config (`*.yml`/`*.yaml`) | No hashing library found; no DB files tracked in git (good); no CI configuration anywhere in the repo | Supports F6 and F7. |

---

## Prioritized action plan

1. **F1 (Critical):** Before any further schema work, add a real migration tool or replace the silent `drop_all` with a hard startup failure. This is the one item that can destroy real user data with a routine, well-intentioned change.
2. **F4 + F9 (High):** Fix or clearly document the e2e/dev workflow gap — either wire a dev proxy so `npm run dev` + `npm run test:e2e` work zero-config, or update `frontend/README.md`/`AGENTS.md` with the actual required steps (build + serve via backend + `E2E_BASE_URL`). This directly affects every future contributor's first experience with the repo.
3. **F3 (High):** Add minimal error handling (`response.ok` check + user-visible failure state) to `persistBoard` in `KanbanBoard.tsx`. Small, contained change with an outsized reliability payoff.
4. **F5 (High):** Add referential-integrity validation to the board-save path (`save_board` or a Pydantic validator on `BoardData`) so malformed payloads produce a clean 422 instead of silent data loss or an unhandled 500.
5. **F2 + F6 (High/Medium, do together):** Add a hashing library and hash passwords at creation/auth time, or at minimum rename `password_hash` to reflect current reality and note the accepted tradeoff explicitly in code and docs.
6. **F7 (Medium):** Pin `pytest` in a dev-requirements file; consider a minimal CI workflow — this is cheap and would have caught F4 and F8 automatically going forward.
7. **F8 (Medium):** One-line fix — escape the quotes in `AiChatSidebar.tsx:105`.
8. **F10 (Medium):** Add `max_length` to the AI request/prompt fields for consistency with `ConversationTurn`.
9. **F11, F12, F13, F14, F15, F16 (Medium/Low):** No immediate action required for the current single-user local MVP scope; keep this list as the checklist to work through the day multi-user support or any non-local deployment is actually scheduled.
