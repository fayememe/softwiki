'use client';

import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import { apiListWikiTopics, apiBuildWikiPage, apiGetWikiPage } from '@/lib/api';
import styles from './WikiPanel.module.css';

interface TocItem {
  id: string;
  text: string;
  level: number;
}

function extractToc(markdown: string): TocItem[] {
  const lines = markdown.split('\n');
  const toc: TocItem[] = [];
  for (const line of lines) {
    const m = line.match(/^(#{1,4})\s+(.+)$/);
    if (m) {
      const text = m[2].replace(/\*+/g, '').trim();
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
  const [building, setBuilding] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingTopics, setLoadingTopics] = useState(true);
  const [markdown, setMarkdown] = useState('');
  const [builtAt, setBuiltAt] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState('');
  const contentRef = useRef<HTMLDivElement>(null);

  const toc = extractToc(markdown);

  const fetchTopics = async () => {
    setLoadingTopics(true);
    try {
      const data = await apiListWikiTopics();
      const loaded = data.topics || {};
      setTopics(loaded);
      const keys = Object.keys(loaded);
      if (keys.length > 0) selectTopic(keys[0], loaded);
    } catch {
      setError('Failed to fetch topics');
    } finally {
      setLoadingTopics(false);
    }
  };

  const selectTopic = async (topic: string, topicsMap?: Record<string, any>) => {
    setSelectedTopic(topic);
    setMarkdown('');
    setError(null);
    setLoading(true);
    try {
      const page = await apiGetWikiPage(topic);
      setMarkdown(page.content);
      setBuiltAt(page.built_at);
    } catch {
      setMarkdown('');
      setBuiltAt('');
    } finally {
      setLoading(false);
    }
  };

  const handleBuild = async () => {
    if (!selectedTopic || building) return;
    setBuilding(true);
    setError(null);
    try {
      const res = await apiBuildWikiPage(selectedTopic);
      setMarkdown(res.content);
      const now = new Date();
      setBuiltAt(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Build failed');
    } finally {
      setBuilding(false);
    }
  };

  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      setActiveSection(id);
    }
  };

  useEffect(() => { fetchTopics(); }, []);

  // Track active section on scroll
  useEffect(() => {
    if (!contentRef.current || toc.length === 0) return;
    const headings = contentRef.current.querySelectorAll('h1,h2,h3,h4');
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActiveSection(entry.target.id);
        }
      },
      { rootMargin: '-20% 0px -70% 0px' }
    );
    headings.forEach(h => observer.observe(h));
    return () => observer.disconnect();
  }, [markdown]);

  const topicName = (key: string) =>
    topics[key]?.name || key.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

  return (
    <div className={styles.panel}>
      {/* ── Left: Topic List ── */}
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
            {Object.keys(topics).map(key => (
              <button
                key={key}
                className={`${styles.topicItem} ${selectedTopic === key ? styles.topicActive : ''}`}
                onClick={() => selectTopic(key)}
              >
                {topicName(key)}
              </button>
            ))}
          </div>
        )}
      </aside>

      {/* ── Center: Article ── */}
      <article className={styles.article}>
        {loading ? (
          <div className={styles.loadingState}>
            <div className={styles.spinner} />
            <span>Loading wiki page…</span>
          </div>
        ) : !markdown ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon}>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
              </svg>
            </div>
            <h3 className={styles.emptyTitle}>{topicName(selectedTopic)}</h3>
            <p className={styles.emptyDesc}>This wiki page has not been compiled yet.</p>
            <button
              className={styles.buildBtn}
              onClick={handleBuild}
              disabled={building}
            >
              {building ? (
                <><span className={styles.btnSpinner} /> Compiling…</>
              ) : (
                '◆ Compile Wiki Page'
              )}
            </button>
            {error && <p className={styles.errorMsg}>{error}</p>}
          </div>
        ) : (
          <>
            <div className={styles.articleHeader}>
              <h1 className={styles.articleTitle}>{topicName(selectedTopic)}</h1>
              <div className={styles.articleMeta}>
                <span className={styles.builtAt}>
                  Built {builtAt}
                </span>
                <button
                  className={styles.rebuildBtn}
                  onClick={handleBuild}
                  disabled={building}
                >
                  {building ? 'Compiling…' : '↻ Rebuild'}
                </button>
              </div>
            </div>

            {/* Inline TOC */}
            {toc.length > 2 && (
              <div className={styles.tocBox}>
                <div className={styles.tocTitle}>Contents</div>
                <nav className={styles.tocList}>
                  {toc.filter(t => t.level <= 3).map((item, i) => (
                    <button
                      key={i}
                      className={`${styles.tocItem} ${styles['tocLevel' + item.level]} ${activeSection === item.id ? styles.tocActive : ''}`}
                      onClick={() => scrollToSection(item.id)}
                    >
                      {item.text}
                    </button>
                  ))}
                </nav>
              </div>
            )}

            {/* Article body */}
            <div className={styles.articleBody} ref={contentRef}>
              <ReactMarkdown
                components={{
                  h1: ({ children }) => <h1 id={slugify(String(children))}>{children}</h1>,
                  h2: ({ children }) => <h2 id={slugify(String(children))}>{children}</h2>,
                  h3: ({ children }) => <h3 id={slugify(String(children))}>{children}</h3>,
                  h4: ({ children }) => <h4 id={slugify(String(children))}>{children}</h4>,
                }}
              >
                {markdown}
              </ReactMarkdown>
            </div>
          </>
        )}
      </article>

      {/* ── Right: Sticky TOC ── */}
      {toc.length > 2 && markdown && (
        <nav className={styles.tocSidebar}>
          <div className={styles.tocSidebarTitle}>On this page</div>
          {toc.filter(t => t.level <= 3).map((item, i) => (
            <button
              key={i}
              className={`${styles.tocSidebarItem} ${styles['tocSidebarLevel' + item.level]} ${activeSection === item.id ? styles.tocSidebarActive : ''}`}
              onClick={() => scrollToSection(item.id)}
            >
              {item.text}
            </button>
          ))}
        </nav>
      )}
    </div>
  );
}
