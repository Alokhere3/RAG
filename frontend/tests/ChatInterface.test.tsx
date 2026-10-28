import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ChatInterface } from "../src/features/chat/ChatInterface";
import { apiClient } from "../src/services/api";

describe("ChatInterface (Phase 7 - Chunk 7.5)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders empty state and sample questions when no messages exist", async () => {
    vi.spyOn(apiClient, "getConversations").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    });

    render(<ChatInterface />);

    await waitFor(() => {
      expect(screen.getByTestId("chat-empty-state")).toBeInTheDocument();
      expect(screen.getByText("Grounded Knowledge Assistant")).toBeInTheDocument();
      expect(screen.getByText("No conversations yet.")).toBeInTheDocument();
    });
  });

  it("creates a new conversation and renders it in the sidebar", async () => {
    vi.spyOn(apiClient, "getConversations").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    });

    vi.spyOn(apiClient, "createConversation").mockResolvedValue({
      id: "conv-1",
      user_id: "user-1",
      title: "New Conversation",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    vi.spyOn(apiClient, "getMessages").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    });

    render(<ChatInterface />);

    await waitFor(() => {
      expect(screen.getByTestId("new-chat-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("new-chat-button"));

    await waitFor(() => {
      expect(apiClient.createConversation).toHaveBeenCalled();
      expect(screen.getByTestId("conversation-item-conv-1")).toBeInTheDocument();
    });
  });

  it("sends a message, renders assistant answer-only response, and verifies no citation elements exist", async () => {
    vi.spyOn(apiClient, "getConversations").mockResolvedValue({
      items: [
        {
          id: "conv-1",
          user_id: "user-1",
          title: "HR Policies",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
    });

    vi.spyOn(apiClient, "getMessages").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    });

    vi.spyOn(apiClient, "sendMessage").mockResolvedValue({
      answer: "Annual vacation allowance is 25 days.",
    });

    render(<ChatInterface />);

    await waitFor(() => {
      expect(screen.getByTestId("conversation-item-conv-1")).toBeInTheDocument();
    });

    const input = screen.getByTestId("chat-input");
    fireEvent.change(input, { target: { value: "What is vacation allowance?" } });

    const sendBtn = screen.getByTestId("send-message-button");
    expect(sendBtn).not.toBeDisabled();
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(screen.getByTestId("user-message")).toBeInTheDocument();
      expect(screen.getByTestId("assistant-message")).toBeInTheDocument();
      expect(screen.getByText("Annual vacation allowance is 25 days.")).toBeInTheDocument();
      expect(screen.queryByTestId("citations-tray")).toBeNull();
      expect(screen.queryByTestId("citation-pill")).toBeNull();
      expect(screen.queryByTestId("citation-card")).toBeNull();
    });
  });
});
