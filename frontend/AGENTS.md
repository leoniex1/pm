# Frontend Agent Reference

## Scope

This frontend is a Next.js app (App Router) that currently runs as a client-side Kanban demo. It is the starting point to be integrated into the FastAPI backend and Docker flow.

## Current structure

- `src/app/layout.tsx`: Root HTML layout and global metadata/font wiring.
- `src/app/page.tsx`: Home route; renders `KanbanBoard`.
- `src/app/globals.css`: Global styles and color tokens.
- `src/components/KanbanBoard.tsx`: Main board state container and drag/drop orchestration.
- `src/components/AiChatSidebar.tsx`: AI chat sidebar UI, local chat history, send/loading/error states.
- `src/components/KanbanColumn.tsx`: Column rendering, title editing, card list, add form.
- `src/components/KanbanCard.tsx`: Sortable card UI and delete action.
- `src/components/KanbanCardPreview.tsx`: Drag overlay preview.
- `src/components/NewCardForm.tsx`: Inline add-card form with simple validation.
- `src/lib/kanban.ts`: Board types, seed data, card movement logic, id helper.
- `src/components/KanbanBoard.test.tsx`: Component-level interaction tests.
- `src/components/AiChatSidebar.test.tsx`: Component tests for chat input, pending state, and error rendering.
- `src/lib/kanban.test.ts`: Unit tests for board movement logic.
- `tests/kanban.spec.ts`: Playwright e2e test entry point.

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
- Board data is fetched from `GET /api/board` and persisted with `PUT /api/board`.
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
npm run build
npm run start
npm run lint
npm run test:unit
npm run test:e2e
npm run test:all
```

Install dependencies once before running scripts:

```bash
npm install
```

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
