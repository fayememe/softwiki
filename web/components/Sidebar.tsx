'use client';

import { useState } from 'react';
import type { Session } from '@/app/page';
import styles from './Sidebar.module.css';

export type ActivePanel = 'chat' | 'documents' | 'claims' | 'wiki' | 'ingest';

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
}

function ChatIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function IngestIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function DocsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  );
}

function ClaimsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
      <line x1="7" y1="7" x2="7.01" y2="7" />
    </svg>
  );
}

function WikiIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      <line x1="8" y1="7" x2="16" y2="7" />
      <line x1="8" y1="11" x2="14" y2="11" />
    </svg>
  );
}

const NAV_ITEMS: { id: ActivePanel; icon: React.ReactNode; label: string }[] = [
  { id: 'chat',      icon: <ChatIcon />,     label: 'Chat' },
  { id: 'ingest',    icon: <IngestIcon />,    label: 'Ingest' },
  { id: 'documents', icon: <DocsIcon />,      label: 'Documents' },
  { id: 'claims',    icon: <ClaimsIcon />,    label: 'Claims' },
  { id: 'wiki',      icon: <WikiIcon />,      label: 'Wiki' },
];

function formatDate(ts: number): string {
  const d = new Date(ts);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 0) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export default function Sidebar({
  activePanel, onPanelChange, docCount, claimCount,
  sessions, activeSessionId, onNewSession, onSelectSession, onDeleteSession, onRenameSession,
}: SidebarProps) {
  const isWiki = activePanel === 'wiki';
  const [collapsed, setCollapsed] = useState(isWiki);
  const [showSessions, setShowSessions] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');

  const effectiveCollapsed = collapsed || isWiki;

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

  const sidebarClass = [
    styles.sidebar,
    effectiveCollapsed ? styles.collapsed : '',
    isWiki ? styles.wikiMode : '',
  ].filter(Boolean).join(' ');

  return (
    <aside className={sidebarClass}>
      <div className={styles.logo}>
        <div className={styles.logoMark}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 6v6l4 2" />
          </svg>
        </div>
        {!effectiveCollapsed && (
          <div className={styles.logoText}>
            <span className={styles.logoName}>Softwiki</span>
            <span className={styles.logoTagline}>Research Hub</span>
          </div>
        )}
        {!isWiki && (
          <button
            className={styles.collapseBtn}
            onClick={() => setCollapsed(c => !c)}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              {collapsed ? <polyline points="9 18 15 12 9 6" /> : <polyline points="15 18 9 12 15 6" />}
            </svg>
          </button>
        )}
      </div>

      <nav className={styles.nav}>
        {NAV_ITEMS.map(item => {
          const b = badge(item.id);
          return (
            <button
              key={item.id}
              className={`${styles.navItem} ${activePanel === item.id ? styles.active : ''}`}
              onClick={() => {
                onPanelChange(item.id);
                if (!isWiki) setCollapsed(false);
              }}
              title={effectiveCollapsed ? item.label : undefined}
              aria-label={item.label}
              aria-current={activePanel === item.id ? 'page' : undefined}
            >
              <span className={styles.navIcon}>{item.icon}</span>
              {!effectiveCollapsed && <span className={styles.navLabel}>{item.label}</span>}
              {!effectiveCollapsed && b !== undefined && b > 0 && (
                <span className={styles.navBadge}>{b > 99 ? '99+' : b}</span>
              )}
            </button>
          );
        })}
      </nav>

      {!effectiveCollapsed && (
        <div className={styles.sessionSection}>
          <div className={styles.sessionHeader}>
            <button
              className={styles.sessionToggle}
              onClick={() => setShowSessions(s => !s)}
              aria-expanded={showSessions}
            >
              <svg
                className={`${styles.sessionChevron} ${showSessions ? styles.chevronOpen : ''}`}
                width="12" height="12" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
              >
                <polyline points="9 18 15 12 9 6" />
              </svg>
              <span className={styles.sessionTitle}>Sessions</span>
              <span className={styles.sessionCount}>{sessions.length}</span>
            </button>
            <button className={styles.newSessionBtn} onClick={onNewSession} title="New session" aria-label="New session">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
          </div>

          {showSessions && (
            <div className={styles.sessionList}>
              {sessions.length === 0 ? (
                <div className={styles.sessionEmpty}>No sessions yet</div>
              ) : (
                sessions.map(session => (
                  <div key={session.id} className={`${styles.sessionItem} ${activeSessionId === session.id ? styles.sessionActive : ''}`}>
                    <button className={styles.sessionClick} onClick={() => onSelectSession(session.id)} title={session.name}>
                      <svg className={styles.sessionIcon} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                      </svg>
                      <div className={styles.sessionInfo}>
                        {editingId === session.id ? (
                          <input className={styles.sessionRename} value={editName} onChange={e => setEditName(e.target.value)} onBlur={commitRename} onKeyDown={e => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setEditingId(null); }} autoFocus onClick={e => e.stopPropagation()} />
                        ) : (
                          <span className={styles.sessionName} onDoubleClick={() => startRename(session.id, session.name)}>{session.name}</span>
                        )}
                        <span className={styles.sessionDate}>
                          {session.messages.length > 0 ? `${session.messages.length} messages · ${formatDate(session.updatedAt)}` : 'Empty'}
                        </span>
                      </div>
                    </button>
                    <button className={styles.sessionDelete} onClick={() => onDeleteSession(session.id)} title="Delete session" aria-label="Delete session">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {!effectiveCollapsed && (
        <div className={styles.footer}>
          <div className={styles.footerInfo}>
            <span className={styles.footerLabel}>Workspace</span>
            <span className={styles.footerStatus}>
              <span className={styles.statusDot} /> Active
            </span>
          </div>
        </div>
      )}
    </aside>
  );
}
