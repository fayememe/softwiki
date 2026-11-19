'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { apiListDocuments, apiListClaims, apiListGraph } from '@/lib/api';
import { useT } from '@/lib/i18n';
import styles from './GlobalSearch.module.css';

interface SearchResult {
  type: string;
  label: string;
  subtitle: string;
  icon: string;
}

export default function GlobalSearch({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery('');
      setResults([]);
      setSelectedIdx(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); return; }
    const ql = q.toLowerCase();
    const out: SearchResult[] = [];

    try {
      const docs = await apiListDocuments();
      docs.filter(d => d.title.toLowerCase().includes(ql)).forEach(d => {
        out.push({ type: 'search.typeDocument', label: d.title, subtitle: d.source_name, icon: '📄' });
      });
    } catch {}

    try {
      const claims = await apiListClaims();
      claims.filter(c => c.text.toLowerCase().includes(ql)).slice(0, 10).forEach(c => {
        out.push({ type: 'search.typeClaim', label: c.text.slice(0, 80), subtitle: c.actor || t('common.unknown'), icon: '📋' });
      });
    } catch {}

    try {
      const graph = await apiListGraph();
      graph.entities.filter(e => e.name.toLowerCase().includes(ql)).forEach(e => {
        out.push({ type: 'search.typeEntity', label: e.name, subtitle: e.type || 'entity', icon: '🏷️' });
      });
    } catch {}

    setResults(out.slice(0, 20));
    setSelectedIdx(0);
  }, [t]);

  useEffect(() => {
    const timer = setTimeout(() => doSearch(query), 200);
    return () => clearTimeout(timer);
  }, [query, doSearch]);

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIdx(i => Math.min(i + 1, results.length - 1)); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedIdx(i => Math.max(i - 1, 0)); }
    if (e.key === 'Escape') { onClose(); }
    if (e.key === 'Enter' && results[selectedIdx]) {
      onClose();
    }
  };

  if (!open) return null;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={e => e.stopPropagation()}>
        <input
          ref={inputRef}
          className={styles.input}
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKey}
          placeholder={t('search.placeholder')}
        />
        <div className={styles.results}>
          {results.length === 0 && query && <div className={styles.empty}>{t('search.noResults')}</div>}
          {results.map((r, i) => (
            <div key={`${r.type}-${i}`} className={`${styles.item} ${i === selectedIdx ? styles.itemActive : ''}`}
              onClick={() => onClose()}>
              <span className={styles.itemIcon}>{r.icon}</span>
              <div className={styles.itemInfo}>
                <span className={styles.itemLabel}>{r.label}</span>
                <span className={styles.itemSub}>{r.subtitle}</span>
              </div>
              <span className={styles.itemType}>{t(r.type)}</span>
            </div>
          ))}
        </div>
        <div className={styles.footer}>
          <span>{t('search.navigate')}</span>
          <span>{t('search.open')}</span>
          <span>{t('search.close')}</span>
        </div>
      </div>
    </div>
  );
}
