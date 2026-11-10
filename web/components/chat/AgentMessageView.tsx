'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { AgentMessage, AgentPart } from '@/lib/api';
import { agentErrorText } from '@/lib/agent-chat';
import ToolCard from './ToolCard';
import styles from './AgentMessageView.module.css';

function asText(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value === undefined || value === null) return '';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function renderPart(part: AgentPart, streaming: boolean) {
  if (part.type === 'text') {
    return (
      <div key={part.id} className={styles.text}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{part.text || ''}</ReactMarkdown>
        {streaming && <span className={styles.caret} aria-hidden />}
      </div>
    );
  }
  if (part.type === 'tool') {
    return <ToolCard key={part.id} part={part} />;
  }
  if (part.type === 'reasoning') {
    return (
      <details key={part.id} className={styles.fold}>
        <summary>Thinking</summary>
        <pre className={styles.pre}>{part.text || ''}</pre>
      </details>
    );
  }
  if (part.type === 'step-start' || part.type === 'step-finish') {
    return null;
  }
  if (part.type === 'error') {
    return <div key={part.id} className={styles.error}>{asText(part.text) || 'Agent error'}</div>;
  }
  return (
    <details key={part.id} className={styles.fold}>
      <summary>{part.type}</summary>
      <pre className={styles.pre}>{asText(part)}</pre>
    </details>
  );
}

interface AgentMessageViewProps {
  message: AgentMessage;
  streaming?: boolean;
}

export default function AgentMessageView({ message, streaming = false }: AgentMessageViewProps) {
  const isUser = message.info.role === 'user';
  const error = agentErrorText(message.info.error);

  if (isUser) {
    return (
      <div className={`${styles.row} ${styles.userRow}`}>
        <div className={`${styles.avatar} ${styles.userAvatar}`} aria-hidden>U</div>
        <div className={styles.userBubble}>
          {message.parts.filter((part) => part.type === 'text').map((part) => (
            <p key={part.id}>{part.text}</p>
          ))}
        </div>
      </div>
    );
  }

  const parts = message.parts.filter((part) => {
    if (part.type === 'text' && !part.text && !streaming) return false;
    return true;
  });

  return (
    <div className={styles.row}>
      <div className={`${styles.avatar} ${styles.botAvatar}`} aria-hidden>AI</div>
      <div className={styles.body}>
        {parts.map((part) => renderPart(part, streaming))}
        {error && <div className={styles.error}>{error}</div>}
      </div>
    </div>
  );
}
