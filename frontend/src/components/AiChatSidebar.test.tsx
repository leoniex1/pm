import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AiChatSidebar, type ChatMessage } from "@/components/AiChatSidebar";

describe("AiChatSidebar", () => {
  it("renders sidebar and empty state", () => {
    render(
      <AiChatSidebar
        onSend={async () => ({ assistantMessage: "ok", operationsCount: 0 })}
      />
    );

    expect(screen.getByTestId("ai-chat-sidebar")).toBeInTheDocument();
    expect(screen.getByTestId("ai-empty-state")).toBeInTheDocument();
  });

  it("lets user type and send a message", async () => {
    const onSend = vi.fn(async () => ({ assistantMessage: "Hello", operationsCount: 0 }));
    render(<AiChatSidebar onSend={onSend} />);

    await userEvent.type(screen.getByTestId("ai-input"), "Hi AI");
    await userEvent.click(screen.getByTestId("ai-send"));

    expect(onSend).toHaveBeenCalledWith("Hi AI", [
      { role: "user", message: "Hi AI" } as ChatMessage,
    ]);
    expect(await screen.findByText("Hello")).toBeInTheDocument();
  });

  it("sends on Enter and inserts newline on Shift+Enter", async () => {
    const onSend = vi.fn(async () => ({ assistantMessage: "Done", operationsCount: 0 }));
    render(<AiChatSidebar onSend={onSend} />);

    const input = screen.getByTestId("ai-input");
    await userEvent.type(input, "Line one");
    await userEvent.keyboard("{Shift>}{Enter}{/Shift}");
    await userEvent.type(input, "Line two");

    expect(input).toHaveValue("Line one\nLine two");

    await userEvent.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("Line one\nLine two", [
      { role: "user", message: "Line one\nLine two" } as ChatMessage,
    ]);
  });

  it("disables send while pending and shows loading", async () => {
    let resolver: ((value: { assistantMessage: string; operationsCount: number }) => void) | null = null;
    const onSend = vi.fn(
      () =>
        new Promise<{ assistantMessage: string; operationsCount: number }>((resolve) => {
          resolver = resolve;
        })
    );

    render(<AiChatSidebar onSend={onSend} />);

    await userEvent.type(screen.getByTestId("ai-input"), "pending test");
    await userEvent.click(screen.getByTestId("ai-send"));

    expect(screen.getByTestId("ai-send")).toBeDisabled();
    expect(screen.getByTestId("ai-loading")).toBeInTheDocument();

    resolver?.({ assistantMessage: "Done", operationsCount: 0 });
    expect(await screen.findByText("Done")).toBeInTheDocument();
  });

  it("shows error for failed request", async () => {
    const onSend = vi.fn(async () => {
      throw new Error("AI request failed");
    });

    render(<AiChatSidebar onSend={onSend} />);

    await userEvent.type(screen.getByTestId("ai-input"), "trigger error");
    await userEvent.click(screen.getByTestId("ai-send"));

    expect(await screen.findByTestId("ai-error")).toHaveTextContent("AI request failed");
  });
});
