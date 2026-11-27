'use client';

import { useState, useEffect, useCallback } from 'react';
import Sidebar, { ActivePanel } from '@/components/Sidebar';
import ChatPanel from '@/components/ChatPanel';
import AgentSidePane from '@/components/AgentSidePane';
import IngestPanel from '@/components/IngestPanel';
import DocumentsPanel from '@/components/DocumentsPanel';
import ClaimsPanel from '@/components/ClaimsPanel';
import ConflictsPanel from '@/components/ConflictsPanel';
import AdminPanel from '@/components/AdminPanel';
import DashboardPanel from '@/components/DashboardPanel';
import GraphStudioPanel from '@/components/GraphStudioPanel';
import KbWizardPanel from '@/components/KbWizardPanel';
import TimelinePanel from '@/components/TimelinePanel';
import WikiWebPanel from '@/components/WikiWebPanel';
import PipelinePanel from '@/components/PipelinePanel';
import LanguageSwitcher from '@/components/LanguageSwitcher';
import GlobalSearch from '@/components/GlobalSearch';
import { apiStatus } from '@/lib/api';
import type { Message } from '@/components/ChatMessage';
import { useT } from '@/lib/i18n';

export interface Session {
  id: string;
  name: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
}

export type ThemeMode = 'dark' | 'light' | 'auto';

/**
 * Sentinel default session name stored in localStorage.
 * Rendered through the i18n dictionary so it follows the current locale.
 */
export const NEW_CHAT_NAME = 'New Chat';

const THEME_KEY = 'softwiki_theme';

/**
 * Sessions are per knowledge base: switching kb must not drag another library's
 * conversation history into view (the two have unrelated claims and sources).
 */
const sessionsKey = (kb: string) => `softwiki_sessions:${kb}`;

function loadSessions(kb: string): Session[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(sessionsKey(kb));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    for (const s of parsed) {
      for (const m of s.messages) {
        if (m.timestamp) m.timestamp = new Date(m.timestamp);
      }
    }
    return parsed;
  } catch {
    return [];
  }
}

function saveSessions(kb: string, sessions: Session[]) {
  try { localStorage.setItem(sessionsKey(kb), JSON.stringify(sessions)); } catch {}
}

function genId(): string {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function createNewSession(): Session {
  return {
    id: genId(),
    name: NEW_CHAT_NAME,
    messages: [],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
}

function generateSessionName(messages: Message[]): string {
  const firstMsg = messages.find(m => m.role === 'user');
  if (!firstMsg) return NEW_CHAT_NAME;
  const text = firstMsg.content.trim();
  return text.length > 48 ? text.slice(0, 48) + '…' : text;
}

function loadTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'auto';
  try {
    return (localStorage.getItem(THEME_KEY) as ThemeMode) || 'auto';
  } catch {
    return 'auto';
  }
}

function applyTheme(theme: ThemeMode) {
  const root = document.documentElement;
  if (theme === 'auto') {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
  } else {
    root.setAttribute('data-theme', theme);
  }
}

// ── Theme cycle icons (simple, flat) ──
function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function AutoIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5" fill="currentColor" opacity="0.3" />
    </svg>
  );
}

const THEME_ICONS: Record<ThemeMode, React.ReactNode> = {
  dark: <MoonIcon />,
  light: <SunIcon />,
  auto: <AutoIcon />,
};

const THEME_NEXT: Record<ThemeMode, ThemeMode> = {
  auto: 'light',
  light: 'dark',
  dark: 'auto',
};

export default function Home() {
  // I18nProvider lives in app/layout.tsx so the server can render the right
  // locale on first paint; mounting another one here would shadow it.
  return <HomeInner />;
}

function HomeInner() {
  const t = useT();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<ActivePanel>('chat');
  const [docCount, setDocCount] = useState(0);
  const [claimCount, setClaimCount] = useState(0);
  const [theme, setTheme] = useState<ThemeMode>('auto');
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentProject, setAgentProject] = useState<string | undefined>(undefined);
  const [searchOpen, setSearchOpen] = useState(false);
  // Which kb this WebUI is serving. Sessions live under it; the kb switcher
  // reloads the page, so this is read once.
  const [kbName, setKbName] = useState<string | null>(null);

  // Load theme
  useEffect(() => {
    const saved = loadTheme();
    setTheme(saved);
    applyTheme(saved);
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => {
      if (loadTheme() === 'auto') applyTheme('auto');
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // Which kb is active (the process-wide workspace is not user-switchable here)
  useEffect(() => {
    fetch('/api/kb', { cache: 'no-store' })
      .then(r => r.json())
      .then(d => setKbName(d.active || d.kbs?.[0]?.name || 'default'))
      .catch(() => setKbName('default'));
  }, []);

  // Load this kb's sessions
  useEffect(() => {
    if (!kbName) return;
    const loaded = loadSessions(kbName);
    if (loaded.length > 0) {
      setSessions(loaded);
      setActiveSessionId(loaded[0].id);
    } else {
      const def = createNewSession();
      setSessions([def]);
      setActiveSessionId(def.id);
    }
  }, [kbName]);

  useEffect(() => {
    if (kbName && sessions.length > 0) saveSessions(kbName, sessions);
  }, [kbName, sessions]);

  // ⌘K / Ctrl+K global search
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(s => !s);
      }
      if (e.key === 'Escape') setSearchOpen(false);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const status = await apiStatus();
      setDocCount(status.counts.documents || 0);
      setClaimCount(status.counts.claims || 0);
    } catch {}
  }, []);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, [fetchStats]);

  const activeSession = sessions.find(s => s.id === activeSessionId) || null;

  const updateSession = useCallback((id: string, updater: (s: Session) => Session) => {
    setSessions(prev => prev.map(s => s.id === id ? updater(s) : s));
  }, []);

  // The wiki panel hands control to the same assistant pane the header opens,
  // but lands on the Manage project (the one allowed to propose wiki changes).
  const openWikiAssistant = useCallback(() => {
    setAgentProject('manage');
    setAgentOpen(true);
  }, []);

  // Selecting a session from the always-visible sidebar list also opens chat.
  const selectSession = useCallback((id: string) => {
    setActiveSessionId(id);
    setActivePanel('chat');
  }, []);

  const handleNewSession = useCallback(() => {
    const ns = createNewSession();
    setSessions(prev => [ns, ...prev]);
    setActiveSessionId(ns.id);
    setActivePanel('chat');
  }, []);

  const handleDeleteSession = useCallback((id: string) => {
    setSessions(prev => {
      const f = prev.filter(s => s.id !== id);
      if (f.length === 0) {
        const ns = createNewSession();
        setActiveSessionId(ns.id);
        return [ns];
      }
      if (activeSessionId === id) setActiveSessionId(f[0].id);
      return f;
    });
  }, [activeSessionId]);

  const handleRenameSession = useCallback((id: string, name: string) => {
    updateSession(id, s => ({ ...s, name, updatedAt: Date.now() }));
  }, [updateSession]);

  const handleMessagesChange = useCallback((id: string, messages: Message[]) => {
    updateSession(id, s => ({
      ...s,
      messages,
      name: s.name === NEW_CHAT_NAME && messages.length > 0 ? generateSessionName(messages) : s.name,
      updatedAt: Date.now(),
    }));
  }, [updateSession]);

  function cycleTheme() {
    const current = localStorage.getItem(THEME_KEY) || 'auto';
    const next = current === 'auto' ? 'light' : current === 'light' ? 'dark' : 'auto';
    try { localStorage.setItem(THEME_KEY, next); } catch {}
    applyTheme(next);
    setTheme(next);
  }

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <Sidebar
        activePanel={activePanel}
        onPanelChange={setActivePanel}
        docCount={docCount}
        claimCount={claimCount}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onNewSession={handleNewSession}
        onSelectSession={selectSession}
        onDeleteSession={handleDeleteSession}
        onRenameSession={handleRenameSession}
      />
      <main style={{ flex: 1, height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative' }}>
        {/* ── Top-right actions: theme, language, assistant ── */}
        <div className="top-actions">
          <button
            onClick={cycleTheme}
            className="icon-btn"
            title={t('app.themeTitle', { theme: t(`app.theme_${theme}`) })}
            aria-label={t('app.toggleTheme')}
          >
            {theme === 'light' ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>
            ) : theme === 'dark' ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5" fill="currentColor" opacity="0.3"/></svg>
            )}
          </button>
          <LanguageSwitcher />
          <button
            onClick={() => setAgentOpen(v => !v)}
            className={`icon-btn ${agentOpen ? 'icon-btn-active' : ''}`}
            title={t('assistant.title')}
            aria-label={t('assistant.title')}
            aria-pressed={agentOpen}
          >
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              <circle cx="9" cy="10" r="1"/><circle cx="15" cy="10" r="1"/>
            </svg>
          </button>
        </div>
        {activePanel === 'chat' && activeSession && (
          <ChatPanel
            key={activeSession.id}
            sessionId={activeSession.id}
            messages={activeSession.messages}
            onMessagesChange={handleMessagesChange}
          />
        )}
        {activePanel === 'home' && <DashboardPanel />}
        {activePanel === 'ingest' && <IngestPanel />}
        {activePanel === 'pipeline' && <PipelinePanel onNavigate={setActivePanel} />}
        {activePanel === 'documents' && <DocumentsPanel onRefreshStats={fetchStats} />}
        {activePanel === 'claims' && <ClaimsPanel />}
        {activePanel === 'conflicts' && <ConflictsPanel />}
        {activePanel === 'graph' && <GraphStudioPanel />}
        {activePanel === 'timeline' && <TimelinePanel />}
        {activePanel === 'llmwiki' && (
          <WikiWebPanel onOpenAssistant={openWikiAssistant} initialTab="pages" />
        )}
        {activePanel === 'wikiweb' && (
          <WikiWebPanel onOpenAssistant={openWikiAssistant} initialTab="portal" />
        )}
        {activePanel === 'kbwizard' && <KbWizardPanel />}
        {activePanel === 'users' && <AdminPanel />}
      </main>
      {agentOpen && (
        <AgentSidePane
          initialProject={agentProject}
          onClose={() => { setAgentOpen(false); setAgentProject(undefined); }}
        />
      )}

      <GlobalSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
