# Frontend Agent Reference

## Scope

This frontend is a Next.js app (App Router) that currently runs as a client-side Kanban demo. It is the starting point to be integrated into the FastAPI backend and Docker flow.

## Current structure

- `src/app/layout.tsx`: Root HTML layout and global metadata/font wiring.
- `src/app/page.tsx`: Home route; renders `KanbanBoard`.
- `src/app/login/page.tsx`: Login form. Username/password fields start empty (no prefilled credentials).
- `src/app/globals.css`: Global styles and color tokens.
- `src/components/KanbanBoard.tsx`: Main board state container and drag/drop orchestration.
- `src/components/AiChatSidebar.tsx`: AI chat sidebar UI, local chat history, send/loading/error states.
- `src/components/KanbanColumn.tsx`: Column rendering, title editing, card list, add form.
- `src/components/KanbanCard.tsx`: Sortable card UI and delete action.
- `src/components/KanbanCardPreview.tsx`: Drag overlay preview.
- `src/components/NewCardForm.tsx`: Inline add-card form with simple validation.
- `src/lib/kanban.ts`: Board types, seed data, card movement logic, id helper (`createId` uses `crypto.randomUUID()`).
- `src/components/KanbanBoard.test.tsx`: Component-level interaction tests, including failed-save error/revert behavior.
- `src/components/AiChatSidebar.test.tsx`: Component tests for chat input, pending state, and error rendering.
- `src/lib/kanban.test.ts`: Unit tests for board movement logic and id generation.
- `src/app/login/page.test.tsx`: Confirms the login form has no prefilled credentials.
- `tests/kanban.spec.ts`: Playwright e2e test entry point.
- `scripts/full-stack.mjs`, `scripts/e2e.mjs`, `scripts/serve.mjs`: build+serve orchestration for e2e/local full-stack dev (see "Build, run, and test scripts").

## Architecture and state

- `KanbanBoard` owns board state and loads/persists it through backend APIs.
- `AiChatSidebar` owns in-memory chat history for the current page session.
- Board shape:
  - `columns: Column[]` where each column stores ordered `cardIds`.
  - `cards: Record<string, Card>` keyed by id.
- Drag/drop is implemented with `@dnd-kit`:
  - `DndContext` in `KanbanBoard`.
  - `useDroppable` in columns.
  - `useSortable` in cards.
  - `moveCard` in `src/lib/kanban.ts` is the core reorder/move function.
- Column renaming, card create, card delete, and card move are reflected immediately in UI and then persisted through backend APIs.
- Auth is session cookie based; frontend API calls are sent with credentials.
- Board data is fetched from `GET /api/board` and persisted with `PUT /api/board`. `persistBoard`
  applies the change optimistically, then checks the response: on failure (non-OK status or a network
  error) it reverts to the previous board state and shows an error banner
  (`data-testid="board-save-error"`) rather than silently diverging from what's actually persisted.
- AI chat uses `POST /api/ai/respond` with `{ message, history }` and triggers board reload when operations are returned.

## Important components and responsibilities

- `KanbanBoard`
  - Handles `onDragStart`/`onDragEnd` and active drag overlay state.
  - Persists rename/add/delete/move operations through backend API calls.
  - Wires AI sidebar send handler and reloads board after AI mutations.
- `AiChatSidebar`
  - Renders in-session chat transcript and no-changes/change count signal.
  - Handles Enter-to-send and Shift+Enter newline behavior.
  - Renders pending and server-error states from `/api/ai/respond`.
- `KanbanColumn`
  - Displays editable title input and card count.
  - Binds add/delete callbacks to column-specific actions.
- `NewCardForm`
  - Enforces non-empty title.
  - Resets/collapses after successful add.
- `moveCard` utility
  - Supports intra-column reorder and inter-column moves.
  - Supports dropping onto a column to append at end.

## Build, run, and test scripts

Run from `frontend/` (these map directly to `package.json` scripts):

```bash
npm run dev
npm run dev:full
npm run build
npm run start
npm run lint
npm run test:unit
npm run test:e2e
npm run test:e2e:raw
npm run test:all
```

Install dependencies once before running scripts:

```bash
npm install
```

`npm run dev` only starts the Next.js dev server. It has no backend behind it — every frontend fetch
call uses a relative path, so `/api/*` calls (including the login/auth-redirect flow) do not resolve to
anything in that mode. It's the right choice for pure UI/styling work; it is not a full-stack dev server.

For anything that needs the real API:

- `npm run dev:full` (`scripts/serve.mjs`) builds the frontend, copies it into `backend/static/`, and
  runs the real FastAPI backend on a scratch SQLite database (never `backend/data/kanban.db`) — use
  this for manual local full-stack testing without Docker.
- `npm run test:e2e` (`scripts/e2e.mjs`) does the same build+serve, runs the full Playwright suite
  against it, and always tears the backend down afterward (success or failure). This is the fix for a
  previously broken default: Playwright's own `webServer` config (see `playwright.config.ts`) only knows
  how to start a bare `next dev`, which cannot pass a single test that touches `/api/*` or the
  unauthenticated-redirect behavior (that logic lives only in the FastAPI backend). If `E2E_BASE_URL` is
  already set (e.g. pointing at a Docker container), `scripts/e2e.mjs` skips all of that and just runs
  Playwright directly — `npm run test:e2e:raw` does the same without the env-var check, for when you
  want to invoke Playwright directly against whatever is already running.

## Coding conventions

- TypeScript-first; keep explicit types for board entities and component props.
- Prefer small pure helpers in `src/lib` for business logic and testability.
- Keep state updates immutable and localized in the board container.
- Keep UI components focused on rendering and event forwarding.
- Write or update tests when behavior changes (unit for pure logic, component tests for UI behavior).

## Constraints and integration notes

- Preserve baseline board UX (rename, add, delete, drag/drop) while integrating API-backed persistence.
- Keep AI chat history in memory only (no persisted transcript for MVP).
- AI failures from strict structured parsing are expected to surface as user-visible error text; board state must remain stable.
- Keep color tokens aligned with project palette in `src/app/globals.css`.
- Frontend is statically built and served by FastAPI from the same container.
