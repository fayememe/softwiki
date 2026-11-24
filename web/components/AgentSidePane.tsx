'use client';

/**
 * Role-scoped assistant pane on the right.
 *
 * Three projects — Work / Manage / Admin — each backed by its own opencode
 * agent profile (that is where the permission set lives). The pane is
 * independent of the main view: you can browse the wiki on the left and talk to
 * an assistant on the right without either stealing focus from the other.
 *
 * Each project keeps its own session, remembered locally, so switching tabs
 * does not drag one project's context into another.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AgentMessageView from './chat/AgentMessageView';
import { useAgentChat } from './chat/useAgentChat';
import styles from './AgentSidePane.module.css';

interface Project {
  id: string;
  title: string;
  agent: string;
  color: string;
  description: string;
}

interface StoredSession {
  id: string;
  title: string;
  at: number;
}

type SubTab = 'about' | 'sessions' | 'chat';

const STORE_KEY = (projectId: string) => `softwiki_agent_project_${projectId}`;

function loadSessions(projectId: string): StoredSession[] {
  try {
    const raw = localStorage.getItem(STORE_KEY(projectId));
    return raw ? (JSON.parse(raw) as StoredSession[]) : [];
  } catch {
    return [];
  }
}

function saveSessions(projectId: string, sessions: StoredSession[]) {
  try {
    localStorage.setItem(STORE_KEY(projectId), JSON.stringify(sessions.slice(0, 20)));
  } catch {
    /* storage may be disabled; sessions just are not remembered */
  }
}

export default function AgentSidePane({ onClose }: { onClose: () => void }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string>('');
  const [subTab, setSubTab] = useState<SubTab>('chat');
  const [sessions, setSessions] = useState<StoredSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const project = useMemo(
    () => projects.find((p) => p.id === projectId) || null,
    [projects, projectId],
  );

  const chat = useAgentChat({
    agentSessionId: sessionId,
    onSessionCreated: (id) => {
      setSessionId(id);
      if (!project) return;
      const next = [{ id, title: input.slice(0, 40) || 'New session', at: Date.now() }, ...sessions];
      setSessions(next);
      saveSessions(project.id, next);
    },
    agent: project?.agent,
  });

  useEffect(() => {
    fetch('/api/agent/projects', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => {
        setProjects(d.projects || []);
        if ((d.projects || []).length) setProjectId(d.projects[0].id);
      })
      .catch(() => setProjects([]));
  }, []);

  // Switching project loads that project's own session.
  useEffect(() => {
    if (!projectId) return;
    const stored = loadSessions(projectId);
    setSessions(stored);
    setSessionId(stored[0]?.id ?? null);
    setSubTab('chat');
    setInput('');
  }, [projectId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat.messages.length, chat.busy]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || chat.busy) return;
    setInput('');
    await chat.send(text);
  }, [input, chat]);

  const startNew = useCallback(() => {
    setSessionId(null);
    setSubTab('chat');
  }, []);

  if (!project && projects.length === 0) {
    return (
      <aside className={styles.pane}>
        <div className={styles.empty}>Assistant is not configured on this instance.</div>
      </aside>
    );
  }

  return (
    <aside className={styles.pane} style={{ ['--accent' as string]: project?.color || '#3366cc' }}>
      <header className={styles.head}>
        <nav className={styles.projects}>
          {projects.map((p) => (
            <button
              key={p.id}
              className={`${styles.projectTab} ${p.id === projectId ? styles.projectActive : ''}`}
              style={p.id === projectId ? { borderBottomColor: p.color, color: p.color } : undefined}
              onClick={() => setProjectId(p.id)}
            >
              {p.title}
            </button>
          ))}
        </nav>
        <button className={styles.close} onClick={onClose} aria-label="Close assistant">✕</button>
      </header>

      <nav className={styles.subTabs}>
        {(['about', 'sessions', 'chat'] as SubTab[]).map((tab) => (
          <button
            key={tab}
            className={`${styles.subTab} ${subTab === tab ? styles.subActive : ''}`}
            onClick={() => setSubTab(tab)}
          >
            {tab === 'about' ? 'About' : tab === 'sessions' ? 'Sessions' : 'Chat'}
          </button>
        ))}
      </nav>

      {subTab === 'about' && project && (
        <div className={styles.about}>
          <h3 style={{ color: project.color }}>{project.title}</h3>
          <p>{project.description}</p>
          <dl>
            <dt>Agent</dt><dd><code>{project.agent}</code></dd>
            <dt>Can</dt><dd>Read this instance&apos;s knowledge bases within your scope; propose changes.</dd>
            <dt>Cannot</dt><dd>Leave your scope, or approve its own proposals.</dd>
          </dl>
        </div>
      )}

      {subTab === 'sessions' && (
        <div className={styles.sessions}>
          <button className={styles.newSession} onClick={startNew}>+ New session</button>
          {sessions.length === 0 && <div className={styles.empty}>No sessions yet.</div>}
          {sessions.map((s) => (
            <button
              key={s.id}
              className={`${styles.sessionItem} ${s.id === sessionId ? styles.sessionActive : ''}`}
              onClick={() => { setSessionId(s.id); setSubTab('chat'); }}
            >
              <span>{s.title || s.id.slice(0, 12)}</span>
              <small>{new Date(s.at).toLocaleString()}</small>
            </button>
          ))}
        </div>
      )}

      {subTab === 'chat' && (
        <>
          <div className={styles.body}>
            {chat.messages.length === 0 && (
              <div className={styles.empty}>
                Talk to the {project?.title.toLowerCase()} assistant. It works with your
                permissions and proposes changes instead of applying them.
              </div>
            )}
            {chat.messages.map((m) => (
              <AgentMessageView key={m.info.id} message={m} streaming={chat.busy} />
            ))}
            <div ref={bottomRef} />
          </div>

          <div className={styles.composer}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={`Message the ${project?.title.toLowerCase()} assistant…`}
              rows={2}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <div className={styles.composerActions}>
              {chat.busy ? (
                <button className={styles.stop} onClick={() => void chat.stop()}>Stop</button>
              ) : (
                <button className={styles.send} onClick={() => void send()} disabled={!input.trim()}>
                  Send
                </button>
              )}
            </div>
            {chat.error && <div className={styles.error}>{chat.error}</div>}
          </div>
        </>
      )}
    </aside>
  );
}
