'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  agentEventsUrl,
  apiAgentAbort,
  apiAgentAsk,
  apiAgentCreateSession,
  apiAgentMessages,
  apiAgentPrompt,
} from '@/lib/api';
import type { AgentAskResponse, AgentMessage, AgentPart } from '@/lib/api';
import {
  emptyAgentChat,
  historyState,
  normalizeAgentEvent,
  reduceAgentEvent,
  type AgentChatState,
} from '@/lib/agent-chat';

interface UseAgentChatOptions {
  agentSessionId: string | null;
  onSessionCreated: (id: string) => void;
  agent?: string;
}

export interface AgentChatController {
  messages: AgentMessage[];
  busy: boolean;
  error: string | null;
  connected: boolean;
  send: (text: string) => Promise<void>;
  stop: () => Promise<void>;
  regenerate: () => Promise<void>;
}

function localId(): string {
  return `local-${crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)}`;
}

function userMessage(id: string, text: string, sessionID: string): AgentMessage {
  return {
    info: { id, role: 'user', sessionID },
    parts: [{ id: `${id}-text`, type: 'text', text }],
  };
}

function stateFromAsk(result: AgentAskResponse): AgentChatState {
  const state = historyState([]);
  const parts: AgentPart[] = [];
  (result.tools || []).forEach((tool, index) => {
    parts.push({
      id: `tool-${index}`,
      type: 'tool',
      tool: tool.name,
      state: { status: tool.status, input: tool.input, output: tool.output },
    });
  });
  parts.push({ id: 'answer', type: 'text', text: result.answer });
  state.messages.answer = { info: { id: 'answer', role: 'assistant' }, parts };
  state.order.push('answer');
  return state;
}

export function useAgentChat({
  agentSessionId,
  onSessionCreated,
  agent,
}: UseAgentChatOptions): AgentChatController {
  const storeRef = useRef<AgentChatState>(emptyAgentChat);
  const sessionRef = useRef<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);
  const connectedSessionRef = useRef<string | null>(null);
  const frameRef = useRef<number | null>(null);
  const [snapshot, setSnapshot] = useState<AgentChatState>(emptyAgentChat);
  const [connected, setConnected] = useState(false);

  const flush = useCallback(() => {
    frameRef.current = null;
    setSnapshot(storeRef.current);
  }, []);

  const schedule = useCallback(() => {
    if (frameRef.current !== null) return;
    frameRef.current = window.requestAnimationFrame(flush);
  }, [flush]);

  const replace = useCallback((state: AgentChatState) => {
    storeRef.current = state;
    schedule();
  }, [schedule]);

  const closeEvents = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
    connectedSessionRef.current = null;
    setConnected(false);
  }, []);

  const connect = useCallback((sessionId: string) => {
    if (connectedSessionRef.current === sessionId && sourceRef.current) return;
    sourceRef.current?.close();
    const source = new EventSource(agentEventsUrl(sessionId));
    sourceRef.current = source;
    connectedSessionRef.current = sessionId;
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (event) => {
      try {
        const parsed = normalizeAgentEvent(JSON.parse(event.data));
        if (!parsed) return;
        const next = reduceAgentEvent(storeRef.current, parsed, sessionId);
        if (next !== storeRef.current) {
          storeRef.current = next;
          schedule();
        }
      } catch (err) {
        console.warn('agent event ignored', err);
      }
    };
  }, [schedule]);

  const loadHistory = useCallback(async (sessionId: string) => {
    try {
      const data = await apiAgentMessages(sessionId);
      replace(historyState(data.messages || []));
    } catch (err) {
      replace({
        ...storeRef.current,
        error: err instanceof Error ? err.message : 'Failed to load agent history',
      });
    }
  }, [replace]);

  useEffect(() => {
    if (agentSessionId === sessionRef.current) return;
    sessionRef.current = agentSessionId;
    closeEvents();
    replace(emptyAgentChat);
    if (agentSessionId) {
      connect(agentSessionId);
      void loadHistory(agentSessionId);
    }
  }, [agentSessionId, closeEvents, connect, loadHistory, replace]);

  useEffect(() => () => {
    closeEvents();
    if (frameRef.current !== null) window.cancelAnimationFrame(frameRef.current);
  }, [closeEvents]);

  const send = useCallback(async (text: string) => {
    const question = text.trim();
    if (!question) return;

    let sessionId = sessionRef.current;
    replace({ ...storeRef.current, busy: true, error: null });
    try {
      if (!sessionId) {
        const created = await apiAgentCreateSession(question.slice(0, 60));
        sessionId = created.session_id;
        sessionRef.current = sessionId;
        onSessionCreated(sessionId);
      }
      connect(sessionId);
      const optimistic = userMessage(localId(), question, sessionId);
      replace({
        ...storeRef.current,
        busy: true,
        error: null,
        messages: { ...storeRef.current.messages, [optimistic.info.id]: optimistic },
        order: [...storeRef.current.order, optimistic.info.id],
      });

      try {
        await apiAgentPrompt(question, sessionId, agent);
      } catch (promptError) {
        const fallback = await apiAgentAsk(question, sessionId, agent);
        if (fallback.error) throw new Error(fallback.error);
        replace(stateFromAsk(fallback));
      }
    } catch (err) {
      replace({
        ...storeRef.current,
        busy: false,
        error: err instanceof Error ? err.message : 'Agent request failed',
      });
    }
  }, [agent, connect, onSessionCreated, replace]);

  const stop = useCallback(async () => {
    const sessionId = sessionRef.current;
    replace({ ...storeRef.current, busy: false });
    if (sessionId) {
      try {
        await apiAgentAbort(sessionId);
      } catch (err) {
        replace({
          ...storeRef.current,
          error: err instanceof Error ? err.message : 'Failed to stop the agent',
        });
      }
    }
  }, [replace]);

  const regenerate = useCallback(async () => {
    const lastUser = [...storeRef.current.order]
      .reverse()
      .map((id) => storeRef.current.messages[id])
      .find((message) => message?.info.role === 'user');
    const text = lastUser?.parts.find((part) => part.type === 'text')?.text;
    if (text) await send(text);
  }, [send]);

  return {
    messages: snapshot.order.map((id) => snapshot.messages[id]).filter(Boolean),
    busy: snapshot.busy,
    error: snapshot.error,
    connected,
    send,
    stop,
    regenerate,
  };
}
