# Code Review Report

**Date:** 2026-07-21
**Scope:** Full repository — architecture, backend, frontend, authentication, database layer, AI integration, tests, configuration, documentation, security, error handling, maintainability, developer experience.
**Method:** Manual read of every application source file (backend `app/`, all backend tests, all frontend `src/` components/lib, all frontend tests, config files, Dockerfile, scripts, docs), plus direct verification of claims by running the test suites, `eslint`, and targeted reproduction commands rather than relying on documentation claims alone. No application code was modified.

---

## Executive summary

This is a small, well-scoped MVP with unusually good process discipline for its size: a locked-down structured-output contract for AI-driven board mutations, atomic all-or-nothing operation application, ownership isolation, and a documentation trail (`docs/PLAN.md`, `docs/DATABASE_DESIGN.md`, `docs/AI_STRUCTURED_OUTPUT_SCHEMA.md`) that was written and approved *before* the corresponding code. Backend test coverage is thorough and all 44 backend tests, 14 frontend unit tests, and 8 Playwright e2e tests pass.

The most important issues found are not in the "happy path" logic — they are in **operational safety** (a schema-drift check that silently drops and recreates the entire database on mismatch, with no migration path), **credential handling** (a column literally named `password_hash` that stores and compares plaintext), and **the reliability of the frontend's write path and its own test suite** (board saves are fire-and-forget with no error handling, and the documented default `npm run test:e2e` command cannot actually pass because Playwright's own bundled dev server has no backend behind it — verified by direct reproduction). None of these are exotic; they're all reachable by inspecting the code paths that already exist.

---

## Remediation status (2026-07-22)

All 16 findings — Critical (F1), High (F2–F5), Medium (F6–F12), and now Low (F13–F16) — have been
remediated in this repository. Every finding below has a **Remediation** block recording what changed,
which files were touched, and what test evidence backs the fix.

### Second remediation pass (2026-07-22): F13–F16, and a `backend/app/main.py` refactor

F13–F16 were remediated on 2026-07-22, and `backend/app/main.py` (previously a single 319-line file
holding every route, model, and helper) was split into a package — `config.py`, `middleware.py`,
`dependencies.py`, and `routers/{auth,board,ai,health,frontend}.py` — with `main.py` reduced to app
creation, middleware/DB wiring, and router registration. This was a pure reorganization: every endpoint,
response shape, auth behavior, and DB behavior was preserved and re-verified by the full test suite
(80/80 backend tests passing after the move, up from 62, with only import/monkeypatch *paths* updated
in 4 test files to point at the new module locations — no assertions changed). See the F13–F16 entries
below and the "After second remediation pass" test table for full evidence.

Files changed in this second pass:

- `backend/app/config.py`, `middleware.py`, `dependencies.py` (new); `backend/app/routers/` (new package:
  `auth.py`, `board.py`, `ai.py`, `health.py`, `frontend.py`) — the `main.py` refactor, and F13's
  session-secret/HTTPS-only configuration.
- `backend/app/main.py` — reduced to a thin entrypoint.
- `backend/tests/test_config.py`, `test_app_structure.py` (new) — F13 and refactor-safety tests.
- `backend/tests/conftest.py`, `test_ai_structured.py`, `test_openrouter.py` — updated import/monkeypatch
  paths only (`backend.app.main.*` → `backend.app.routers.ai.*`), required by the refactor.
- `frontend/src/lib/kanban.ts` — F14: `createId` now uses `crypto.randomUUID()`.
- `frontend/src/lib/kanban.test.ts` — new `createId` tests.
- `frontend/src/app/login/page.tsx` — F15: removed prefilled username/password.
- `frontend/src/app/login/page.test.tsx` (new) — confirms empty fields.
- `frontend/public/{file,globe,next,vercel,window}.svg` (deleted) — F16.
- `CLAUDE.md`, `backend/AGENTS.md`, `frontend/AGENTS.md` — updated for the new backend structure and
  F13–F15.

### First remediation pass (2026-07-21): F1–F12

Summary of files changed in the first pass:

- `backend/app/board_store.py` — Alembic-based schema management (F1), bcrypt password hashing (F2/F6),
  `BoardData` referential-integrity validator (F5), collision-safe multi-user seeding (F12).
- `backend/app/main.py` — removed dead CORS middleware (F9), added AI input length limits (F10) and
  per-user AI rate limiting (F11).
- `backend/alembic.ini`, `backend/migrations/` (new) — migration scaffolding and the initial schema
  revision (F1).
- `backend/requirements.txt` — added `alembic`, `bcrypt` (F1, F2/F6).
- `backend/requirements-dev.txt` (new) — pins `pytest` (F7).
- `backend/tests/conftest.py` (new) — resets AI rate-limit state between tests (supports F11 tests).
- `backend/tests/test_password_security.py`, `test_schema_migrations.py` (new); `test_board.py`,
  `test_ai_structured.py`, `test_openrouter.py` (extended) — new/updated tests for every remediation.
- `frontend/src/components/KanbanBoard.tsx` — `persistBoard` now detects and reports save failures (F3).
- `frontend/src/components/KanbanBoard.test.tsx` — new test for the failed-save/revert path.
- `frontend/src/components/AiChatSidebar.tsx` — fixed lint errors (F8).
- `frontend/scripts/full-stack.mjs`, `e2e.mjs`, `serve.mjs` (new) — build+serve orchestration so the
  default `npm run test:e2e` runs against the real full application (F4/F9).
- `frontend/package.json` — `test:e2e` now runs the orchestration script; added `dev:full`,
  `test:e2e:raw` (F4/F9).
- `CLAUDE.md`, `backend/AGENTS.md`, `frontend/AGENTS.md`, `frontend/README.md`,
  `docs/DATABASE_DESIGN.md` — updated to describe all of the above.

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
- **Remediation:** Adopted Alembic. `backend/migrations/versions/0001_initial_schema.py` hand-written to
  exactly mirror the schema `create_all` previously produced. `board_store._ensure_schema()` no longer
  calls `drop_all` on the normal path: a brand-new database is `upgrade`d to head; a database already
  managed by Alembic gets pending migrations applied; a database created before Alembic was adopted
  (tables exist, no `alembic_version` table) is `stamp`ed to head in place — no table is ever dropped.
  `reset_database()` remains a test-only `drop_all`/`create_all` utility, unchanged in purpose, never
  called from the startup path.
  - **Files:** `backend/app/board_store.py`, `backend/alembic.ini` (new), `backend/migrations/env.py`
    (new), `backend/migrations/script.py.mako` (new), `backend/migrations/versions/0001_initial_schema.py`
    (new), `backend/requirements.txt` (added `alembic`).
  - **Tests added:** `backend/tests/test_schema_migrations.py` — `test_fresh_database_is_created_via_migrations`,
    and critically `test_preexisting_database_without_alembic_is_adopted_without_data_loss` (creates a
    database the old way, inserts a real row, runs the new `_ensure_schema()`, asserts the row survives
    byte-for-byte and `alembic_version` is now present), plus
    `test_ensure_schema_is_idempotent_and_never_drops_data`.
  - **Verification evidence:** all three new tests pass; manually reproduced the exact scenario before
    writing the automated test (created a pre-Alembic DB with a real row via direct `sqlalchemy`/`sqlite3`
    calls, ran `_ensure_schema()`, confirmed the row was untouched and `alembic_version` was created) —
    see the "Test results" table below.

### High

**F2 — Passwords are stored and compared in plaintext behind a field literally named `password_hash`**
- **Affected files:** `backend/app/board_store.py` (`User.password_hash`, `authenticate_user`, `_ensure_user` calls with `"password"` as the literal argument)
- **Issue:** `authenticate_user` does `if user.password_hash != password: return None` — a direct plaintext string comparison, not a hash comparison, and not constant-time. The column is named as though hashing occurs; it does not. `docs/DATABASE_DESIGN.md` explicitly states "Password storage should be hash-only; no plaintext" as a design note for this exact table, so the implementation contradicts the project's own written requirement.
- **Why it matters:** For a single hardcoded local-only demo credential this has low practical exposure today, but the field name actively misleads any future maintainer into believing hashing is already handled, and multi-user support (an explicitly stated future goal in `AGENTS.md` and `docs/DATABASE_DESIGN.md`) cannot be safely built on top of this table as-is — a new user's password would be persisted in the clear.
- **Recommended action:** Either rename the column to reflect reality (`password_plaintext` is honest, if unappealing) with a comment explaining the accepted MVP tradeoff, or — better, since the cost is low — add `passlib`/`bcrypt` now and hash at `_ensure_user`/`authenticate_user` time so the multi-user foundation is actually sound before it's built on.
- **Remediation:** Added `bcrypt` and hash at write time / verify at read time: `_hash_password` (used by
  `_ensure_user`) and `_verify_password` (used by `authenticate_user`, via `bcrypt.checkpw` — not a
  string comparison). `password_hash` now genuinely holds a bcrypt hash.
  - **Files:** `backend/app/board_store.py`, `backend/requirements.txt` (added `bcrypt`).
  - **Tests added:** `backend/tests/test_password_security.py` — asserts the stored value is not the
    plaintext password and starts with the bcrypt `$2b$` prefix, a direct hash/verify round-trip test,
    `authenticate_user` accept/reject tests, and an end-to-end login test confirming the HTTP login flow
    still works unchanged with hashed storage underneath.
  - **Verification evidence:** all 5 new tests pass; pre-existing `test_invalid_login_fails` and
    `test_login_session_logout_flow` (which exercise login via HTTP) continue to pass unmodified.

**F3 — Board writes from the frontend are fire-and-forget; no error handling or rollback on save failure**
- **Affected files:** `frontend/src/components/KanbanBoard.tsx` (`persistBoard`)
- **Issue:** `persistBoard` calls `setBoard(nextBoard)` (optimistic local update) and then `fetch("/api/board", { method: "PUT", ... })` — the response is never awaited for its status, never checked with `response.ok`, and there is no `catch`. Every mutation handler (`handleRenameColumn`, `handleAddCard`, `handleDeleteCard`, `handleDragEnd`) calls this via `void persistBoard(nextBoard)`, discarding the promise entirely.
- **Why it matters:** If the PUT fails (network blip, session expiry, a 422 from a malformed payload, a 500), the UI silently continues showing the optimistic state as if it had been saved. On reload, the user's most recent edit(s) can vanish with zero indication anything went wrong. This is a known, already-flagged gap — `docs/PLAN.md` Part 7 explicitly lists "Add optimistic or controlled update strategy with rollback/error UX" as unchecked — this review confirms it by reading the actual code path.
- **Recommended action:** At minimum, check `response.ok` in `persistBoard`, and on failure either revert to the last known-good board (refetch) or surface a visible error to the user. This does not need to be a full optimistic-UI framework — a single try/catch with a toast/banner and a re-fetch-on-failure would close the gap.
- **Remediation:** `persistBoard` now wraps the request in try/catch, checks `response.ok`, and on any
  failure (non-OK response or thrown error) reverts local state to the pre-edit board and sets a
  `saveError` message rendered as a dismissible banner (`data-testid="board-save-error"`) in
  `KanbanBoard`'s render tree.
  - **Files:** `frontend/src/components/KanbanBoard.tsx`.
  - **Tests added:** `frontend/src/components/KanbanBoard.test.tsx` — `"shows an error and reverts the
    board when saving fails"`: mocks a 500 response from `PUT /api/board`, performs an add-card action,
    asserts the error banner appears and the optimistically-added card is reverted/absent.
  - **Verification evidence:** new test passes; all pre-existing `KanbanBoard.test.tsx` tests continue
    to pass unmodified.

**F4 — The documented default `npm run test:e2e` cannot pass; verified by direct reproduction**
- **Affected files:** `frontend/playwright.config.ts`, `frontend/package.json` (`test:e2e` script), `frontend/tests/kanban.spec.ts`, `frontend/next.config.ts`, `frontend/src/app/page.tsx`
- **Issue:** `playwright.config.ts`'s `webServer` block runs plain `next dev` on port 3000 whenever `E2E_BASE_URL` is not set — which is the default, undocumented-elsewhere case (`frontend/README.md` and `frontend/AGENTS.md` both just say `npm run test:e2e`). But: (1) every frontend fetch call uses a relative path (`/api/board`, `/api/auth/login`, etc.), which in that mode resolves against the Next dev server itself — there is no backend on port 3000 and no proxy/rewrite configured anywhere (`next.config.ts` only sets `output: "export"`); and (2) the unauthenticated-redirect-to-`/login` behavior the very first test asserts is implemented **only** in FastAPI's catch-all route (`main.py`) — `frontend/src/app/page.tsx` renders `<KanbanBoard>` unconditionally with no client-side auth check at all. I reproduced this directly: running `npx playwright test -g "redirects unauthenticated"` without `E2E_BASE_URL` fails immediately (`Expected pattern: /\/login/, Received: "http://127.0.0.1:3000/"`). The full suite would fail the same way for every test that touches `/api/*`.
- **Why it matters:** This is the command every piece of documentation tells a new contributor to run. As shipped, it fails on the very first test, for reasons that have nothing to do with application correctness (the app itself is fine — I verified this in a prior session by building the static export, serving it through FastAPI, and pointing `E2E_BASE_URL` at that; all 8 tests passed). A new contributor following the README will conclude the app is broken.
- **Recommended action:** Either (a) document that e2e tests require `E2E_BASE_URL` pointed at a running backend-served build (and ideally provide a one-line script that builds the static export, copies it to `backend/static`, starts uvicorn, and runs Playwright against it — exactly the sequence used to validate this app in the previous test-running session), or (b) add a Next.js rewrite/proxy so `next dev` on 3000 actually forwards `/api/*` to a backend on 8000, making the zero-config path work as documented.
- **Remediation:** Went with option (a), since option (b) is not actually possible given
  `next.config.ts`'s `output: "export"` (Next disables rewrites/middleware entirely for static export —
  there is no server for a rewrite to run on). Added `frontend/scripts/full-stack.mjs` (shared
  build/copy/start-backend/health-check/stop helpers), `frontend/scripts/e2e.mjs` (the new `test:e2e`:
  builds the frontend, copies the export into `backend/static`, starts the real FastAPI backend on a
  scratch database in the OS temp directory, waits for `/api/health`, runs Playwright with
  `E2E_BASE_URL` pointed at it, and always tears the backend down in a `finally` block — success or
  failure), and `frontend/scripts/serve.mjs` (`npm run dev:full`: the same build+serve, left running in
  the foreground for manual local full-stack testing without Docker). If `E2E_BASE_URL` is already set,
  `e2e.mjs` skips all orchestration and runs Playwright directly against it (unchanged prior behavior
  for that case). `package.json` gained `dev:full` and `test:e2e:raw` (direct Playwright, no
  orchestration) alongside the redefined `test:e2e`.
  - **Files:** `frontend/scripts/full-stack.mjs` (new), `frontend/scripts/e2e.mjs` (new),
    `frontend/scripts/serve.mjs` (new), `frontend/package.json`, `frontend/README.md`,
    `frontend/AGENTS.md`, `CLAUDE.md`.
  - **Verification evidence:** ran `npm run test:e2e -- -g "redirects unauthenticated"` (the exact test
    that failed in the original F4 reproduction) with no `E2E_BASE_URL` set — it now builds, serves, and
    passes. Ran the full default `npm run test:e2e` with no `E2E_BASE_URL` set — all 8 tests pass,
    `backend/static` is cleaned up afterward, and the backend process is confirmed stopped (verified via
    `Get-NetTCPConnection` showing the port released). See the "Test results" table below.

**F5 — `PUT /api/board` has no referential-integrity validation; malformed payloads either silently drop data or crash with an unhandled 500**
- **Affected files:** `backend/app/board_store.py` (`save_board`), `backend/app/main.py` (`update_board`)
- **Issue:** Beyond FastAPI's automatic Pydantic shape validation (field types/presence), there is no check that: cardIds referenced by a column actually exist in the `cards` dict (if not, `save_board` just `continue`s past them — silent data loss, not an error); card ids are unique across columns; or column ids are unique. Duplicate column/card ids in a submitted payload will fail the DB's own unique constraints inside `save_board`, raising an unhandled `IntegrityError` that FastAPI turns into a generic 500, rather than a clean validation error.
- **Why it matters:** `docs/PLAN.md` Part 6 already lists "Add error handling for invalid board/card/column operations" as unchecked — this review confirms the concrete failure modes. This endpoint is reachable by the authenticated frontend's own `PUT /api/board` calls (including AI-mutation-triggered saves), so a client-side bug or a manually crafted request can either corrupt board state invisibly or 500 the API with no actionable error message.
- **Recommended action:** Add an explicit validation pass in `save_board` (or a `model_validator` on `BoardData`) that rejects — with a clear 422 — any column referencing a card id not present in `cards`, and any duplicate column or card id, before touching the database.
- **Remediation:** Added a `model_validator(mode="after")` directly on `BoardData` (so it runs for
  every construction path, including `PUT /api/board`'s automatic FastAPI/Pydantic parsing): rejects
  duplicate column ids, duplicate card ids referenced across columns, cardIds referencing a missing
  card entry, and orphaned `cards` entries not referenced by any column — each with a specific 422
  message rather than a generic 500.
  - **Files:** `backend/app/board_store.py`.
  - **Tests added:** `backend/tests/test_board.py` —
    `test_board_payload_with_missing_card_reference_is_rejected`,
    `test_board_payload_with_orphaned_card_entry_is_rejected`,
    `test_board_payload_with_duplicate_card_id_across_columns_is_rejected`,
    `test_board_payload_with_duplicate_column_id_is_rejected`.
  - **Verification evidence:** all 4 new tests pass with 422 responses (confirmed no unhandled 500 for
    any of these cases); pre-existing `test_board_persistence_for_rename_add_delete_and_move` (which
    manipulates real board payloads through add/delete/move) continues to pass unmodified, confirming
    the new validator doesn't reject legitimate payloads.

### Medium

**F6 — No password-hashing library present anywhere in the dependency tree**
- **Affected files:** `backend/requirements.txt`
- **Issue:** Confirmed via `grep -ri "bcrypt|passlib|argon2|hashlib"` across the backend — no hashing dependency exists. Directly related to F2: there is currently no infrastructure to fix F2 without adding a dependency.
- **Why it matters:** Multi-user support is an explicit stated goal (`AGENTS.md`: "the database will support multiple users for future"); as it stands the schema is ready but the auth layer is not.
- **Recommended action:** Add `passlib[bcrypt]` (or similar) alongside the F2 fix.
- **Remediation:** Added `bcrypt` to `backend/requirements.txt`, used by `_hash_password`/
  `_verify_password` in `board_store.py`. Resolved together with F2 above.
  - **Files:** `backend/requirements.txt`.
  - **Verification evidence:** see F2's test evidence — `bcrypt` is exercised by every test in
    `test_password_security.py` plus every HTTP login test.

**F7 — `pytest` is required by the test suite but declared nowhere in the repo**
- **Affected files:** `backend/requirements.txt` (missing), no `requirements-dev.txt` or `pyproject.toml` exists
- **Issue:** Verified directly this session: `pytest` was not installed in the project's `.venv`, nor in the system Python — despite `backend/tests/` containing 44 tests across 6 files, and a stale `.pytest_cache` at both repo root and `backend/` implying it was run previously via some undocumented ad hoc `pip install pytest`.
- **Why it matters:** A fresh clone (or CI runner) cannot run the backend test suite without first discovering and manually resolving this. There is also no CI configuration anywhere in the repo (`find . -iname "*.yml" -o -iname "*.yaml"` outside `node_modules` returns nothing) — so this has evidently never been caught by automation.
- **Recommended action:** Add a `backend/requirements-dev.txt` (or a `[test]` extra) pinning `pytest`, and consider adding a minimal CI workflow that installs it and runs both test suites — this would have caught F4 and F8 automatically.
- **Remediation:** Added `backend/requirements-dev.txt` (`-r requirements.txt` plus `pytest==9.1.1`,
  matching the version actually verified working). A dedicated CI workflow was judged out of scope for
  this remediation pass (no CI config of any kind exists in the repo yet, and adding one is a
  larger/separate infrastructure decision) — noted here as a good follow-up, not done.
  - **Files:** `backend/requirements-dev.txt` (new).
  - **Verification evidence:** `pip install -r backend/requirements-dev.txt` into a clean check of the
    venv installs `pytest` correctly; full suite run via this file passes (see "Test results" below).

**F8 — `npm run lint` currently fails**
- **Affected files:** `frontend/src/components/AiChatSidebar.tsx` (line 105)
- **Issue:** Verified directly by running `npm run lint`: two `react/no-unescaped-entities` errors on the literal straight quotes around the example prompt text ("Create a card in Backlog").
- **Why it matters:** This is a documented, always-available command (`frontend/AGENTS.md`, `package.json`) that is red right now. With no CI (see F7), nothing currently enforces it, so lint failures can accumulate silently.
- **Recommended action:** Replace the straight quotes with `&ldquo;`/`&rdquo;` (or a typographic `“…”`) at `AiChatSidebar.tsx:105`. Trivial fix; flagged here rather than silently patched because the task scope was review-only.
- **Remediation:** Replaced the straight quotes with `&ldquo;`/`&rdquo;` entities as recommended.
  - **Files:** `frontend/src/components/AiChatSidebar.tsx`.
  - **Verification evidence:** `npm run lint` now exits 0 with no output/errors.

**F9 — CORS configuration implies a dev workflow that doesn't actually exist**
- **Affected files:** `backend/app/main.py` (`CORSMiddleware` config)
- **Issue:** CORS is configured to allow credentialed requests from `http://127.0.0.1:3000` and `http://localhost:3000` — clearly intended to support running the Next dev server separately from the FastAPI backend. But no frontend code ever constructs an absolute URL to the backend; every fetch call uses a relative path, so this configuration is never actually exercised by any code path in the repository. This is the same root cause as F4.
- **Why it matters:** Dead configuration that implies a supported workflow which doesn't work is worse than no configuration — it actively misleads whoever tries to use it (see F4's reproduction).
- **Recommended action:** Resolve alongside F4 — either wire up the proxy this CORS config is clearly meant to support, or remove it and document the actual required workflow.
- **Remediation:** Removed `CORSMiddleware` entirely. Confirmed it could never be legitimately wired up
  as originally implied: `next.config.ts` uses `output: "export"`, and Next disables rewrites/middleware
  entirely for static export, so there is no way to proxy `/api/*` from `next dev` to the backend at the
  framework level. The actual fix for the underlying need (a way to exercise the full app locally) is
  F4's same-origin build+serve scripts (`npm run dev:full`, `npm run test:e2e`), which make cross-origin
  requests — and therefore CORS — unnecessary. Replaced the middleware with a short comment explaining
  why none is needed.
  - **Files:** `backend/app/main.py`.
  - **Verification evidence:** full backend suite (62 tests) passes with no CORS middleware present;
    full e2e suite (8/8) passes against the same-origin build+serve workflow from F4.

**F10 — Inconsistent/missing length bounds on AI request input**
- **Affected files:** `backend/app/main.py` (`AIKanbanRequest.message`, `ConnectivityRequest.prompt`)
- **Issue:** `ConversationTurn.message` (used for history) is capped at 4000 chars via `Field(max_length=4000)`, but the *current* incoming `message`/`prompt` fields on the request models have no length constraint at all.
- **Why it matters:** The unbounded message is concatenated directly into the prompt sent to OpenRouter (`build_structured_prompt`) — an authenticated user (or a bug in the frontend) can send an arbitrarily large request body, inflating token cost with no server-side guard, inconsistent with how history turns are already bounded.
- **Recommended action:** Add the same `max_length=4000` (or similar) constraint to `AIKanbanRequest.message` and `ConnectivityRequest.prompt`.
- **Remediation:** Added `Field(min_length=1, max_length=4000)` to `AIKanbanRequest.message` and
  `Field(default="What is 2 + 2?", max_length=4000)` to `ConnectivityRequest.prompt`, matching
  `ConversationTurn.message`'s existing bound.
  - **Files:** `backend/app/main.py`.
  - **Tests added:** `backend/tests/test_ai_structured.py` — `test_empty_message_is_rejected`,
    `test_overlong_message_is_rejected`; `backend/tests/test_openrouter.py` —
    `test_connectivity_endpoint_rejects_overlong_prompt`.
  - **Verification evidence:** all 3 new tests pass (422 for empty/overlong input).

**F11 — No rate limiting on AI endpoints**
- **Affected files:** `backend/app/main.py` (`/api/ai/respond`, `/api/ai/connectivity`)
- **Issue:** Any authenticated session can call these endpoints as fast as the client permits; there is no throttling.
- **Why it matters:** Each call is a real, billed OpenRouter request. For the current single-hardcoded-user local MVP this is low-risk, but it's a gap that needs to be closed before any multi-user or externally-reachable deployment (both explicitly floated as future directions).
- **Recommended action:** Not urgent for the current MVP scope; note it as a prerequisite for any deployment beyond local single-user use.
- **Remediation:** The user asked for every Medium finding to be remediated, so this was implemented
  rather than deferred: an in-memory per-user sliding-window rate limiter
  (`main._enforce_ai_rate_limit`, 20 requests/60s by default) applied to both `/api/ai/respond` and
  `/api/ai/connectivity`, returning HTTP 429 once exceeded. This is process-local (resets on restart,
  not shared across multiple worker processes) — acceptable for the current single-instance local MVP;
  a shared store (e.g. Redis) would be needed for a multi-instance deployment.
  - **Files:** `backend/app/main.py`, `backend/tests/conftest.py` (new — resets the rate-limit state
    between tests, since it is process-global and would otherwise leak across the many tests that call
    these endpoints as the same user).
  - **Tests added:** `backend/tests/test_ai_structured.py::test_ai_respond_is_rate_limited`,
    `backend/tests/test_openrouter.py::test_connectivity_endpoint_is_rate_limited` (both monkeypatch the
    limit down to 2 requests to keep the test fast and deterministic).
  - **Verification evidence:** both new tests pass (3rd request in the window returns 429); the
    `conftest.py` reset fixture was verified necessary — without it, later tests in the same file that
    call these endpoints repeatedly begin failing with spurious 429s purely due to test ordering.

**F12 — Multi-user schema exists but the seeding logic only supports the one hardcoded account**
- **Affected files:** `backend/app/board_store.py` (`_ensure_board_for_user`)
- **Issue:** `_ensure_board_for_user` only seeds `INITIAL_BOARD_DATA` `if user.username == "user"`; any other user row would get a `Board` with zero columns and no code path to populate one (there is also no registration/user-creation endpoint at all currently).
- **Why it matters:** `docs/DATABASE_DESIGN.md` and `AGENTS.md` both frame the schema as multi-user-ready "for future" — this confirms that readiness is schema-only; the seeding/bootstrap logic is hardcoded to a single account and would need rework even to demo a second user.
- **Recommended action:** No action needed for current MVP scope; flag as a real prerequisite (not just a schema check) the day multi-user support is actually scheduled.
- **Remediation:** Removed the `username == "user"` special case; every new user's first board is now
  seeded from `INITIAL_BOARD_DATA`. This surfaced a real, previously-latent bug during remediation:
  `columns.id`/`cards.id` are primary keys unique across the *whole table*, not scoped per board, so
  naively reusing the exact same literal seed ids for a second user collided with the first user's
  existing rows (`UNIQUE constraint failed: columns.id`) — caught immediately by the existing test suite
  (`test_board_ownership_is_isolated_by_user`, `test_foreign_keys_and_cascade_behavior` both failed on
  the first attempt). Fixed with `_seed_board_data_for_user`: it checks whether the canonical
  `INITIAL_BOARD_DATA` ids are already taken and, if so, seeds an equivalent board with every id suffixed
  `-u<user_id>` instead — collision-free, and generic (not tied to any specific username).
  - **Files:** `backend/app/board_store.py`.
  - **Tests added:** `backend/tests/test_board.py::test_new_user_receives_a_populated_seeded_board_not_an_empty_one`
    (creates a second user, confirms they get a fully populated board with the same shape as
    `INITIAL_BOARD_DATA`, and confirms its ids are disjoint from the first user's board).
  - **Verification evidence:** new test passes; both pre-existing tests that exercise a second user
    (`test_board_ownership_is_isolated_by_user`, `test_foreign_keys_and_cascade_behavior`) continue to
    pass after the collision fix.

### Low

**Status: remediated 2026-07-22.** F13–F16 were initially left as-is per each finding's own
"Recommended action" during the first remediation pass; all four were subsequently remediated in the
second pass, per explicit instruction to close out the remaining Low findings.

**F13 — Hardcoded session secret and `https_only=False` default**
- **Affected files:** `backend/app/main.py` (`SessionMiddleware`)
- **Issue:** `SESSION_SECRET` defaults to the literal string `"pm-mvp-dev-session-secret"` if unset, and `https_only=False` is hardcoded (not environment-driven).
- **Why it matters:** Fine for a local single-user Docker MVP; would need to change (a real secret, `https_only=True`) the moment this is exposed beyond localhost.
- **Recommended action:** No change needed now; worth a one-line comment noting these must change before any non-local deployment.
- **Remediation:** Moved to `backend/app/config.py`. `resolve_session_secret(environment, secret)` only
  falls back to the hardcoded development secret when `ENVIRONMENT == "development"` (the default —
  local/test behavior is unchanged with no env vars set); any other `ENVIRONMENT` with no
  `SESSION_SECRET` set raises `SessionSecretConfigurationError` at startup instead of silently running
  insecurely. `SESSION_HTTPS_ONLY` is now an env var (default `false`, unchanged behavior locally;
  settable to `true` behind TLS) instead of a hardcoded `False`. `middleware.py`'s
  `configure_middleware(app)` wires both into `SessionMiddleware`.
  - **Files:** `backend/app/config.py` (new), `backend/app/middleware.py` (new).
  - **Tests added:** `backend/tests/test_config.py` — development fallback, explicit-secret-always-wins,
    non-development-without-secret raises, non-development-with-secret succeeds, and boolean-env-parsing
    coverage for `SESSION_HTTPS_ONLY`.
  - **Verification evidence:** all new tests pass; every existing auth/session test continues to pass
    with zero env vars set (confirming the development fallback preserves current behavior exactly).

**F14 — Frontend card/column id generation uses `Math.random()`**
- **Affected files:** `frontend/src/lib/kanban.ts` (`createId`)
- **Issue:** IDs are `Math.random().toString(36)` plus a timestamp — not cryptographically random.
- **Why it matters:** Purely a display/identity id with no security role today (contrast with the AI path's stricter `^[a-zA-Z0-9_-]{1,64}$`-pattern ids), so this is cosmetic; flagging only because collision probability, while very low, is non-zero under rapid concurrent creation.
- **Recommended action:** No action needed; `crypto.randomUUID()` would be a trivial drop-in if ever revisited.
- **Remediation:** `createId` now returns `` `${prefix}-${crypto.randomUUID()}` ``. Confirmed
  `crypto.randomUUID()` works under both real browsers and the Vitest/jsdom test environment used here.
  - **Files:** `frontend/src/lib/kanban.ts`.
  - **Tests added:** `frontend/src/lib/kanban.test.ts` — asserts the UUID format and that successive
    calls produce distinct ids.
  - **Verification evidence:** new tests pass; `KanbanBoard.test.tsx`'s existing add/remove-card test
    (which exercises `createId` indirectly) continues to pass unmodified.

**F15 — Login page pre-fills the MVP credentials**
- **Affected files:** `frontend/src/app/login/page.tsx`
- **Issue:** The username/password inputs default to `useState("user")` / `useState("password")` — the actual working credentials are visibly pre-populated on page load.
- **Why it matters:** Convenient for local demoing; would hand out credentials immediately if this build were ever shown to anyone outside a trusted local session.
- **Recommended action:** No action needed for current MVP scope; remove the pre-fill before any wider demo/deployment.
- **Remediation:** Both fields now start as `useState("")`. The login flow itself (submit, redirect,
  error handling) is unchanged.
  - **Files:** `frontend/src/app/login/page.tsx`.
  - **Tests added:** `frontend/src/app/login/page.test.tsx` (new) — asserts both fields render empty.
  - **Verification evidence:** new test passes; the Playwright e2e login flow (`kanban.spec.ts`'s
    `login()` helper, which explicitly `.fill()`s both fields regardless of any prefill) continues to
    pass unmodified — confirming no test anywhere depended on the prefilled values.

**F16 — Unused default Next.js template assets not covered by the backend's public-path allowlist**
- **Affected files:** `frontend/public/{file,globe,next,vercel,window}.svg`, `backend/app/main.py` (`_FRONTEND_PUBLIC_PATHS`)
- **Issue:** These boilerplate assets are unreferenced by the current UI and, if requested directly while unauthenticated, would redirect to `/login` rather than 404 or serve — a minor inconsistency, not a functional bug since nothing currently links to them.
- **Why it matters:** Purely tidiness/maintainability; unused files add noise for future readers.
- **Recommended action:** Delete the unused SVGs during the next frontend cleanup pass.
- **Remediation:** Confirmed via `grep` across `frontend/src` and `frontend/tests` that none of the five
  SVGs were referenced anywhere, then deleted all five. `frontend/public/` is now empty (Next.js does
  not require a populated `public/` directory; the favicon is served from `src/app/favicon.ico` via the
  App Router convention, unaffected).
  - **Files:** `frontend/public/file.svg`, `globe.svg`, `next.svg`, `vercel.svg`, `window.svg` (all
    deleted).
  - **Verification evidence:** pre-deletion `grep` found zero references; `npm run build` and the full
    Playwright e2e suite both pass after deletion, confirming nothing depended on these files.

---

## Test results / evidence reviewed

### Before remediation (original review pass)

| Suite | Command | Result | Notes |
|---|---|---|---|
| Backend unit/integration | `pytest backend/tests` (from repo root, scratch SQLite DB) | **44/44 passed** | Run in a prior session this conversation continues from; `pytest` had to be installed manually into `.venv` first (see F7). |
| Frontend unit | `npm run test:unit` (Vitest) | **14/14 passed** | No server required. |
| Frontend e2e | `npm run test:e2e` equivalent, via built static export served by FastAPI + `E2E_BASE_URL` | **8/8 passed** | Required manually building the frontend, copying `frontend/out` into `backend/static`, and running the real backend — the zero-config default does not work (see F4). |
| Frontend e2e (default, no `E2E_BASE_URL`) | `npx playwright test -g "redirects unauthenticated"` | **1/1 failed** | Reproduced this session specifically to verify F4; test-results artifacts generated during this check were discarded and `git status` confirmed clean afterward. |
| Frontend lint | `npm run lint` | **2 errors** | `react/no-unescaped-entities` in `AiChatSidebar.tsx:105` (F8). |
| Static analysis | `grep` for `bcrypt\|passlib\|argon2\|hashlib`, `git ls-files backend/data`, search for CI config (`*.yml`/`*.yaml`) | No hashing library found; no DB files tracked in git (good); no CI configuration anywhere in the repo | Supports F6 and F7. |

### After remediation (2026-07-21)

All runs used a scratch/temp SQLite database (`DATABASE_URL` pointed at the OS temp directory, or the
build/serve scripts' auto-generated scratch DB) — `backend/data/kanban.db` was never touched (confirmed
via its filesystem last-write-time, unchanged from before this remediation work began).

| Suite | Command | Result | Notes |
|---|---|---|---|
| Backend unit/integration | `pytest backend/tests` (scratch SQLite DB, deps from `requirements-dev.txt`) | **62/62 passed** | 44 original + 18 new tests across F1, F2/F6, F5, F10, F11, F12. |
| Frontend unit | `npm run test:unit` (Vitest) | **15/15 passed** | 14 original + 1 new (F3 failed-save/revert test). |
| Frontend lint | `npm run lint` | **0 errors** | F8 fixed; clean exit code 0. |
| Frontend production build | `npm run build` (`next build`) | **Success** | Includes full TypeScript check; confirms `KanbanBoard.tsx`'s new save-error handling compiles cleanly. |
| Frontend e2e (fixed default workflow) | `npm run test:e2e`, **no** `E2E_BASE_URL` set | **8/8 passed** | This is the direct regression check for F4: builds the frontend, serves it through the real backend on a scratch DB, runs the full suite, tears down automatically. Backend process confirmed stopped and `backend/static` confirmed removed afterward. |
| F4 regression (targeted) | `npm run test:e2e -- -g "redirects unauthenticated"`, no `E2E_BASE_URL` | **1/1 passed** | The exact test that failed in the original review's reproduction now passes through the new default workflow. |
| F1 regression (targeted) | `backend/tests/test_schema_migrations.py` | **3/3 passed** | Includes the direct non-destructiveness proof: a pre-Alembic database with a real row survives `_ensure_schema()` unchanged. |

### After second remediation pass (2026-07-22): F13–F16 + `main.py` refactor

Same scratch-database discipline as above; `backend/data/kanban.db`'s last-write-time was re-confirmed
unchanged at the end of this pass too.

| Suite | Command | Result | Notes |
|---|---|---|---|
| Backend unit/integration | `pytest backend/tests` (scratch SQLite DB) | **80/80 passed** | 62 from the first pass + 18 new: `test_config.py` (F13) and `test_app_structure.py` (refactor route/ordering checks). |
| Frontend unit | `npm run test:unit` (Vitest) | **18/18 passed** | 15 from the first pass + 3 new: 2 `createId` tests (F14), 1 login-page empty-fields test (F15). |
| Frontend lint | `npm run lint` | **0 errors** | |
| Frontend production build | `npm run build` (`next build`) | **Success** | Confirms the F16 asset deletion and F15 login-page change don't break the build. |
| Frontend e2e (fixed default workflow) | `npm run test:e2e`, no `E2E_BASE_URL` | **8/8 passed** | Full suite green after the `main.py` refactor and all F13–F16 changes — including the login flow with no prefilled credentials, and the AI endpoints behind their (unmoved-in-behavior) rate limiter. |
| Refactor route sanity check | Direct import of `backend.app.main.app`, print `app.routes` | All 14 expected routes present, correct methods, catch-all last | Run once immediately after the refactor, before the full test suite, specifically to catch route-ordering mistakes early. |
| Refactor regression (targeted) | `backend/tests/test_app_structure.py` | **3/3 passed** | Included in the 80 above; directly asserts route registration, catch-all-is-last ordering, and router/module separation. |
| F13 regression (targeted) | `backend/tests/test_config.py` | **11/11 passed** | Included in the 80 above. |

---

## Prioritized action plan

Original plan (pre-remediation), kept for history — see the **Remediation** block under each finding
above, and "Remediation status" near the top of this document, for what was actually done and how it
was verified:

1. **F1 (Critical):** Before any further schema work, add a real migration tool or replace the silent `drop_all` with a hard startup failure. This is the one item that can destroy real user data with a routine, well-intentioned change. — **Done: Alembic adopted.**
2. **F4 + F9 (High):** Fix or clearly document the e2e/dev workflow gap — either wire a dev proxy so `npm run dev` + `npm run test:e2e` work zero-config, or update `frontend/README.md`/`AGENTS.md` with the actual required steps (build + serve via backend + `E2E_BASE_URL`). This directly affects every future contributor's first experience with the repo. — **Done: build+serve orchestration scripts; CORS removed.**
3. **F3 (High):** Add minimal error handling (`response.ok` check + user-visible failure state) to `persistBoard` in `KanbanBoard.tsx`. Small, contained change with an outsized reliability payoff. — **Done.**
4. **F5 (High):** Add referential-integrity validation to the board-save path (`save_board` or a Pydantic validator on `BoardData`) so malformed payloads produce a clean 422 instead of silent data loss or an unhandled 500. — **Done.**
5. **F2 + F6 (High/Medium, do together):** Add a hashing library and hash passwords at creation/auth time, or at minimum rename `password_hash` to reflect current reality and note the accepted tradeoff explicitly in code and docs. — **Done: bcrypt hashing.**
6. **F7 (Medium):** Pin `pytest` in a dev-requirements file; consider a minimal CI workflow — this is cheap and would have caught F4 and F8 automatically going forward. — **Done: `requirements-dev.txt` added. CI workflow itself remains a follow-up, not implemented (no CI existed before or after this pass).**
7. **F8 (Medium):** One-line fix — escape the quotes in `AiChatSidebar.tsx:105`. — **Done.**
8. **F10 (Medium):** Add `max_length` to the AI request/prompt fields for consistency with `ConversationTurn`. — **Done.**
9. **F11, F12 (Medium):** Originally scoped as "no immediate action" for the current MVP, but remediated
   anyway per explicit instruction to close every Medium finding — **Done: rate limiting added (F11);
   multi-user seeding fixed, including a real id-collision bug this surfaced (F12).**
10. **F13, F14, F15, F16 (Low):** Originally left as-is (Critical/High/Medium-only scope for the first
    pass); remediated in the second pass on 2026-07-22 — **Done: env-driven session secret with a
    development-only fallback + configurable HTTPS-only cookies (F13); `crypto.randomUUID()` (F14); no
    prefilled login credentials (F15); unused SVGs deleted (F16).**

No findings remain open as of 2026-07-22. `backend/app/main.py` was also refactored into a package
(`config.py`, `middleware.py`, `dependencies.py`, `routers/`) in the same pass — not itself a finding,
but done because F13's fix and the growing route count made a good moment to separate concerns; see
"Remediation status" at the top of this document.

---

## Follow-up review (2026-07-23): clean pass, no new findings

**Date:** 2026-07-23
**Scope:** Full repository re-scan, independent of the diff (the branch had no code changes since the
2026-07-22 remediation — working tree was clean apart from a stale `test-results/.last-run.json`
artifact). Goal was to check for anything new or regressed, not to re-litigate F1–F16.
**Method:** Manual read of every backend (`backend/app/**/*.py`) and frontend
(`frontend/src/**/*.{ts,tsx}`) application source file — `config.py`, `middleware.py`, `dependencies.py`,
`board_store.py`, `structured_output.py`, `openrouter_service.py`, `main.py`, all five routers (`auth`,
`board`, `ai`, `health`, `frontend`), `KanbanBoard.tsx`, `AiChatSidebar.tsx`, `kanban.ts`,
`login/page.tsx`, and the `Dockerfile` — plus a repo-wide grep for `eval`, `exec`, `subprocess`,
`os.system`, `pickle`, `yaml.load`, `innerHTML`, `dangerouslySetInnerHTML`, and `shell=True` (zero hits).
Full test suites were also re-run to confirm no regression: `pytest backend/tests` (80/80), `npm run
lint` (0 errors), `npm run test:unit` (18/18), `npm run test:e2e` (8/8, full build+serve workflow). No
application code was modified.

**Result: no HIGH or MEDIUM confidence findings.** Specifically checked and ruled out:

- **Path traversal** (`routers/frontend.py:_resolve_static_file`) — still correctly resolves and
  containment-checks against `STATIC_DIR` before serving.
- **SQL injection** — all queries go through the SQLAlchemy ORM with bound parameters; no raw SQL
  anywhere.
- **Auth/session integrity** — `password_hash` remains genuine bcrypt; session `user_id` is server-side
  and cookie-signed, never client-supplied; every board/AI route resolves ownership from the session,
  not the request payload — no IDOR path found.
- **AI structured-output injection** — operations remain strictly validated (`extra="forbid"`,
  length/pattern-bounded fields) against the live board snapshot before any DB write; no eval/
  deserialization of model output.
- **XSS** — no `dangerouslySetInnerHTML` anywhere in the frontend; all user- and AI-derived text renders
  through normal JSX text nodes.
- **SSRF** — `openrouter_service.py` posts only to a hardcoded OpenRouter URL; no user-controlled
  host/protocol.
- **Open redirect** — both redirect call sites in `frontend.py` target fixed constants, never a
  user-supplied URL.
- **CORS/CSRF surface** — no CORS middleware (same-origin only); `SameSite=Lax` cookies, unchanged from
  F9/F13.
- **Secrets/config handling** — `SESSION_SECRET` still refuses to start in non-development environments
  without an explicit secret (F13 remediation intact).
- **Docker/build** — no shell interpolation of untrusted input in the `Dockerfile`.

**Conclusion:** the 2026-07-22 remediation (F1–F16) holds with no regressions; this independent full-repo
pass found nothing new to add to the findings list above.
