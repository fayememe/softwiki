'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { apiListWikiTopics, apiGetWikiPage } from '@/lib/api';
import styles from './WikiPanel.module.css';

interface TocItem { id: string; text: string; level: number; }

function extractToc(markdown: string): TocItem[] {
  const lines = markdown.split('\n');
  const toc: TocItem[] = [];
  for (const line of lines) {
    const m = line.match(/^(#{1,4})\s+(.+)$/);
    if (m) {
      let text = m[2].replace(/\*+/g, '').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').trim();
      const id = text.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-');
      toc.push({ id, text, level: m[1].length });
    }
  }
  return toc;
}

function slugify(text: string): string {
  return text.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-');
}

export default function WikiPanel() {
  const [topics, setTopics] = useState<Record<string, any>>({});
  const [selectedTopic, setSelectedTopic] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingTopics, setLoadingTopics] = useState(true);
  const [rawMarkdown, setRawMarkdown] = useState('');
  const [builtAt, setBuiltAt] = useState('');
  const [activeSection, setActiveSection] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [linkedMarkdown, setLinkedMarkdown] = useState('');
  const contentRef = useRef<HTMLDivElement>(null);
  const [searchIdx, setSearchIdx] = useState(0);
  const searchMatches = useRef<HTMLElement[]>([]);

  const toc = extractToc(rawMarkdown);

  // Build linked markdown: replace topic names with wiki:// links
  const buildLinkedMarkdown = useCallback((md: string, topicKeys: string[], topicsMap: Record<string, any>, current: string) => {
    if (!md) return '';
    // Sort topic names by length descending to match longer names first
    const names = topicKeys
      .filter(k => k !== current)
      .map(k => ({ key: k, name: topicsMap[k]?.name || k.replace(/-/g, ' ') }))
      .sort((a, b) => b.name.length - a.name.length);

    let result = md;
    for (const { key, name } of names) {
      // Only replace whole-word matches (not inside other words)
      const regex = new RegExp(`\\b${escapeRegex(name)}\\b`, 'gi');
      result = result.replace(regex, (match) => `[${match}](wiki://${key})`);
    }
    return result;
  }, []);

  useEffect(() => {
    fetchTopics();
  }, []);

  function escapeRegex(s: string) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  const fetchTopics = async () => {
    setLoadingTopics(true);
    try {
      const data = await apiListWikiTopics();
      const loaded = data.topics || {};
      setTopics(loaded);
      const keys = Object.keys(loaded);
      if (keys.length > 0) selectTopic(keys[0], loaded);
    } catch {} finally { setLoadingTopics(false); }
  };

  const selectTopic = async (topic: string, topicsMap?: Record<string, any>) => {
    const map = topicsMap || topics;
    setSelectedTopic(topic);
    setRawMarkdown('');
    setLinkedMarkdown('');
    setSearchQuery('');
    setLoading(true);
    try {
      const page = await apiGetWikiPage(topic);
      setRawMarkdown(page.content);
      const keys = Object.keys(map);
      const linked = buildLinkedMarkdown(page.content, keys, map, topic);
      setLinkedMarkdown(linked);
      setBuiltAt(page.built_at);
    } catch { setRawMarkdown(''); setBuiltAt(''); }
    finally { setLoading(false); }
  };

  const handleWikiLink = (e: React.MouseEvent, topicKey: string) => {
    e.preventDefault();
    selectTopic(topicKey);
  };

  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'start' }); setActiveSection(id); }
  };

  // Scroll tracking for TOC
  useEffect(() => {
    if (!contentRef.current || toc.length === 0) return;
    const headings = contentRef.current.querySelectorAll('h1,h2,h3,h4');
    const observer = new IntersectionObserver(
      (entries) => { for (const e of entries) { if (e.isIntersecting) setActiveSection(e.target.id); } },
      { rootMargin: '-20% 0px -70% 0px' }
    );
    headings.forEach(h => observer.observe(h));
    return () => observer.disconnect();
  }, [linkedMarkdown]);

  // In-page search
  useEffect(() => {
    if (!searchQuery || !contentRef.current) {
      searchMatches.current = [];
      setSearchIdx(0);
      document.querySelectorAll('.wiki-search-highlight').forEach(el => {
        el.replaceWith(el.textContent || '');
      });
      return;
    }
    const body = contentRef.current;
    const textNodes: Text[] = [];
    const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, null);
    let node;
    while ((node = walker.nextNode())) textNodes.push(node as Text);

    body.querySelectorAll('.wiki-search-highlight').forEach(el => {
      el.replaceWith(el.textContent || '');
    });

    const q = searchQuery.toLowerCase();
    const matches: HTMLElement[] = [];
    textNodes.forEach(n => {
      const text = n.textContent || '';
      const idx = text.toLowerCase().indexOf(q);
      if (idx === -1) return;
      const span = document.createElement('span');
      span.className = 'wiki-search-highlight';
      span.textContent = text.substring(idx, idx + q.length);
      const rest = document.createTextNode(text.substring(idx + q.length));
      n.textContent = text.substring(0, idx);
      n.parentNode?.insertBefore(span, n.nextSibling);
      n.parentNode?.insertBefore(rest, span.nextSibling);
      matches.push(span);
    });
    searchMatches.current = matches;
    setSearchIdx(0);
    if (matches.length > 0) matches[0]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [searchQuery, linkedMarkdown]);

  const goToSearchMatch = (dir: number) => {
    const ms = searchMatches.current;
    if (ms.length === 0) return;
    const next = (searchIdx + dir + ms.length) % ms.length;
    setSearchIdx(next);
    ms[next]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    ms[next]?.classList.add('wiki-search-active');
    setTimeout(() => ms[next]?.classList.remove('wiki-search-active'), 1000);
  };

  const topicKeys = Object.keys(topics);
  const topicName = (key: string) =>
    topics[key]?.name || key.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  // Compute "See also" from the raw content
  const bodyLower = rawMarkdown.toLowerCase();
  const related = topicKeys.filter(k => {
    if (k === selectedTopic) return false;
    const name = (topics[k]?.name || k.replace(/-/g, ' ')).toLowerCase();
    return bodyLower.includes(name) && name.length > 2;
  });

  return (
    <div className={styles.panel}>
      <aside className={styles.topicList}>
        <div className={styles.topicListHeader}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          </svg>
          Topics
        </div>
        {loadingTopics ? (
          <div className={styles.topicLoading}>Loading…</div>
        ) : (
          <div className={styles.topicListItems}>
            {(() => {
              const groups: Record<string, string[]> = {};
              const groupOrder: string[] = [];
              for (const key of topicKeys) {
                const g = topics[key]?.group || 'Other';
                if (!groups[g]) { groups[g] = []; groupOrder.push(g); }
                groups[g].push(key);
              }
              return groupOrder.map(g => (
                <div key={g} className={styles.topicGroup}>
                  <div className={styles.topicGroupLabel}>{g}</div>
                  {groups[g].map(key => (
                    <button key={key}
                      className={`${styles.topicItem} ${selectedTopic === key ? styles.topicActive : ''}`}
                      onClick={() => selectTopic(key)}>
                      {topicName(key)}
                    </button>
                  ))}
                </div>
              ));
            })()}
          </div>
        )}
      </aside>

      <article className={styles.article}>
        {loading ? (
          <div className={styles.loadingState}><div className={styles.spinner} /><span>Loading wiki page…</span></div>
        ) : !rawMarkdown ? (
          <div className={styles.emptyState}>
            <h3 className={styles.emptyTitle}>{topicName(selectedTopic)}</h3>
            <p className={styles.emptyDesc}>Wiki page not available yet. Ingest documents and rebuild the index — wiki pages are built automatically.</p>
          </div>
        ) : (
          <>
            <div className={styles.articleHeader}>
              <h1 className={styles.articleTitle}>{topicName(selectedTopic)}</h1>
              <div className={styles.articleMeta}>
                <span className={styles.builtAt}>Built {builtAt}</span>
              </div>
            </div>

            <div className={styles.searchBar}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input className={styles.searchInput} value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search in page…" />
              {searchMatches.current.length > 0 && (
                <span className={styles.searchCount}>
                  {searchIdx + 1}/{searchMatches.current.length}
                  <button className={styles.searchNav} onClick={() => goToSearchMatch(-1)}>↑</button>
                  <button className={styles.searchNav} onClick={() => goToSearchMatch(1)}>↓</button>
                </span>
              )}
            </div>

            {toc.length > 2 && (
              <div className={styles.tocFloat}>
                <div className={styles.tocFloatTitle}>Contents</div>
                {toc.filter(t => t.level <= 3).map((item, i) => (
                  <button key={i}
                    className={`${styles.tocFloatItem} ${styles['tocFloatLevel' + item.level]} ${activeSection === item.id ? styles.tocFloatActive : ''}`}
                    onClick={() => scrollToSection(item.id)}>{item.text}</button>
                ))}
              </div>
            )}
            <div className={styles.articleBody} ref={contentRef}>
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                h1: ({ children }) => <h1 id={slugify(String(children))}>{children}</h1>,
                h2: ({ children }) => <h2 id={slugify(String(children))}>{children}</h2>,
                h3: ({ children }) => <h3 id={slugify(String(children))}>{children}</h3>,
                h4: ({ children }) => <h4 id={slugify(String(children))}>{children}</h4>,
                a: ({ href, children }) => {
                  if (href?.startsWith('wiki://')) {
                    const key = href.slice(7);
                    return <a href="#" className={styles.internalLink} onClick={e => handleWikiLink(e, key)}>{children}</a>;
                  }
                  return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
                },
              }}>{linkedMarkdown}</ReactMarkdown>
            </div>

            {related.length > 0 && (
              <div className={styles.seeAlso}>
                <h2>See also</h2>
                <ul>
                  {related.map(k => (
                    <li key={k}>
                      <a href="#" onClick={e => handleWikiLink(e, k)}>{topicName(k)}</a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </article>

    </div>
  );
}
