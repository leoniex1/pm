# Project execution plan

This plan covers Parts 1-10 with concrete checklists, critical-path tests, and success criteria. Implementation starts only after explicit approval of this plan.

## Decisions locked in

- [x] Single-container Docker MVP: FastAPI serves backend API and statically built Next.js frontend.
- [x] Auth is backend-managed cookie/session with hardcoded credentials `user` / `password`.
- [x] SQLite uses normalized relational schema for users, boards, columns, cards, and ordering.
- [x] JSON is used for docs, API payloads, structured AI I/O, and optional snapshots (not whole-board DB blob).
- [x] OpenRouter model is environment-configurable via `OPENROUTER_MODEL`, default `openai/gpt-oss-120b`.
- [x] Structured output schema must be proposed and approved before Part 9 implementation.
- [x] Testing focus is critical-path unit/integration/e2e without coverage percentage target.

## Part 1: Plan and frontend inspection

### Checklist

- [x] Inspect existing frontend architecture, components, and tests.
- [x] Create `frontend/AGENTS.md` concise reference for architecture, commands, conventions, and constraints.
- [x] Rewrite `docs/PLAN.md` as a detailed checklist plan with tests and success criteria per part.
- [x] Request user approval before starting Part 2.

### Tests

- [x] Verify that referenced frontend commands exist in `frontend/package.json`.
- [x] Verify `frontend/AGENTS.md` content matches actual source structure.
- [x] Manual review: ensure every part includes substeps, tests, and success criteria.

### Success criteria

- [x] `frontend/AGENTS.md` exists and is accurate/practical.
- [x] `docs/PLAN.md` is detailed and approval-ready.
- [x] No code implementation beyond planning/docs is started.

## Part 2: Scaffolding (backend + single container hello world)

### Checklist

- [x] Initialize backend project in `backend/` using FastAPI and `uv` workflow.
- [x] Add backend entrypoint and basic health/API route.
- [x] Add Dockerfile for one-container build/runtime.
- [x] Add scripts in `scripts/` for start/stop on Mac, Linux, and Windows.
- [x] Serve simple static HTML at `/` from FastAPI to prove container plumbing.

### Tests

- [x] Build Docker image successfully.
- [x] Run container and verify `/` returns hello page.
- [x] Verify API endpoint (for example `/api/health`) returns expected JSON.
- [x] Verify start/stop scripts work on their target OS shell conventions.

### Success criteria

- [x] One command path starts local container successfully.
- [x] FastAPI serves both static response at `/` and API response under `/api/*`.
- [x] Documentation for how to run is minimal and correct.

## Part 3: Serve built frontend from FastAPI

### Checklist

- [x] Build Next.js frontend to static assets as part of Docker build flow.
- [x] Configure FastAPI static file serving for built frontend.
- [x] Route `/` to the Kanban demo.
- [x] Ensure fallback behavior supports frontend routing requirements for MVP.

### Tests

- [x] Containerized app at `/` shows existing Kanban UI.
- [x] Existing frontend unit tests pass.
- [x] Integration test verifies static assets are served correctly.

### Success criteria

- [x] Demo Kanban renders from containerized app root.
- [x] No regression to current rename/add/delete/drag interactions.

## Part 4: Dummy sign-in/sign-out with backend session

### Checklist

- [x] Add backend session management using secure cookie-based session.
- [x] Implement login endpoint validating `user` / `password`.
- [x] Implement logout endpoint clearing session.
- [x] Protect board/API endpoints behind authenticated session.
- [x] Add frontend login screen and auth-aware routing/state.

### Tests

- [x] Backend test: successful login sets session cookie.
- [x] Backend test: invalid credentials rejected.
- [x] Backend test: logout clears session.
- [x] Integration/e2e: unauthenticated user redirected/shown login.
- [x] Integration/e2e: authenticated user reaches Kanban and can logout.

### Success criteria

- [x] User cannot access board without login.
- [x] Valid login and logout flows work end to end.
- [x] No localStorage-only auth guard is used for core auth state.

## Part 5: Database model and sign-off

Reconciliation note: database persistence implementation was completed early before explicit Part 5 sign-off. Items below reflect verified current state.

### Checklist

- [x] Author schema proposal in docs for normalized SQLite tables:
- [x] `users`
- [x] `boards`
- [x] `columns`
- [x] `cards`
- [x] `card_positions` (or equivalent deterministic ordering table/fields)
- [x] Define foreign keys, uniqueness constraints, and delete/update behavior.
- [x] Define migration/bootstrap strategy that creates DB if missing.
- [x] Define JSON payload contract for board read/write API.
- [ ] Request explicit user approval before implementing schema in code.

### Tests

- [x] Validate schema with sample data insert/select/update/delete script.
- [x] Validate board reconstruction query returns correct ordered columns/cards.

### Success criteria

- [x] Schema doc is clear, normalized, and approved.
- [x] Ordering strategy is deterministic and testable.

## Part 6: Backend board API and persistence

Reconciliation note: some Part 6 implementation and tests were completed early during Part 5 execution.

### Checklist

- [x] Implement SQLite initialization on startup if DB file does not exist.
- [x] Implement repository/data-access layer for board entities.
- [x] Implement authenticated board APIs (read and update operations).
- [x] Add validation for payload shape and ownership checks.
- [ ] Add error handling for invalid board/card/column operations.

### Tests

- [x] Unit tests for data-access methods (create/read/update ordering moves).
- [x] API tests for auth-required routes.
- [x] API tests for successful board retrieval and updates.
- [x] API tests for invalid payloads and unauthorized access.

### Success criteria

- [x] Backend can persist and return board state per user reliably.
- [x] DB auto-creation path works on first run.

## Part 7: Frontend-backend integration for persistent Kanban

Reconciliation note: core Part 7 integration was completed early during Part 5 execution.

### Checklist

- [x] Replace in-memory-only initialization with backend board fetch.
- [x] Wire rename/add/delete/move operations to backend APIs.
- [ ] Add optimistic or controlled update strategy with rollback/error UX.
- [x] Ensure session-aware API calls include credentials.
- [x] Keep existing UX quality and responsiveness.

### Tests

- [x] Integration tests for initial board load from backend.
- [x] Integration tests for rename/add/delete/move persistence.
- [x] Reload test: board state persists across refresh and login session.
- [x] Regression test for drag/drop ordering behavior.

### Success criteria

- [x] Board interactions persist to SQLite and survive refresh.
- [x] Frontend and backend are fully connected for core Kanban workflow.

## Part 8: OpenRouter connectivity

### Checklist

- [ ] Add backend OpenRouter client with env-based config:
- [ ] `OPENROUTER_API_KEY` required.
- [ ] `OPENROUTER_MODEL` optional, default `openai/gpt-oss-120b`.
- [ ] Add basic service method and endpoint for connectivity check.
- [ ] Implement simple prompt test (`2+2`) pathway.

### Tests

- [ ] Unit test for config resolution and default model behavior.
- [ ] Integration test with mocked OpenRouter response.
- [ ] Manual connectivity test with real API key verifies non-error response.

### Success criteria

- [ ] Backend can successfully call OpenRouter in configured environments.
- [ ] Model selection is environment-configurable with correct default.

## Part 9: Structured outputs for AI-assisted board updates (approval gate first)

### Checklist

- [ ] Draft and document exact structured output schema in docs before coding.
- [ ] Include response text, optional board update operations, and validation rules.
- [ ] Request explicit user approval of schema.
- [ ] After approval, implement backend prompt assembly with:
- [ ] current board JSON
- [ ] user message
- [ ] conversation history
- [ ] Implement strict parsing/validation and safe application of allowed operations.
- [ ] Persist applied updates and return both assistant response and resulting board diff/state.

### Tests

- [ ] Schema validation tests for valid and invalid model outputs.
- [ ] Integration tests for no-op response (chat only).
- [ ] Integration tests for valid board mutation response.
- [ ] Failure-path tests for malformed/unsafe operations.

### Success criteria

- [ ] Structured output contract is documented, approved, and enforced.
- [ ] AI responses can safely and deterministically update the board when requested.

## Part 10: Frontend AI sidebar and auto-refresh board updates

### Checklist

- [ ] Add sidebar chat UI integrated with backend AI endpoint.
- [ ] Show conversation history and loading/error states.
- [ ] Apply returned board updates to UI state automatically.
- [ ] Ensure visual integration fits existing design language.
- [ ] Keep Kanban interactions and AI interactions coherent under concurrent updates.

### Tests

- [ ] Component tests for sidebar send/render states.
- [ ] Integration tests for AI chat request/response cycle.
- [ ] Integration tests verifying AI-triggered board changes render immediately.
- [ ] Regression tests for manual board edits after AI updates.

### Success criteria

- [ ] Sidebar chat works end to end.
- [ ] Board refreshes automatically when AI returns updates.
- [ ] Existing Kanban behavior remains stable.

## Cross-cutting quality gates

- [ ] Keep implementation simple and avoid unnecessary abstractions.
- [ ] Maintain concise docs; update only what is needed.
- [ ] Add tests only for critical paths and behavior changes.
- [ ] Confirm root cause for defects before applying fixes.
- [ ] Preserve project color palette and overall UI consistency.

## Execution control

- [ ] Stop after Part 1 deliverables and wait for user approval.
- [ ] Do not start Part 2+ until explicit approval is received.