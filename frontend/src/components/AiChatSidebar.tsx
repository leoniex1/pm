"use client";

import { useMemo, useState } from "react";

export type ChatRole = "user" | "assistant";

export type ChatMessage = {
  role: ChatRole;
  message: string;
};

type SendResult = {
  assistantMessage: string;
  operationsCount: number;
};

type AiChatSidebarProps = {
  onSend: (message: string, history: ChatMessage[]) => Promise<SendResult>;
};

export const AiChatSidebar = ({ onSend }: AiChatSidebarProps) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastOperationCount, setLastOperationCount] = useState<number | null>(null);

  const canSend = useMemo(() => !isPending && draft.trim().length > 0, [draft, isPending]);

  const handleSend = async () => {
    const trimmed = draft.trim();
    if (!trimmed || isPending) {
      return;
    }

    const nextUserMessage: ChatMessage = { role: "user", message: trimmed };
    const history = [...messages, nextUserMessage];

    setMessages(history);
    setDraft("");
    setError(null);
    setIsPending(true);

    try {
      const result = await onSend(trimmed, history);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", message: result.assistantMessage },
      ]);
      setLastOperationCount(result.operationsCount);
    } catch (sendError) {
      const message =
        sendError instanceof Error
          ? sendError.message
          : "AI request failed. Please try again.";
      setError(message);
    } finally {
      setIsPending(false);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  return (
    <aside
      className="flex min-h-[420px] flex-col rounded-3xl border border-[var(--stroke)] bg-white/90 p-4 shadow-[var(--shadow)]"
      data-testid="ai-chat-sidebar"
    >
      <div className="flex items-center justify-between gap-3 border-b border-[var(--stroke)] pb-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--gray-text)]">
            AI Assistant
          </p>
          <h2 className="mt-1 font-display text-lg font-semibold text-[var(--navy-dark)]">
            Board Chat
          </h2>
        </div>
        {lastOperationCount !== null ? (
          <span
            className="rounded-full border border-[var(--stroke)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--secondary-purple)]"
            data-testid="ai-operation-count"
          >
            {lastOperationCount > 0
              ? `${lastOperationCount} change${lastOperationCount === 1 ? "" : "s"}`
              : "No changes"}
          </span>
        ) : null}
      </div>

      <div
        className="mt-4 flex flex-1 flex-col gap-3 overflow-y-auto pr-1"
        data-testid="ai-message-list"
      >
        {messages.length === 0 ? (
          <div
            className="rounded-2xl border border-dashed border-[var(--stroke)] bg-[var(--surface)] p-4 text-sm leading-6 text-[var(--gray-text)]"
            data-testid="ai-empty-state"
          >
            Ask the AI to summarize your board or make a safe change. Example:
            &ldquo;Create a card in Backlog.&rdquo;
          </div>
        ) : null}

        {messages.map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={
              message.role === "user"
                ? "ml-6 rounded-2xl bg-[var(--primary-blue)] px-4 py-3 text-sm leading-6 text-white"
                : "mr-6 rounded-2xl border border-[var(--stroke)] bg-[var(--surface)] px-4 py-3 text-sm leading-6 text-[var(--navy-dark)]"
            }
            data-testid={`ai-message-${message.role}`}
          >
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] opacity-75">
              {message.role === "user" ? "You" : "Assistant"}
            </p>
            <p className="whitespace-pre-wrap break-words">{message.message}</p>
          </div>
        ))}

        {isPending ? (
          <div
            className="mr-6 rounded-2xl border border-[var(--stroke)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--gray-text)]"
            data-testid="ai-loading"
          >
            Thinking...
          </div>
        ) : null}
      </div>

      {error ? (
        <div
          className="mt-3 rounded-2xl border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700"
          data-testid="ai-error"
        >
          {error}
        </div>
      ) : null}

      <div className="mt-3 flex flex-col gap-3 border-t border-[var(--stroke)] pt-3">
        <label className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--gray-text)]" htmlFor="ai-chat-input">
          Message
        </label>
        <textarea
          id="ai-chat-input"
          data-testid="ai-input"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask AI about your board..."
          rows={4}
          className="w-full resize-none rounded-2xl border border-[var(--stroke)] bg-white px-3 py-2 text-sm leading-6 text-[var(--navy-dark)] outline-none focus:border-[var(--primary-blue)]"
          disabled={isPending}
        />
        <button
          type="button"
          data-testid="ai-send"
          onClick={() => void handleSend()}
          disabled={!canSend}
          className="inline-flex items-center justify-center rounded-full bg-[var(--secondary-purple)] px-5 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-white transition disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? "Sending..." : "Send"}
        </button>
      </div>
    </aside>
  );
};
