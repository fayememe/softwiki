'use client';

import { useEffect, useState } from 'react';
import { useT } from '@/lib/i18n';

const KBS = [
  { id: 'coffee', label: 'Coffee KB', port: '6108' },
  { id: 'ai-history', label: 'AI History KB', port: '6109' },
];

export default function KnowledgeBaseSelector() {
  const t = useT();
  const [current, setCurrent] = useState('');

  useEffect(() => {
    const port = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
    setCurrent(KBS.find(k => k.port === port)?.id || 'current');
  }, []);

  const change = (id: string) => {
    const kb = KBS.find(k => k.id === id);
    if (!kb) return;
    const protocol = window.location.protocol;
    window.location.href = `${protocol}//${window.location.hostname}:${kb.port}/`;
  };

  return (
    <select
      aria-label={t('workspace.kbAria')}
      title={t('workspace.kbTitle')}
      value={current}
      onChange={e => change(e.target.value)}
      style={{
        width: '100%',
        marginTop: 6,
        padding: '5px 7px',
        borderRadius: 6,
        border: '1px solid var(--glass-border, #d8dde3)',
        background: 'var(--glass-bg, #fff)',
        color: 'var(--text-secondary, #54595d)',
        fontSize: 11,
      }}
    >
      {current === 'current' && <option value="current">{t('workspace.current')}</option>}
      {KBS.map(k => <option key={k.id} value={k.id}>{k.label}</option>)}
    </select>
  );
}
