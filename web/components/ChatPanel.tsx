'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { apiAsk } from '@/lib/api';
import type { Source } from '@/lib/api';
import ChatMessage, { type Message } from './ChatMessage';
import SourceDrawer from './SourceDrawer';
import styles from './ChatPanel.module.css';

const SUGGESTIONS = [
  "What's in my knowledge base?",
  "Summarize the key findings from recent sources",
  "Compare different perspectives on the main topic",
  "What areas need more research?",
];

interface ChatPanelProps {
  sessionId: string;
  messages: Message[];
  onMessagesChange: (sessionId: string, messages: Message[]) => void;
}

const MODES = [
  { id: 'normal', label: 'Normal' },
  { id: 'deep', label: 'Deep' },
  { id: 'concise', label: 'Concise' },
  { id: 'creative', label: 'Creative' },
];

export default function ChatPanel({ sessionId, messages, onMessagesChange }: ChatPanelProps) {
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [drawerSource, setDrawerSource] = useState<Source | null>(null);
  const [mode, setMode] = useState('normal');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');

  const scrollToBottom = useCallback((instant = false) => {
    messagesEndRef.current?.scrollIntoView({ behavior: instant ? 'instant' : 'smooth' });
  }, []);

  // Scroll on new messages (smooth), but not on initial mount
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) {
      scrollToBottom(true);
      isFirstRender.current = false;
    } else {
      scrollToBottom();
    }
  }, [messages, streamingContent, scrollToBottom]);

  // Focus input on session change
  useEffect(() => {
    inputRef.current?.focus();
  }, [sessionId]);

  const genId = () =>
    crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

  const handleSend = useCallback(async (text?: string) => {
    const question = (text ?? input).trim();
    if (!question || isLoading) return;

    const userMsg: Message = {
      id: genId(),
      role: 'user',
      content: question,
      timestamp: new Date(),
    };

    const loadingMsg: Message = {
      id: genId(),
      role: 'assistant',
      content: '',
      isLoading: true,
      timestamp: new Date(),
    };

    const updatedMessages = [...messages, userMsg, loadingMsg];
    onMessagesChange(sessionId, updatedMessages);
    setInput('');
    setIsLoading(true);

    try {
      const history = messages
        .filter(m => !m.isLoading)
        .slice(-20) // last 20 messages
        .map(m => ({ role: m.role, content: m.content }));
      const response = await apiAsk(question, history, mode);
      const assistantMsg: Message = {
        id: genId(),
        role: 'assistant',
        content: response.answer,
        sources: response.sources,
        timestamp: new Date(),
      };
      // Replace loading message with actual response
      const finalMessages = updatedMessages
        .filter(m => m.id !== loadingMsg.id)
        .concat(assistantMsg);
      onMessagesChange(sessionId, finalMessages);
    } catch (err) {
      const errText = err instanceof Error ? err.message : 'Request failed';
      const errorMsg: Message = {
        id: genId(),
        role: 'assistant',
        content: `Error: ${errText}\n\nMake sure the API server is running: \`sw api\``,
        error: true,
        timestamp: new Date(),
      };
      const finalMessages = updatedMessages
        .filter(m => m.id !== loadingMsg.id)
        .concat(errorMsg);
      onMessagesChange(sessionId, finalMessages);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  }, [input, isLoading, messages, sessionId, onMessagesChange]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  };

  const clearChat = () => {
    if (messages.length === 0 || !confirm('Clear all messages in this session?')) return;
    onMessagesChange(sessionId, []);
  };

  const hasMessages = messages.length > 0;

  return (
    <div className={styles.chatPanel}>
      {/* Messages area */}
      <div className={styles.messagesArea} role="log" aria-live="polite" aria-label="Chat messages">
        <div className={styles.messagesInner}>
          {!hasMessages ? (
            <div className={styles.empty}>
              <div className={styles.emptyGlow} />
              <div className={styles.emptyIcon}>
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 6v6l4 2" />
                </svg>
              </div>
              <h2 className={styles.emptyTitle}>Research Chat</h2>
              <p className={styles.emptyDesc}>
                Ask questions about your ingested documents. The system searches across full-text, vectors, claims, and knowledge graph to give you grounded answers.
              </p>
              <div className={styles.suggestions}>
                {SUGGESTIONS.map((s, i) => (
                  <button
                    key={i}
                    className={styles.suggestion}
                    onClick={() => handleSend(s)}
                    disabled={isLoading}
                  >
                    <span className={styles.suggestionIcon}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="9 18 15 12 9 6" />
                      </svg>
                    </span>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className={styles.messageList}>
              {messages.map(msg => (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  onSourceClick={src => setDrawerSource(src)}
                />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Mode selector */}
      <div className={styles.modeBar}>
        <div className={styles.modeInner}>
          {MODES.map(m => (
            <button
              key={m.id}
              className={`${styles.modeBtn} ${mode === m.id ? styles.modeActive : ''}`}
              onClick={() => setMode(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* Input bar */}
      <div className={styles.inputArea}>
        <div className={styles.inputContainer}>
          <div className={styles.inputWrapper}>
            <textarea
              ref={inputRef}
              className={styles.input}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask a research question…"
              rows={1}
              disabled={isLoading}
              aria-label="Research question"
            />
            <div className={styles.inputActions}>
              {hasMessages && (
                <button
                  className={styles.clearBtn}
                  onClick={clearChat}
                  title="Clear session"
                  aria-label="Clear session"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
              )}
              <button
                className={styles.sendBtn}
                onClick={() => handleSend()}
                disabled={!input.trim() || isLoading}
                aria-label="Send message"
                title="Send (Enter)"
              >
                {isLoading ? (
                  <span className={styles.spinner} />
                ) : (
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                )}
              </button>
            </div>
          </div>
          <p className={styles.hint}>
            Answers are grounded in your indexed documents. Press <kbd>Enter</kbd> to send, <kbd>Shift+Enter</kbd> for new line.
          </p>
        </div>
      </div>

      {/* Source detail drawer */}
      {drawerSource && (
        <SourceDrawer
          source={drawerSource}
          onClose={() => setDrawerSource(null)}
        />
      )}
    </div>
  );
}
