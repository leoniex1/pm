import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { KanbanBoard } from "@/components/KanbanBoard";
import { initialData } from "@/lib/kanban";

const getFirstColumn = () => screen.getAllByTestId(/column-/i)[0];

describe("KanbanBoard", () => {
  let boardState: typeof initialData;

  beforeEach(() => {
    boardState = structuredClone(initialData);

    global.fetch = vi.fn(async (input: string | URL, init?: RequestInit) => {
      if (typeof input === "string" && input === "/api/board" && !init?.method) {
        return new Response(JSON.stringify(boardState), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (typeof input === "string" && input === "/api/board" && init?.method === "PUT") {
        boardState = JSON.parse(String(init.body));
        return new Response(JSON.stringify(boardState), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (typeof input === "string" && input === "/api/ai/respond" && init?.method === "POST") {
        const payload = JSON.parse(String(init.body)) as { message: string };

        if (payload.message === "chat-only") {
          return new Response(
            JSON.stringify({
              assistant_message: "Chat response",
              operations: [],
              board: boardState,
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }
          );
        }

        if (payload.message === "apply-change") {
          const aiCardId = "ai-card-test";
          boardState = {
            ...boardState,
            cards: {
              ...boardState.cards,
              [aiCardId]: {
                id: aiCardId,
                title: "AI created card",
                details: "Created by assistant",
              },
            },
            columns: boardState.columns.map((column) =>
              column.id === "col-backlog"
                ? { ...column, cardIds: [aiCardId, ...column.cardIds] }
                : column
            ),
          };

          return new Response(
            JSON.stringify({
              assistant_message: "Applied one change",
              operations: [{ id: "op-1", type: "create_card" }],
              board: boardState,
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            }
          );
        }

        if (payload.message === "error-case") {
          return new Response(
            JSON.stringify({ detail: "AI request failed." }),
            {
              status: 500,
              headers: { "Content-Type": "application/json" },
            }
          );
        }

        return new Response(
          JSON.stringify({
            assistant_message: "Default",
            operations: [],
            board: boardState,
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }
        );
      }

      throw new Error("Unexpected fetch call");
    }) as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders five columns", async () => {
    render(<KanbanBoard />);
    await screen.findByDisplayValue("Backlog");
    expect(screen.getAllByTestId(/column-/i)).toHaveLength(5);
  });

  it("renames a column", async () => {
    render(<KanbanBoard />);
    await screen.findByDisplayValue("Backlog");
    const column = getFirstColumn();
    const input = within(column).getByLabelText("Column title");
    await userEvent.clear(input);
    await userEvent.type(input, "New Name");
    expect(input).toHaveValue("New Name");
  });

  it("adds and removes a card", async () => {
    render(<KanbanBoard />);
    await screen.findByDisplayValue("Backlog");
    const column = getFirstColumn();
    const addButton = within(column).getByRole("button", {
      name: /add a card/i,
    });
    await userEvent.click(addButton);

    const titleInput = within(column).getByPlaceholderText(/card title/i);
    await userEvent.type(titleInput, "New card");
    const detailsInput = within(column).getByPlaceholderText(/details/i);
    await userEvent.type(detailsInput, "Notes");

    await userEvent.click(within(column).getByRole("button", { name: /add card/i }));

    expect(within(column).getByText("New card")).toBeInTheDocument();

    const deleteButton = within(column).getByRole("button", {
      name: /delete new card/i,
    });
    await userEvent.click(deleteButton);

    expect(within(column).queryByText("New card")).not.toBeInTheDocument();
  });

  it("shows sidebar and sends chat-only message without board refresh", async () => {
    render(<KanbanBoard />);
    await screen.findByDisplayValue("Backlog");

    const initialGetCalls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      ([url, init]) => url === "/api/board" && !init?.method
    ).length;

    await userEvent.type(screen.getByTestId("ai-input"), "chat-only");
    await userEvent.click(screen.getByTestId("ai-send"));

    expect(await screen.findByText("Chat response")).toBeInTheDocument();

    const getCallsAfter = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.filter(
      ([url, init]) => url === "/api/board" && !init?.method
    ).length;
    expect(getCallsAfter).toBe(initialGetCalls);
  });

  it("refreshes board after AI mutation and renders created card", async () => {
    render(<KanbanBoard />);
    await screen.findByDisplayValue("Backlog");

    await userEvent.type(screen.getByTestId("ai-input"), "apply-change");
    await userEvent.click(screen.getByTestId("ai-send"));

    expect(await screen.findByText("Applied one change")).toBeInTheDocument();

    const backlog = screen.getByTestId("column-col-backlog");
    expect(within(backlog).getByText("AI created card")).toBeInTheDocument();
  });

  it("shows AI error state on failed response", async () => {
    render(<KanbanBoard />);
    await screen.findByDisplayValue("Backlog");

    await userEvent.type(screen.getByTestId("ai-input"), "error-case");
    await userEvent.click(screen.getByTestId("ai-send"));

    expect(await screen.findByTestId("ai-error")).toHaveTextContent("AI request failed.");
  });
});
