'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { apiAgentSessions, apiAgentStatus, apiAsk, apiReport, apiReportDownloadUrl, apiWorkflows } from '@/lib/api';
import type { AgentSessionSummary, Source, Workflow } from '@/lib/api';
import ChatMessage, { type Message } from './ChatMessage';
import AgentMessageView from './chat/AgentMessageView';
import { useAgentChat } from './chat/useAgentChat';
import SourceDrawer from './SourceDrawer';
import { useT } from '@/lib/i18n';
import styles from './ChatPanel.module.css';

const SUGGESTIONS = [
  'chat.suggestions.kb',
  'chat.suggestions.summarize',
  'chat.suggestions.compare',
  'chat.suggestions.gaps',
];

interface ChatPanelProps {
  sessionId: string;
  messages: Message[];
  onMessagesChange: (sessionId: string, messages: Message[]) => void;
}

const MODES = [
  { id: 'normal' },
  { id: 'deep' },
  { id: 'concise' },
  { id: 'creative' },
];

export default function ChatPanel({ sessionId, messages, onMessagesChange }: ChatPanelProps) {
  const t = useT();
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [drawerSource, setDrawerSource] = useState<Source | null>(null);
  const [mode, setMode] = useState('normal');
  const [workflow, setWorkflow] = useState('');
  const [workflows, setWorkflows] = useState<Record<string, Workflow>>({});
  const [isReporting, setIsReporting] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [engine, setEngine] = useState<'quick' | 'agent'>('quick');
  const [agentSessionId, setAgentSessionId] = useState<string | null>(null);
  const [agentAvailable, setAgentAvailable] = useState<boolean | null>(null);
  const [agentSessions, setAgentSessions] = useState<AgentSessionSummary[]>([]);

  const handleAgentSessionCreated = useCallback((id: string) => {
    setAgentSessionId(id);
    try {
      localStorage.setItem(`softwiki_agent_session_${sessionId}`, id);
    } catch {}
  }, [sessionId]);

  const agentChat = useAgentChat({
    agentSessionId,
    onSessionCreated: handleAgentSessionCreated,
  });

  const agentTail = agentChat.messages[agentChat.messages.length - 1];
  const agentTailLength = agentTail?.parts.reduce(
    (total, part) => total + (part.text?.length || 0), 0,
  ) ?? 0;

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
  }, [messages, streamingContent, agentTailLength, scrollToBottom]);

  // Focus input on session change
  useEffect(() => {
    inputRef.current?.focus();
  }, [sessionId]);

  useEffect(() => {
    apiWorkflows()
      .then(data => setWorkflows(data.workflows))
      .catch(() => {});
  }, []);

  useEffect(() => {
    apiAgentStatus()
      .then(s => setAgentAvailable(s.available))
      .catch(() => setAgentAvailable(false));
  }, []);

  useEffect(() => {
    try {
      setAgentSessionId(localStorage.getItem(`softwiki_agent_session_${sessionId}`));
    } catch {
      setAgentSessionId(null);
    }
  }, [sessionId]);

  useEffect(() => {
    if (engine !== 'agent') return;
    apiAgentSessions()
      .then(data => setAgentSessions((data.sessions || []).filter(session => !session.parent_id)))
      .catch(() => setAgentSessions([]));
  }, [engine, agentChat.busy]);

  const genId = () =>
    crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

  const handleSend = useCallback(async (text?: string) => {
    const question = (text ?? input).trim();
    if (!question) return;
    if (engine === 'agent') {
      if (agentChat.busy) return;
      setInput('');
      await agentChat.send(question);
      inputRef.current?.focus();
      return;
    }
    if (isLoading) return;

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
      const response = await apiAsk(question, history, mode, workflow || undefined);
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
      const errText = err instanceof Error ? err.message : t('chat.requestFailed');
      const errorMsg: Message = {
        id: genId(),
        role: 'assistant',
        content: `${t('common.error')}: ${errText}\n\n${t('chat.apiError')}`,
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
  }, [input, isLoading, messages, sessionId, onMessagesChange, mode, workflow, engine, agentSessionId, agentChat.busy, agentChat.send, t]);

  const handleReport = async () => {
    const question = (
      input.trim() ||
      [...messages].reverse().find(m => m.role === 'user' && !m.isLoading)?.content ||
      ''
    ).trim();
    if (!question || isReporting) return;
    setIsReporting(true);
    try {
      const report = await apiReport(question, 'research-report', workflow || undefined);
      window.open(apiReportDownloadUrl(report.report_id), '_blank', 'noopener,noreferrer');
    } catch (err) {
      alert(err instanceof Error ? err.message : t('chat.reportFailed'));
    } finally {
      setIsReporting(false);
    }
  };

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
    const count = engine === 'agent' ? agentChat.messages.length : messages.length;
    if (count === 0 || !confirm(t('chat.clearConfirm'))) return;
    if (engine === 'agent') {
      if (agentChat.busy) void agentChat.stop();
      setAgentSessionId(null);
      try {
        localStorage.removeItem(`softwiki_agent_session_${sessionId}`);
      } catch {}
      return;
    }
    onMessagesChange(sessionId, []);
  };

  const hasMessages = engine === 'agent'
    ? agentChat.messages.length > 0
    : messages.length > 0;

  return (
    <div className={styles.chatPanel}>
      {/* Messages area */}
      <div className={styles.messagesArea} role="log" aria-live="polite" aria-label={t('chat.messagesAria')}>
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
              <h2 className={styles.emptyTitle}>
                {engine === 'agent' ? 'SWAgent' : t('chat.emptyTitle')}
              </h2>
              <p className={styles.emptyDesc}>
                {engine === 'agent'
                  ? t('chat.emptyDescAgent')
                  : t('chat.emptyDesc')}
              </p>
              <div className={styles.suggestions}>
                {SUGGESTIONS.map((s, i) => (
                  <button
                    key={i}
                    className={styles.suggestion}
                    onClick={() => handleSend(t(s))}
                    disabled={engine === 'agent' ? agentChat.busy : isLoading}
                  >
                    <span className={styles.suggestionIcon}>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="9 18 15 12 9 6" />
                      </svg>
                    </span>
                    {t(s)}
                  </button>
                ))}
              </div>
            </div>
          ) : engine === 'agent' ? (
            <div className={styles.messageList}>
              {agentChat.messages.map((msg, index) => (
                <AgentMessageView
                  key={msg.info.id}
                  message={msg}
                  streaming={
                    agentChat.busy
                    && index === agentChat.messages.length - 1
                    && msg.info.role !== 'user'
                  }
                />
              ))}
              <div ref={messagesEndRef} />
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
      {engine === 'agent' && agentChat.error && (
        <div className={styles.agentError} role="alert">{agentChat.error}</div>
      )}

      {/* Mode / workflow / report bar */}
      <div className={styles.modeBar}>
        <div className={styles.modeInner}>
          <div className={styles.engineSwitch} role="group" aria-label={t('chat.answerEngine')}>
            <button
              className={`${styles.engineBtn} ${engine === 'quick' ? styles.engineActive : ''}`}
              onClick={() => setEngine('quick')}
              disabled={isLoading}
            >
              {t('chat.engineQuick')}
            </button>
            <button
              className={`${styles.engineBtn} ${engine === 'agent' ? styles.engineActive : ''}`}
              onClick={() => setEngine('agent')}
              disabled={isLoading}
              title={t('chat.agentEngineTitle')}
            >
              SWAgent
            </button>
          </div>
          {engine === 'quick' ? MODES.map(m => (
            <button
              key={m.id}
              className={`${styles.modeBtn} ${mode === m.id ? styles.modeActive : ''}`}
              onClick={() => setMode(m.id)}
            >
              {t(`chat.mode_${m.id}`)}
            </button>
          )) : (
            <>
              <select
                className={styles.workflowSelect}
                value={agentSessionId || ''}
                onChange={e => {
                  const next = e.target.value || null;
                  setAgentSessionId(next);
                  try {
                    if (next) {
                      localStorage.setItem(`softwiki_agent_session_${sessionId}`, next);
                    } else {
                      localStorage.removeItem(`softwiki_agent_session_${sessionId}`);
                    }
                  } catch {}
                }}
                aria-label={t('chat.agentSessionAria')}
              >
                <option value="">{t('chat.newSession')}</option>
                {agentSessions.map(item => (
                  <option key={item.id} value={item.id}>
                    {(item.title || item.id).slice(0, 48)}
                  </option>
                ))}
              </select>
              <span className={styles.agentHint}>
                {agentChat.connected
                  ? t('chat.live')
                  : agentAvailable === false
                    ? t('chat.agentOffline')
                    : t('chat.connecting')}
              </span>
              {agentChat.busy ? (
                <button
                  className={styles.reportBtn}
                  onClick={() => { void agentChat.stop(); }}
                  title={t('chat.stopTitle')}
                >
                  {t('chat.stop')}
                </button>
              ) : hasMessages ? (
                <button
                  className={styles.reportBtn}
                  onClick={() => { void agentChat.regenerate(); }}
                  title={t('chat.retryTitle')}
                >
                  {t('common.retry')}
                </button>
              ) : null}
            </>
          )}
          <div className={styles.modeRight}>
            {engine === 'quick' && (
              <select
                className={styles.workflowSelect}
                value={workflow}
                onChange={e => setWorkflow(e.target.value)}
                aria-label={t('chat.workflowAria')}
                disabled={isLoading}
              >
                <option value="">{t('chat.noWorkflow')}</option>
                {Object.entries(workflows).map(([id, wf]) => (
                  <option key={id} value={id}>{wf.name || id}</option>
                ))}
              </select>
            )}
            {engine === 'quick' && (
              <button
                className={styles.reportBtn}
                onClick={handleReport}
                disabled={isReporting || isLoading}
                title={t('chat.reportTitle')}
              >
                {isReporting ? t('chat.generating') : t('chat.report')}
              </button>
            )}
          </div>
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
              placeholder={engine === 'agent' ? t('chat.askAgentPlaceholder') : t('chat.askPlaceholder')}
              rows={1}
              disabled={engine === 'agent' ? agentChat.busy : isLoading}
              aria-label={t('chat.inputAria')}
            />
            <div className={styles.inputActions}>
              {hasMessages && (
                <button
                  className={styles.clearBtn}
                  onClick={clearChat}
                  title={t('chat.clearSession')}
                  aria-label={t('chat.clearSession')}
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
                disabled={!input.trim() || (engine === 'agent' ? agentChat.busy : isLoading)}
                aria-label={t('chat.sendMessage')}
                title={t('chat.sendTitle')}
              >
                {(engine === 'agent' ? agentChat.busy : isLoading) ? (
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
            {engine === 'agent'
              ? t('chat.hintAgent')
              : t('chat.hintQuick')}{' '}
            {t('chat.press')}<kbd>Enter</kbd>{t('chat.sendAction')}<kbd>Shift+Enter</kbd>{t('chat.newLineAction')}
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
