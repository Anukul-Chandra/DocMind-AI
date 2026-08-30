import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ConversationItem } from "./ConversationItem";
import type { ConversationMeta } from "@/types/conversations";

function makeConversation(overrides: Partial<ConversationMeta> = {}): ConversationMeta {
  return {
    conversation_id: "c1",
    owner_id: "u1",
    title: "My chat",
    message_count: 2,
    ...overrides,
  };
}

function renderItem(props: {
  conversation: ConversationMeta;
  isActive?: boolean;
  onSelect?: (id: string) => void;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ConversationItem
        conversation={props.conversation}
        isActive={props.isActive ?? false}
        onSelect={props.onSelect ?? (() => {})}
      />
    </QueryClientProvider>,
  );
}

describe("ConversationItem", () => {
  it("renders the conversation title as clickable", () => {
    renderItem({ conversation: makeConversation() });
    expect(
      screen.getByRole("button", { name: "Open chat: My chat" }),
    ).toBeInTheDocument();
  });

  it("falls back to 'New chat' when the title is blank", () => {
    renderItem({ conversation: makeConversation({ title: "   " }) });
    expect(
      screen.getByRole("button", { name: "Open chat: New chat" }),
    ).toBeInTheDocument();
  });

  it("calls onSelect with the conversation id when clicked", () => {
    const onSelect = vi.fn();
    renderItem({
      conversation: makeConversation(),
      isActive: false,
      onSelect,
    });
    fireEvent.click(screen.getByRole("button", { name: "Open chat: My chat" }));
    expect(onSelect).toHaveBeenCalledWith("c1");
  });

  it("marks the active conversation with aria-current", () => {
    renderItem({ conversation: makeConversation(), isActive: true });
    expect(
      screen.getByRole("button", { name: "Open chat: My chat" }),
    ).toHaveAttribute("aria-current", "page");
  });

  it("shows rename and delete actions for the active conversation", () => {
    renderItem({ conversation: makeConversation(), isActive: true });
    expect(screen.getByText("Rename")).toBeInTheDocument();
    expect(screen.getByText("Delete")).toBeInTheDocument();
  });

  it("does not show actions for an inactive conversation", () => {
    renderItem({ conversation: makeConversation(), isActive: false });
    expect(screen.queryByText("Rename")).not.toBeInTheDocument();
    expect(screen.queryByText("Delete")).not.toBeInTheDocument();
  });
});
