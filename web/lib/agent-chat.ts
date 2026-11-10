import type { AgentEvent, AgentMessage, AgentPart, AgentPartState } from './api';

export interface AgentChatState {
  messages: Record<string, AgentMessage>;
  order: string[];
  busy: boolean;
  error: string | null;
}

export const emptyAgentChat: AgentChatState = {
  messages: {},
  order: [],
  busy: false,
  error: null,
};

export interface NormalizedAgentEvent {
  type: string;
  properties: Record<string, unknown>;
  data: Record<string, unknown>;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

export function agentErrorText(value: unknown): string | null {
  if (!value) return null;
  if (typeof value === 'string') return value;
  const record = asRecord(value);
  if (!record) return null;
  const data = asRecord(record.data);
  return asString(data?.message) || asString(record.message) || asString(record.name) || 'Agent error';
}

export function normalizeAgentEvent(raw: unknown): NormalizedAgentEvent | null {
  const outer = asRecord(raw);
  if (!outer) return null;
  const event = asRecord(outer.payload) || outer;
  const type = asString(event.type);
  if (!type) return null;
  return {
    type,
    properties: asRecord(event.properties) || {},
    data: asRecord(event.data) || {},
  };
}

export function eventSessionId(event: NormalizedAgentEvent): string | undefined {
  const part = asRecord(event.properties.part);
  const info = asRecord(event.properties.info);
  return (
    asString(event.properties.sessionID) ||
    (part ? asString(part.sessionID) : undefined) ||
    (info ? asString(info.sessionID) : undefined) ||
    asString(event.data.sessionID) ||
    undefined
  );
}

export function isAgentTurnEnd(event: NormalizedAgentEvent): boolean {
  return (
    event.type === 'session.idle' ||
    event.type === 'session.execution.succeeded' ||
    event.type === 'session.execution.interrupted'
  );
}

function withMessage(state: AgentChatState, message: AgentMessage): AgentChatState {
  const messages = { ...state.messages, [message.info.id]: message };
  const order = state.order.includes(message.info.id)
    ? state.order
    : [...state.order, message.info.id];
  return { ...state, messages, order };
}

function updateMessage(
  state: AgentChatState,
  id: string,
  update: (message: AgentMessage) => AgentMessage,
): AgentChatState {
  const existing = state.messages[id];
  if (!existing) return state;
  return { ...state, messages: { ...state.messages, [id]: update(existing) } };
}

function upsertPart(message: AgentMessage, part: AgentPart): AgentMessage {
  const index = message.parts.findIndex((item) => item.id === part.id);
  const parts = index >= 0
    ? message.parts.map((item) => (item.id === part.id ? { ...item, ...part } : item))
    : [...message.parts, part];
  return { ...message, parts };
}

function findPart(state: AgentChatState, partId: string): { messageId: string; part: AgentPart } | null {
  for (const messageId of state.order) {
    const message = state.messages[messageId];
    const part = message?.parts.find((item) => item.id === partId);
    if (part) return { messageId, part };
  }
  return null;
}

export function reduceAgentEvent(
  state: AgentChatState,
  event: NormalizedAgentEvent,
  sessionId: string | null,
): AgentChatState {
  const sid = eventSessionId(event);
  if (sessionId && sid && sid !== sessionId) return state;

  if (event.type === 'message.updated') {
    const info = asRecord(event.properties.info) || asRecord(event.data.info);
    const id = info ? asString(info.id) : undefined;
    if (!info || !id) return state;
    const role = asString(info.role);
    let next = state;
    if (role === 'user') {
      const localIds = next.order.filter(
        (messageId) => messageId.startsWith('local-') && next.messages[messageId]?.info.role === 'user',
      );
      if (localIds.length) {
        const messages = { ...next.messages };
        for (const localId of localIds) delete messages[localId];
        next = { ...next, messages, order: next.order.filter((messageId) => !localIds.includes(messageId)) };
      }
    }
    const existing = next.messages[id];
    return withMessage(next, {
      info: { ...(existing?.info || {}), ...(info as unknown as AgentMessage['info']) },
      parts: existing?.parts || [],
    });
  }

  if (event.type === 'message.part.updated') {
    const part = (asRecord(event.properties.part) || asRecord(event.data.part)) as AgentPart | null;
    const partId = part ? asString(part.id) : undefined;
    if (!part || !partId) return state;
    const messageId = asString(part.messageID) || '';
    if (!messageId) return state;
    const existing = state.messages[messageId];
    const message: AgentMessage = existing || {
      info: { id: messageId, role: 'assistant', sessionID: sid },
      parts: [],
    };
    return withMessage(state, upsertPart(message, { ...part, id: partId }));
  }

  if (event.type === 'message.part.delta') {
    const partId = asString(event.properties.partID) || asString(event.data.partID);
    const delta = asString(event.properties.delta) ?? asString(event.data.delta) ?? '';
    const field = asString(event.properties.field) || asString(event.data.field) || 'text';
    if (!partId || !delta) return state;
    const found = findPart(state, partId);
    if (!found) return state;
    return updateMessage(state, found.messageId, (message) => upsertPart(message, {
      ...found.part,
      [field]: `${asString(found.part[field]) || ''}${delta}`,
    }));
  }

  if (event.type === 'message.part.removed') {
    const partId = asString(event.properties.partID) || asString(event.data.partID);
    if (!partId) return state;
    const found = findPart(state, partId);
    if (!found) return state;
    return updateMessage(state, found.messageId, (message) => ({
      ...message,
      parts: message.parts.filter((item) => item.id !== partId),
    }));
  }

  if (event.type === 'session.status') {
    const status = asRecord(event.properties.status) || asRecord(event.data.status);
    const type = typeof status === 'string' ? status : asString(status?.type);
    const busy = type === 'busy' || type === 'retry' || type === 'running';
    return { ...state, busy };
  }

  if (isAgentTurnEnd(event)) {
    return { ...state, busy: false };
  }

  if (event.type === 'session.execution.failed' || event.type === 'session.error') {
    const error =
      agentErrorText(event.properties.error) ||
      agentErrorText(event.data.error) ||
      asString(event.properties.message) ||
      asString(event.data.message) ||
      'Agent error';
    return { ...state, busy: false, error };
  }

  return state;
}

export function historyState(messages: AgentMessage[]): AgentChatState {
  const next: AgentChatState = { ...emptyAgentChat, messages: {}, order: [] };
  for (const message of messages) {
    if (!message?.info?.id) continue;
    next.messages[message.info.id] = {
      info: message.info,
      parts: Array.isArray(message.parts) ? message.parts : [],
    };
    next.order.push(message.info.id);
  }
  return next;
}

export function toolState(part: AgentPart): AgentPartState {
  return part.state || {};
}
