'use client';

import { useState, useEffect } from 'react';
import { apiStatus, apiListWorkspaces } from '@/lib/api';
import styles from './DashboardPanel.module.css';

interface Counts {
  documents: number; chunks: number; claims: number;
  entities: number; relationships: number; events: number;
}

const FLOW = [
  { stage: 'Input', icon: '📥', items: [
    { label: 'Documents', key: 'documents', color: '#5588ff' },
  ]},
  { stage: 'Process', icon: '⚙️', items: [
    { label: 'Chunks', key: 'chunks', color: '#22d3ee' },
    { label: 'Claims', key: 'claims', color: '#a78bfa' },
  ]},
  { stage: 'Knowledge', icon: '🧠', items: [
    { label: 'Entities', key: 'entities', color: '#22c55e' },
    { label: 'Relationships', key: 'relationships', color: '#f59e0b' },
    { label: 'Events', key: 'events', color: '#ef4444' },
  ]},
];

export default function DashboardPanel() {
  const [counts, setCounts] = useState<Counts | null>(null);
  const [ws, setWs] = useState('');

  useEffect(() => {
    apiStatus().then(s => {
      setCounts(s.counts as Counts);
      setWs(s.workspace.split('/').pop() || '');
    }).catch(() => {});
    const interval = setInterval(() => {
      apiStatus().then(s => setCounts(s.counts as Counts)).catch(() => {});
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  const v = (key: string) => counts ? counts[key as keyof Counts] : 0;

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>Dashboard</h1>
          <p className={styles.subtitle}>Workspace: <strong>{ws}</strong></p>
        </div>
        <div className={styles.total}>
          <span className={styles.totalNum}>{v('documents')}</span>
          <span className={styles.totalLabel}>documents</span>
        </div>
      </div>

      {/* Data flow diagram */}
      <div className={styles.flow}>
        {FLOW.map((stage, si) => (
          <div key={stage.stage} className={styles.stage}>
            <div className={styles.stageHeader}>
              <span className={styles.stageIcon}>{stage.icon}</span>
              <span className={styles.stageName}>{stage.stage}</span>
            </div>
            <div className={styles.stageCards}>
              {stage.items.map(item => (
                <div key={item.key} className={styles.flowCard}>
                  <span className={styles.flowValue}>{v(item.key)}</span>
                  <span className={styles.flowLabel}>{item.label}</span>
                </div>
              ))}
            </div>
            {si < FLOW.length - 1 && (
              <div className={styles.arrow}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
