import React, { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "../../services/api";
import type { CitationItem, ConversationItem, MessageItem } from "../../types/chat";

export const ChatInterface: React.FC = () => {
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(true);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [inputText, setInputText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expandedCitation, setExpandedCitation] = useState<{
    msgId: string;
    citationIdx: number;
    citation: CitationItem;
  } | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    if (typeof messagesEndRef.current?.scrollIntoView === "function") {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isSending]);

  const loadConversations = useCallback(async () => {
    setIsLoadingConversations(true);
    try {
      const res = await apiClient.getConversations();
      setConversations(res.items);
      if (res.items.length > 0 && !activeConversationId) {
        setActiveConversationId(res.items[0]?.id ?? null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversations.");
    } finally {
      setIsLoadingConversations(false);
    }
  }, [activeConversationId]);

  const loadMessages = useCallback(async (convId: string) => {
    setIsLoadingMessages(true);
    setError(null);
    try {
      const res = await apiClient.getMessages(convId);
      setMessages(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages.");
    } finally {
      setIsLoadingMessages(false);
    }
  }, []);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    if (activeConversationId) {
      void loadMessages(activeConversationId);
    } else {
      setMessages([]);
    }
  }, [activeConversationId, loadMessages]);

  const handleCreateConversation = async () => {
    setError(null);
    try {
      const newConv = await apiClient.createConversation();
      setConversations((prev) => [newConv, ...prev]);
      setActiveConversationId(newConv.id);
      setMessages([]);
      setTimeout(() => textareaRef.current?.focus(), 50);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create conversation.");
    }
  };

  const handleDeleteConversation = async (convId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this conversation?")) return;
    try {
      await apiClient.deleteConversation(convId);
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      if (activeConversationId === convId) {
        const remaining = conversations.filter((c) => c.id !== convId);
        setActiveConversationId(remaining.length > 0 ? (remaining[0]?.id ?? null) : null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete conversation.");
    }
  };

  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const clean = inputText.trim();
    if (!clean || isSending) return;

    setError(null);
    let targetConvId = activeConversationId;

    if (!targetConvId) {
      try {
        const newConv = await apiClient.createConversation();
        setConversations((prev) => [newConv, ...prev]);
        setActiveConversationId(newConv.id);
        targetConvId = newConv.id;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to start conversation.");
        return;
      }
    }

    const optimisticUserMsg: MessageItem = {
      id: "opt-" + Date.now(),
      conversation_id: targetConvId,
      role: "user",
      content: clean,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, optimisticUserMsg]);
    setInputText("");
    setIsSending(true);

    try {
      const asstMsg = await apiClient.sendMessage(targetConvId, clean);
      setMessages((prev) => [...prev, asstMsg]);
      // Update active conversation title in sidebar if updated
      void loadConversations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate answer.");
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSendMessage();
    }
  };

  return (
    <div className="chat-interface-container" data-testid="chat-interface">
      {/* Sidebar */}
      <aside className="chat-sidebar" data-testid="chat-sidebar">
        <div className="chat-sidebar-header">
          <h2 className="chat-sidebar-title">Conversations</h2>
          <button
            className="btn-new-chat"
            onClick={handleCreateConversation}
            data-testid="new-chat-button"
            title="Start new conversation"
          >
            <span className="icon-plus">+</span> New Chat
          </button>
        </div>

        <div className="chat-conversation-list" data-testid="conversation-list">
          {isLoadingConversations ? (
            <div className="chat-loading-item">Loading conversations...</div>
          ) : conversations.length === 0 ? (
            <div className="chat-empty-sidebar">No conversations yet.</div>
          ) : (
            conversations.map((conv) => (
              <div
                key={conv.id}
                className={`chat-conversation-item ${conv.id === activeConversationId ? "active" : ""
                  }`}
                onClick={() => setActiveConversationId(conv.id)}
                data-testid={`conversation-item-${conv.id}`}
              >
                <div className="conv-item-content">
                  <div className="conv-title">{conv.title}</div>
                  <div className="conv-date">
                    {new Date(conv.updated_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                    })}
                  </div>
                </div>
                <button
                  className="btn-delete-conv"
                  onClick={(e) => handleDeleteConversation(conv.id, e)}
                  data-testid={`delete-conversation-${conv.id}`}
                  title="Delete conversation"
                >
                  ✕
                </button>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Main chat window */}
      <main className="chat-main" data-testid="chat-main">
        {error && (
          <div className="chat-error-banner" data-testid="chat-error-banner">
            <span>{error}</span>
            <button className="chat-error-close" onClick={() => setError(null)}>
              ✕
            </button>
          </div>
        )}

        <div className="chat-messages-scroll" data-testid="messages-container">
          {isLoadingMessages ? (
            <div className="chat-loading-messages">
              <span className="spin-icon">⏳</span> Loading history...
            </div>
          ) : messages.length === 0 ? (
            <div className="chat-empty-state" data-testid="chat-empty-state">
              <div className="chat-empty-icon">💬</div>
              <h3>Grounded Knowledge Assistant</h3>
              <p>
                Ask questions against your indexed documents. Answers are strictly
                grounded with transparent, verifiable citations.
              </p>
              <div className="sample-questions">
                <button
                  className="sample-prompt-chip"
                  onClick={() => {
                    setInputText("What are the key policies and guidelines?");
                    setTimeout(() => textareaRef.current?.focus(), 50);
                  }}
                >
                  "What are the key policies and guidelines?"
                </button>
                <button
                  className="sample-prompt-chip"
                  onClick={() => {
                    setInputText("Summarize the most recent uploaded reports.");
                    setTimeout(() => textareaRef.current?.focus(), 50);
                  }}
                >
                  "Summarize the most recent uploaded reports."
                </button>
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`chat-message-row ${msg.role === "user" ? "user-row" : "assistant-row"}`}
                data-testid={msg.role === "user" ? "user-message" : "assistant-message"}
              >
                <div className={`chat-bubble ${msg.role === "user" ? "user-bubble" : "assistant-bubble"}`}>
                  <div className="chat-message-header">
                    <span className="chat-role-label">
                      {msg.role === "user" ? "You" : "Assistant"}
                    </span>
                    {msg.latency_ms != null && (
                      <span className="chat-latency-badge">
                        {Math.round(msg.latency_ms)}ms
                      </span>
                    )}
                  </div>
                  <div className="chat-message-content">{msg.content}</div>

                  {/* Citations section */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="chat-citations-section" data-testid="citations-tray">
                      <div className="citations-header">Sources & Citations:</div>
                      <div className="citation-pills-row">
                        {msg.citations.map((c, idx) => {
                          const isExpanded =
                            expandedCitation?.msgId === msg.id &&
                            expandedCitation?.citationIdx === idx;
                          return (
                            <button
                              key={idx}
                              className={`citation-pill ${isExpanded ? "active" : ""}`}
                              onClick={() =>
                                setExpandedCitation(
                                  isExpanded ? null : { msgId: msg.id, citationIdx: idx, citation: c }
                                )
                              }
                              data-testid="citation-pill"
                              title="Click to view verified source chunk"
                            >
                              📄 {c.document_title}
                              <span className="citation-chunk">
                                Chunk #{c.chunk_index}
                              </span>
                              <span className="citation-score">
                                {Math.round(c.relevance_score * 100)}%
                              </span>
                            </button>
                          );
                        })}
                      </div>

                      {/* Expanded Citation Preview Card */}
                      {expandedCitation?.msgId === msg.id && (
                        <div className="citation-preview-card" data-testid="citation-card">
                          <div className="citation-preview-header">
                            <strong>{expandedCitation.citation.document_title}</strong>
                            <span className="citation-score-badge">
                              Score: {(expandedCitation.citation.relevance_score * 100).toFixed(1)}%
                            </span>
                            <button
                              className="citation-close-btn"
                              onClick={() => setExpandedCitation(null)}
                            >
                              ✕
                            </button>
                          </div>
                          <div className="citation-preview-meta">
                            Chunk #{expandedCitation.citation.chunk_index}
                          </div>
                          <blockquote className="citation-preview-snippet">
                            {expandedCitation.citation.snippet}
                          </blockquote>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}

          {isSending && (
            <div className="chat-message-row assistant-row">
              <div
                className="chat-bubble assistant-bubble loading-bubble"
                data-testid="chat-loading-indicator"
              >
                <div className="typing-dots">
                  <span>●</span>
                  <span>●</span>
                  <span>●</span>
                </div>
                <span className="loading-text">Synthesizing grounded answer...</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Floating / Docked Input Bar */}
        <div className="chat-input-container">
          <form className="chat-input-form" onSubmit={handleSendMessage}>
            <textarea
              ref={textareaRef}
              className="chat-textarea"
              placeholder="Ask a question about your indexed documents..."
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              maxLength={4000}
              data-testid="chat-input"
              disabled={isSending}
            />
            <div className="chat-input-actions">
              <span className="chat-char-counter">
                {inputText.length} / 4000
              </span>
              <button
                type="submit"
                className="btn-send-message"
                disabled={!inputText.trim() || isSending}
                data-testid="send-message-button"
              >
                Send
              </button>
            </div>
          </form>
        </div>
      </main>
    </div>
  );
};
