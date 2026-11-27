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
import { useI18n, type MessageKey } from '@/lib/i18n';
import AgentMessageView from './chat/AgentMessageView';
import { useAgentChat } from './chat/useAgentChat';
import { useResizableWidth } from '@/lib/use-resizable-width';
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

/** Project title/description are localised here; the API text is the fallback. */
const PROJECT_KEYS: Record<string, { title: MessageKey; description: MessageKey }> = {
  work: {
    title: 'assistant.projects.work.title',
    description: 'assistant.projects.work.description',
  },
  manage: {
    title: 'assistant.projects.manage.title',
    description: 'assistant.projects.manage.description',
  },
  admin: {
    title: 'assistant.projects.admin.title',
    description: 'assistant.projects.admin.description',
  },
};

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

export default function AgentSidePane({
  onClose,
  initialProject,
}: {
  onClose: () => void;
  /** Land on this project instead of the first one (e.g. `manage` from the wiki panel). */
  initialProject?: string;
}) {
  const { t } = useI18n();
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string>('');
  const [subTab, setSubTab] = useState<SubTab>('chat');
  const [sessions, setSessions] = useState<StoredSession[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const pane = useResizableWidth({
    storageKey: 'softwiki_assistant_width',
    defaultWidth: 420,
    min: 320,
    max: () => Math.max(360, Math.min(760, window.innerWidth - 520)),
  });

  const project = useMemo(
    () => projects.find((p) => p.id === projectId) || null,
    [projects, projectId],
  );

  const projectTitle = useCallback(
    (p: Project | null) => {
      if (!p) return '';
      const keys = PROJECT_KEYS[p.id];
      return keys ? t(keys.title) : p.title;
    },
    [t],
  );

  const chat = useAgentChat({
    agentSessionId: sessionId,
    onSessionCreated: (id) => {
      setSessionId(id);
      if (!project) return;
      const next = [
        { id, title: input.slice(0, 40) || t('assistant.newSessionTitle'), at: Date.now() },
        ...sessions,
      ];
      setSessions(next);
      saveSessions(project.id, next);
    },
    agent: project?.agent,
  });

  useEffect(() => {
    fetch('/api/agent/projects', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => {
        const list: Project[] = d.projects || [];
        setProjects(list);
        if (!list.length) return;
        const wanted = initialProject && list.some((p) => p.id === initialProject);
        setProjectId(wanted ? (initialProject as string) : list[0].id);
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
        <div className={styles.empty}>{t('assistant.notConfigured')}</div>
      </aside>
    );
  }

  const label = projectTitle(project);

  return (
    <aside
      className={styles.pane}
      style={{
        ['--accent' as string]: project?.color || '#3366cc',
        width: pane.width,
      }}
      data-dragging={pane.dragging ? 'true' : undefined}
    >
      <div
        className={styles.resizer}
        role="separator"
        aria-orientation="vertical"
        aria-label={t('assistant.resize')}
        title={t('assistant.resize')}
        {...pane.handleProps}
      />
      <header className={styles.head}>
        <nav className={styles.projects}>
          {projects.map((p) => (
            <button
              key={p.id}
              className={`${styles.projectTab} ${p.id === projectId ? styles.projectActive : ''}`}
              style={p.id === projectId ? { borderBottomColor: p.color, color: p.color } : undefined}
              onClick={() => setProjectId(p.id)}
            >
              {projectTitle(p)}
            </button>
          ))}
        </nav>
        <button className={styles.close} onClick={onClose} aria-label={t('assistant.title')}>
          ✕
        </button>
      </header>

      <nav className={styles.subTabs}>
        {(['about', 'sessions', 'chat'] as SubTab[]).map((tab) => (
          <button
            key={tab}
            className={`${styles.subTab} ${subTab === tab ? styles.subActive : ''}`}
            onClick={() => setSubTab(tab)}
          >
            {tab === 'about'
              ? t('assistant.tabAbout')
              : tab === 'sessions'
                ? t('assistant.tabSessions')
                : t('assistant.tabChat')}
          </button>
        ))}
      </nav>

      {subTab === 'about' && project && (
        <div className={styles.about}>
          <h3 style={{ color: project.color }}>{label}</h3>
          <p>
            {PROJECT_KEYS[project.id]
              ? t(PROJECT_KEYS[project.id].description)
              : project.description}
          </p>
          <dl>
            <dt>{t('assistant.aboutAgent')}</dt>
            <dd>
              <code>{project.agent}</code>
            </dd>
            <dt>{t('assistant.aboutCan')}</dt>
            <dd>{t('assistant.aboutCanText')}</dd>
            <dt>{t('assistant.aboutCannot')}</dt>
            <dd>{t('assistant.aboutCannotText')}</dd>
          </dl>
        </div>
      )}

      {subTab === 'sessions' && (
        <div className={styles.sessions}>
          <button className={styles.newSession} onClick={startNew}>
            {t('assistant.newSession')}
          </button>
          {sessions.length === 0 && <div className={styles.empty}>{t('assistant.noSessions')}</div>}
          {sessions.map((s) => (
            <button
              key={s.id}
              className={`${styles.sessionItem} ${s.id === sessionId ? styles.sessionActive : ''}`}
              onClick={() => {
                setSessionId(s.id);
                setSubTab('chat');
              }}
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
              <div className={styles.empty}>{t('assistant.emptyChat', { project: label })}</div>
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
              placeholder={t('assistant.placeholder', { project: label })}
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
                <button className={styles.stop} onClick={() => void chat.stop()}>
                  {t('assistant.stop')}
                </button>
              ) : (
                <button className={styles.send} onClick={() => void send()} disabled={!input.trim()}>
                  {t('assistant.send')}
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
