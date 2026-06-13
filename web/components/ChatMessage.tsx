'use client';

import { useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Source } from '@/lib/api';
import styles from './ChatMessage.module.css';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
  isLoading?: boolean;
  error?: boolean;
  timestamp: Date;
}

interface ChatMessageProps {
  message: Message;
  onSourceClick?: (source: Source) => void;
}

function ThinkingDots() {
  return (
    <div className={styles.thinking}>
      <div className={styles.thinkingDots}>
        <span /><span /><span />
      </div>
      <span className={styles.thinkingLabel}>Analyzing knowledge base…</span>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  }, [text]);
  return (
    <button className={styles.copyBtn} onClick={handleCopy} title="Copy message" aria-label="Copy message">
      {copied ? (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      ) : (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>
      )}
    </button>
  );
}

function UserAvatar() {
  return (
    <div className={`${styles.avatar} ${styles.userAvatar}`}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
      </svg>
    </div>
  );
}

function BotAvatar() {
  return (
    <div className={`${styles.avatar} ${styles.botAvatar}`}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 6v6l4 2" stroke="white" strokeWidth="1.5" fill="none" />
      </svg>
    </div>
  );
}

export default function ChatMessage({ message, onSourceClick }: ChatMessageProps) {
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const isUser = message.role === 'user';
  const isAssistant = message.role === 'assistant';

  return (
    <div className={`${styles.row} ${isUser ? styles.userRow : ''} animate-fadeInUp`}>
      {/* Side column for avatar (assistant only) — user avatar is inside bubble */}
      {isAssistant && (
        <div className={styles.avatarCol}>
          <BotAvatar />
        </div>
      )}

      <div className={styles.body}>
        {/* User message */}
        {isUser && (
          <div className={styles.userContainer}>
            <div className={`${styles.bubble} ${styles.userBubble}`}>
              <p className={styles.userText}>{message.content}</p>
              <div className={styles.bubbleActions}>
                <CopyButton text={message.content} />
              </div>
            </div>
            <UserAvatar />
          </div>
        )}

        {/* Assistant message */}
        {isAssistant && (
          <>
            {message.isLoading ? (
              <div className={styles.botContainer}>
                <div className={`${styles.bubble} ${styles.botBubble} ${styles.loadingBubble}`}>
                  <ThinkingDots />
                </div>
              </div>
            ) : (
              <div className={styles.botBlock}>
                {message.error ? (
                  <div className={`${styles.bubble} ${styles.botBubble} ${styles.errorBubble}`}>
                    <div className="prose">
                      <ReactMarkdown>{message.content}</ReactMarkdown>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className={`${styles.bubble} ${styles.botBubble}`}>
                      <div className="prose">
                        <ReactMarkdown components={{
                          pre: ({ children }) => (
                            <div className={styles.codeBlock}>
                              <pre>{children}</pre>
                              <button className={styles.codeCopyBtn}
                                onClick={(e) => {
                                  const code = (e.currentTarget.parentElement as HTMLElement)?.querySelector('code');
                                  if (code) navigator.clipboard.writeText(code.textContent || '').catch(() => {});
                                }}
                                title="Copy code"
                              >
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                                </svg>
                              </button>
                            </div>
                          ),
                        }}>{message.content}</ReactMarkdown>
                      </div>
                      <div className={styles.bubbleActions}>
                        <CopyButton text={message.content} />
                      </div>
                    </div>

                    {/* Sources */}
                    {message.sources && message.sources.length > 0 && (
                      <div className={styles.sources}>
                        <button
                          className={styles.sourcesToggle}
                          onClick={() => setSourcesExpanded(e => !e)}
                          aria-expanded={sourcesExpanded}
                        >
                          <svg
                            className={`${styles.sourcesChevron} ${sourcesExpanded ? styles.chevronOpen : ''}`}
                            width="12" height="12" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                          >
                            <polyline points="9 18 15 12 9 6" />
                          </svg>
                          <span>{message.sources.length} source{message.sources.length !== 1 ? 's' : ''}</span>
                        </button>

                        {sourcesExpanded && (
                          <div className={styles.sourcesList}>
                            {message.sources.map((src, i) => (
                              <button
                                key={i}
                                className={styles.sourceCard}
                                onClick={() => onSourceClick?.(src)}
                                title="Click to view source details"
                              >
                                <span className={styles.sourceNum}>
                                  {src.citation_num ?? i + 1}
                                </span>
                                <div className={styles.sourceMeta}>
                                  <div className={styles.sourceTitle}>{src.title || 'Untitled'}</div>
                                  <div className={styles.sourceInfo}>
                                    <span>{src.source_name || 'Unknown'}</span>
                                    {src.published_at && src.published_at !== 'Unknown' && (
                                      <span>· {src.published_at}</span>
                                    )}
                                    <span className={styles.sourceScore}>
                                      {(src.score * 100).toFixed(0)}%
                                    </span>
                                  </div>
                                </div>
                                {src.url && (
                                  <a
                                    href={src.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    onClick={e => e.stopPropagation()}
                                    className={styles.sourceLink}
                                    aria-label="Open source URL"
                                  >
                                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                                      <polyline points="15 3 21 3 21 9" />
                                      <line x1="10" y1="14" x2="21" y2="3" />
                                    </svg>
                                  </a>
                                )}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
