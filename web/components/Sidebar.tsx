'use client';

import { useState, useEffect } from 'react';
import type { Session, ThemeMode } from '@/app/page';
import { NEW_CHAT_NAME } from '@/app/page';
import { useI18n } from '@/lib/i18n';
import LanguageSwitcher from './LanguageSwitcher';
import RoleSelector from './RoleSelector';
import KnowledgeBaseSelector from './KnowledgeBaseSelector';
import styles from './Sidebar.module.css';

export type ActivePanel =
  | 'home' | 'chat' | 'ingest' | 'documents' | 'claims' | 'conflicts'
  | 'graph' | 'timeline' | 'llmwiki' | 'kbwizard' | 'users';

const ROLE_RANK: Record<string, number> = {
  'wiki-study': 1,
  'wiki-work': 2,
  'wiki-manage': 3,
  'wiki-admin': 4,
};

type RoleId = 'wiki-study' | 'wiki-work' | 'wiki-manage' | 'wiki-admin';

interface SidebarProps {
  activePanel: ActivePanel;
  onPanelChange: (panel: ActivePanel) => void;
  docCount?: number;
  claimCount?: number;
  sessions: Session[];
  activeSessionId: string | null;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, name: string) => void;
  workspaces: string[];
  activeWorkspace: string;
  onWorkspaceChange: (name: string) => void;
  theme?: ThemeMode;
  onCycleTheme?: () => void;
  onToggleAssistant?: () => void;
  assistantOpen?: boolean;
}

function ChatIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>; }
function IngestIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>; }
function DocsIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>; }
function ClaimsIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>; }
function WikiIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2 L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>; }
function MoonIcon() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>; }
function SunIcon() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>; }

function HomeIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>; }
function ConflictsIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3l9 16H3L12 3z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>; }
function GraphIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>; }
function TimelineIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 16 14"/></svg>; }

function PagesIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h9l4 4v12H4z"/><path d="M7 9h6"/><path d="M7 13h6"/><path d="M7 17h4"/></svg>; }
function PortalIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><line x1="3" y1="12" x2="21" y2="12"/><path d="M12 3a15 15 0 0 1 0 18a15 15 0 0 1 0-18z"/></svg>; }
function KbIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6"/><path d="M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6"/></svg>; }

const NAV_GROUPS: {
  key: string;
  labelKey?: string;
  // Minimum role required to see the group. study < work < manage < admin.
  minRole?: RoleId;
  items: { id: ActivePanel; icon: React.ReactNode }[];
}[] = [
  {
    key: 'overview',
    items: [{ id: 'home', icon: <HomeIcon /> }],
  },
  {
    key: 'knowledge',
    labelKey: 'sidebar.groupKnowledge',
    items: [
      { id: 'documents', icon: <DocsIcon /> },
      { id: 'claims', icon: <ClaimsIcon /> },
      { id: 'graph', icon: <GraphIcon /> },
      { id: 'timeline', icon: <TimelineIcon /> },
      { id: 'llmwiki', icon: <WikiIcon /> },
    ],
  },
  {
    key: 'assist',
    items: [{ id: 'chat', icon: <ChatIcon /> }],
  },
  {
    key: 'contrib',
    labelKey: 'sidebar.groupContrib',
    minRole: 'wiki-work',
    items: [
      { id: 'ingest', icon: <IngestIcon /> },
      { id: 'conflicts', icon: <ConflictsIcon /> },
    ],
  },
  {
    key: 'admin',
    labelKey: 'sidebar.groupAdmin',
    minRole: 'wiki-admin',
    items: [
      { id: 'kbwizard', icon: <KbIcon /> },
    ],
  },
];

function formatDate(
  ts: number,
  t: (k: string, p?: Record<string, string | number>) => string,
  locale: string,
): string {
  const d = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 0) return d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
  if (diffDays === 1) return t('sidebar.yesterday');
  if (diffDays < 7) return t('sidebar.daysAgo', { n: diffDays });
  return d.toLocaleDateString(locale, { month: 'short', day: 'numeric' });
}

export default function Sidebar({
  activePanel, onPanelChange, docCount, claimCount,
  sessions, activeSessionId, onNewSession, onSelectSession, onDeleteSession, onRenameSession,
  workspaces, activeWorkspace, onWorkspaceChange,
  theme, onCycleTheme, onToggleAssistant, assistantOpen,
}: SidebarProps) {
  const { t, locale } = useI18n();
  const htmlLocale = locale === 'zh' ? 'zh-CN' : locale;
  const isWiki = activePanel === 'llmwiki';
  const [collapsed, setCollapsed] = useState(false);
  const effectiveCollapsed = collapsed || isWiki;

  // Role gates what the sidebar shows: contributors (work+) get ingest and
  // conflicts, admins get KB management. Enforced server-side too; this only
  // keeps the UI honest.
  const [roleRank, setRoleRank] = useState(1);
  useEffect(() => {
    fetch('/api/permissions', { cache: 'no-store' })
      .then(r => r.json())
      .then(d => setRoleRank(ROLE_RANK[d.role] ?? 1))
      .catch(() => setRoleRank(1));
  }, []);

  // Auto-collapse when entering wiki, expand when leaving
  useEffect(() => { setCollapsed(isWiki); }, [isWiki]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');

  const startRename = (id: string, currentName: string) => {
    setEditingId(id);
    setEditName(currentName);
  };

  const commitRename = () => {
    if (editingId && editName.trim()) {
      onRenameSession(editingId, editName.trim());
    }
    setEditingId(null);
    setEditName('');
  };

  const badge = (id: string) => {
    if (id === 'documents') return docCount;
    if (id === 'claims') return claimCount;
    return undefined;
  };

  return (
    <aside className={`${styles.sidebar} ${effectiveCollapsed ? styles.collapsed : ''}`}>
      {/* ── Top: Logo + Workspace ── */}
      <div className={styles.top}>
        <div className={styles.logoArea}>
          <button className={styles.logoBtn} onClick={() => setCollapsed(c => !c)}>
            <span className={styles.logoPrompt}>{'>_'}</span>
            {effectiveCollapsed ? 'sw' : 'softwiki'}
          </button>
        </div>
        {!effectiveCollapsed && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <LanguageSwitcher />
            <button className={styles.collapseBtn} onClick={() => setCollapsed(c => !c)} title={t("sidebar.collapse")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
            </button>
          </div>
        )}
      </div>

      {/* ── Workspace Selector ── */}
      {!effectiveCollapsed && (
        <div className={styles.wsSection}>
          <KnowledgeBaseSelector />
          <RoleSelector />
        </div>
      )}

      {/* ── Middle: Tool Nav ── */}
      <nav className={styles.nav}>
        {NAV_GROUPS.filter(g => !g.minRole || roleRank >= (ROLE_RANK[g.minRole] ?? 99)).map(group => (
          <div key={group.key} className={styles.navGroup}>
            {!effectiveCollapsed && group.labelKey && (
              <div className={styles.navGroupLabel}>{t(group.labelKey)}</div>
            )}
            {group.items.map(item => {
              const b = badge(item.id);
              const label = t(`sidebar.${item.id}`);
              return (
                <button
                  key={item.id}
                  className={`${styles.navItem} ${activePanel === item.id ? styles.navActive : ''}`}
                  onClick={() => onPanelChange(item.id)}
                  title={collapsed ? label : undefined}
                >
                  <span className={styles.navIcon}>{item.icon}</span>
                  {!effectiveCollapsed && <span className={styles.navLabel}>{label}</span>}
                  {!effectiveCollapsed && b !== undefined && b > 0 && (
                    <span className={styles.navBadge}>{b.toLocaleString()}</span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
        <button
          className={`${styles.navItem} ${assistantOpen ? styles.navActive : ''}`}
          onClick={onToggleAssistant}
          title={t('assistant.title')}
        >
          <span className={styles.navIcon}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              <circle cx="9" cy="10" r="1"/><circle cx="15" cy="10" r="1"/>
            </svg>
          </span>
          {!effectiveCollapsed && <span className={styles.navLabel}>{t('assistant.title')}</span>}
        </button>
        <a
          className={`${styles.navItem} ${styles.navLink}`}
          href="/wikiweb"
          target="_blank"
          rel="noopener noreferrer"
          title={t("sidebar.wikiPortalTitle")}
        >
          <span className={styles.navIcon}><PortalIcon /></span>
          {!effectiveCollapsed && <span className={styles.navLabel}>{t("sidebar.wikiPortal")}</span>}
          {!effectiveCollapsed && <span className={styles.navBadge}>↗</span>}
        </a>
        <a
          className={`${styles.navItem} ${styles.navLink}`}
          href="/graph-studio"
          target="_blank"
          rel="noopener noreferrer"
          title="Knowledge Graph Studio"
        >
          <span className={styles.navIcon}><GraphIcon /></span>
          {!effectiveCollapsed && <span className={styles.navLabel}>Graph Studio</span>}
          {!effectiveCollapsed && <span className={styles.navBadge}>↗</span>}
        </a>
      </nav>

      {/* ── Bottom: Session List (only for Chat) ── */}
      {!effectiveCollapsed && activePanel === 'chat' && (
        <div className={styles.sessionSection}>
          <div className={styles.sessionHeader}>
            <span className={styles.sessionTitle}>{t("sidebar.sessions")}</span>
            <span className={styles.sessionCount}>{sessions.length}</span>
            <button className={styles.newSessionBtn} onClick={onNewSession} title={t("sidebar.newSession")}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
          </div>

          <div className={styles.sessionList}>
            {sessions.length === 0 ? (
              <div className={styles.sessionEmpty}>{t("sidebar.noSessions")}</div>
            ) : (
              sessions.map(session => (
                <div key={session.id} className={`${styles.sessionItem} ${activeSessionId === session.id ? styles.sessionActive : ''}`}>
                  <button className={styles.sessionClick} onClick={() => onSelectSession(session.id)} title={session.name}>
                    <div className={styles.sessionInfo}>
                      {editingId === session.id ? (
                        <input
                          className={styles.sessionRename}
                          value={editName}
                          onChange={e => setEditName(e.target.value)}
                          onBlur={commitRename}
                          onKeyDown={e => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setEditingId(null); }}
                          autoFocus
                          onClick={e => e.stopPropagation()}
                        />
                      ) : (
                        <span className={styles.sessionName} onDoubleClick={() => startRename(session.id, session.name)}>
                          {session.name === NEW_CHAT_NAME ? t('app.newChat') : session.name}
                        </span>
                      )}
                      <span className={styles.sessionDate}>
                        {session.messages.length > 0
                          ? `${session.messages.length} ${t('sidebar.msgs')} · ${formatDate(session.updatedAt, t, htmlLocale)}`
                          : t('sidebar.empty')}
                      </span>
                    </div>
                  </button>
                  <button className={styles.sessionDelete} onClick={() => onDeleteSession(session.id)} title={t("common.delete")}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* ── Collapsed mode ── */}
      {effectiveCollapsed && (
        <div className={styles.collapsedFooter}>
          <LanguageSwitcher collapsed />
          <button className={styles.expandBtn} onClick={() => setCollapsed(false)} title={t("sidebar.expand")}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>
      )}
    </aside>
  );
}
