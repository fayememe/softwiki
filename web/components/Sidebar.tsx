'use client';

import { useState, useEffect } from 'react';
import type { Session, ThemeMode } from '@/app/page';
import styles from './Sidebar.module.css';

export type ActivePanel = 'home' | 'chat' | 'ingest' | 'documents' | 'claims' | 'graph' | 'timeline' | 'wiki';

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
}

function ChatIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>; }
function IngestIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>; }
function DocsIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>; }
function ClaimsIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>; }
function WikiIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2 L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>; }
function MoonIcon() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>; }
function SunIcon() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/></svg>; }

function HomeIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>; }
function GraphIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>; }
function TimelineIcon() { return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 16 14"/></svg>; }

const TOOLS: { id: ActivePanel; icon: React.ReactNode; label: string }[] = [
  { id: 'home',      icon: <HomeIcon />,     label: 'Home' },
  { id: 'chat',      icon: <ChatIcon />,     label: 'Chat' },
  { id: 'ingest',    icon: <IngestIcon />,   label: 'Ingest' },
  { id: 'documents', icon: <DocsIcon />,     label: 'Documents' },
  { id: 'claims',    icon: <ClaimsIcon />,   label: 'Claims' },
  { id: 'graph',     icon: <GraphIcon />,    label: 'Graph' },
  { id: 'timeline',  icon: <TimelineIcon />, label: 'Timeline' },
  { id: 'wiki',      icon: <WikiIcon />,     label: 'Wiki' },
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
  workspaces, activeWorkspace, onWorkspaceChange,
  theme, onCycleTheme,
}: SidebarProps) {
  const isWiki = activePanel === 'wiki';
  const [collapsed, setCollapsed] = useState(false);
  const effectiveCollapsed = collapsed || isWiki;

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
          <button className={styles.collapseBtn} onClick={() => setCollapsed(c => !c)} title="Collapse sidebar">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
        )}
      </div>

      {/* ── Workspace Selector ── */}
      {!effectiveCollapsed && (
        <div className={styles.wsSection}>
          <select
            className={styles.wsSelect}
            value={activeWorkspace}
            onChange={e => onWorkspaceChange(e.target.value)}
            title="Switch workspace"
          >
            {workspaces.map(ws => (
              <option key={ws} value={ws}>{ws}</option>
            ))}
          </select>
        </div>
      )}

      {/* ── Middle: Tool Nav ── */}
      <nav className={styles.nav}>
        {TOOLS.map(item => {
          const b = badge(item.id);
          return (
            <button
              key={item.id}
              className={`${styles.navItem} ${activePanel === item.id ? styles.navActive : ''}`}
              onClick={() => onPanelChange(item.id)}
              title={collapsed ? item.label : undefined}
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

      {/* ── Bottom: Session List (only for Chat) ── */}
      {!effectiveCollapsed && activePanel === 'chat' && (
        <div className={styles.sessionSection}>
          <div className={styles.sessionHeader}>
            <span className={styles.sessionTitle}>Sessions</span>
            <span className={styles.sessionCount}>{sessions.length}</span>
            <button className={styles.newSessionBtn} onClick={onNewSession} title="New session">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
          </div>

          <div className={styles.sessionList}>
            {sessions.length === 0 ? (
              <div className={styles.sessionEmpty}>No sessions yet</div>
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
                          {session.name}
                        </span>
                      )}
                      <span className={styles.sessionDate}>
                        {session.messages.length > 0
                          ? `${session.messages.length} msgs · ${formatDate(session.updatedAt)}`
                          : 'Empty'}
                      </span>
                    </div>
                  </button>
                  <button className={styles.sessionDelete} onClick={() => onDeleteSession(session.id)} title="Delete">
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
          <button className={styles.expandBtn} onClick={() => setCollapsed(false)} title="Expand sidebar">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>
      )}
    </aside>
  );
}
