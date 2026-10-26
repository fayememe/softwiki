'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  apiApplyWiki,
  apiBuildWikiPage,
  apiDeleteWikiIntervention,
  apiGetWikiPage,
  apiListWikiInterventions,
  apiListWikiTopics,
  apiPreviewWiki,
  apiSaveWikiIntervention,
} from '@/lib/api';
import type { WikiIntervention, WikiPreviewResult } from '@/lib/api';
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
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [studioOpen, setStudioOpen] = useState(false);
  const [studioTopics, setStudioTopics] = useState('');
  const [promptText, setPromptText] = useState('');
  const [includeSaved, setIncludeSaved] = useState(true);
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [saving, setSaving] = useState(false);
  const [studioError, setStudioError] = useState('');
  const [studioNotice, setStudioNotice] = useState('');
  const [previewResults, setPreviewResults] = useState<WikiPreviewResult[]>([]);
  const [interventions, setInterventions] = useState<WikiIntervention[]>([]);
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
      const loaded = (data.topics || {}) as Record<string, any>;
      setTopics(loaded);
      const firstTop = Object.keys(loaded).find(
        k => loaded[k]?.kind === 'category' && !loaded[k]?.parent,
      );
      const firstSub = firstTop
        ? (loaded[firstTop].children || []).find((k: string) => loaded[k]?.kind === 'category')
        : null;
      if (firstSub) {
        selectCategory(firstSub, loaded);
      } else {
        const firstPage = Object.keys(loaded).find(k => loaded[k]?.kind !== 'category');
        if (firstPage) selectTopic(firstPage, loaded);
      }
    } catch {} finally { setLoadingTopics(false); }
  };

  const selectCategory = (category: string, topicsMap?: Record<string, any>) => {
    setSelectedCategory(category);
    setSelectedTopic('');
    setRawMarkdown('');
    setLinkedMarkdown('');
    setSearchQuery('');
    setBuiltAt('');
  };

  const selectTopic = async (topic: string, topicsMap?: Record<string, any>) => {
    const map = topicsMap || topics;
    setSelectedCategory(null);
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

  const handleBuild = async () => {
    if (!selectedTopic || building) return;
    setBuilding(true);
    try {
      await apiBuildWikiPage(selectedTopic);
      await selectTopic(selectedTopic);
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Wiki generation failed');
    } finally {
      setBuilding(false);
    }
  };

  const currentGroup = topics[selectedTopic]?.category || topics[selectedTopic]?.group || 'Other';

  const parseStudioTopics = useCallback(() => {
    return studioTopics
      .split(/[\n,]+/)
      .map(s => s.trim())
      .filter(Boolean);
  }, [studioTopics]);

  const loadInterventions = useCallback(async () => {
    try {
      const data = await apiListWikiInterventions();
      setInterventions(data.interventions || []);
    } catch {
      setInterventions([]);
    }
  }, []);

  const openStudio = () => {
    setStudioOpen(true);
    setStudioTopics(selectedTopic || '');
    setPreviewResults([]);
    setStudioError('');
    setStudioNotice('');
    loadInterventions();
  };

  const handlePreview = async () => {
    const ts = parseStudioTopics();
    if (ts.length === 0) { setStudioError('请至少指定一个 topic。'); return; }
    if (ts.length > 3) { setStudioError('Preview 一次最多 3 个 topic。'); return; }
    setPreviewing(true);
    setStudioError('');
    setStudioNotice('');
    try {
      const data = await apiPreviewWiki(ts, promptText, includeSaved);
      setPreviewResults(data.results || []);
    } catch (err) {
      setStudioError(err instanceof Error ? err.message : 'Preview failed');
      setPreviewResults([]);
    } finally {
      setPreviewing(false);
    }
  };

  const handleSaveIntervention = async (kind: 'global' | 'group' | 'topic') => {
    if (!promptText.trim()) { setStudioError('Prompt 为空，无法保存。'); return; }
    let scope = 'global';
    if (kind === 'group') scope = `group:${currentGroup}`;
    if (kind === 'topic') scope = `topic:${selectedTopic}`;
    setSaving(true);
    setStudioError('');
    setStudioNotice('');
    try {
      await apiSaveWikiIntervention({ scope, text: promptText });
      setPromptText('');
      await loadInterventions();
      setStudioNotice(`已保存到 ${scope}；后续生成会自动叠加。`);
    } catch (err) {
      setStudioError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteIntervention = async (id: string) => {
    try {
      await apiDeleteWikiIntervention(id);
      await loadInterventions();
    } catch (err) {
      setStudioError(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  const handleApplyPrompts = async () => {
    const ts = parseStudioTopics();
    if (ts.length === 0) { setStudioError('请至少指定一个 topic。'); return; }
    if (previewResults.length === 0) { setStudioError('请先 Preview，确认效果后再 Apply。'); return; }
    setApplying(true);
    setStudioError('');
    setStudioNotice('');
    try {
      const data = await apiApplyWiki(ts, promptText, includeSaved);
      const failed = (data.results || []).filter(r => r.error);
      setStudioNotice(`已应用 ${ts.length - failed.length}/${ts.length} 个 topic。`);
      if (failed.length) setStudioError(failed.map(f => `${f.topic}: ${f.error}`).join('\n'));
      if (ts.includes(selectedTopic)) await selectTopic(selectedTopic);
    } catch (err) {
      setStudioError(err instanceof Error ? err.message : 'Apply failed');
    } finally {
      setApplying(false);
    }
  };

  const topicKeys = Object.keys(topics).filter(
    k => topics[k]?.kind !== 'category' && k !== '__ignore__',
  );
  const topCategories = Object.keys(topics).filter(
    k => topics[k]?.kind === 'category' && !topics[k]?.parent,
  );
  const topicName = (key: string) =>
    topics[key]?.name || key.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const categoryChildren = selectedCategory
    ? (topics[selectedCategory]?.children || [])
        .map((k: string) => ({ key: k, info: topics[k] }))
        .filter((x: { key: string; info: any }) => x.info && x.info.kind !== 'category')
    : [];

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
          <button className={styles.topicRefresh} onClick={fetchTopics} title="Reload topics" aria-label="Reload topics">↻</button>
        </div>
        {loadingTopics ? (
          <div className={styles.topicLoading}>Loading…</div>
        ) : (
          <div className={styles.topicListItems}>
            {topCategories.map(topKey => {
              const top = topics[topKey] || {};
              return (
                <div key={topKey} className={styles.topicGroup}>
                  <div className={styles.topicGroupLabel}>{top.name || topKey}</div>
                  {(top.children || []).map((childKey: string) => {
                    const child = topics[childKey] || {};
                    if (child.kind === 'category') {
                      return (
                        <button key={childKey}
                          className={`${styles.topicItem} ${selectedCategory === childKey ? styles.topicActive : ''}`}
                          onClick={() => selectCategory(childKey)}>
                          {child.name || childKey}
                        </button>
                      );
                    }
                    if (child.kind === 'page' && child.nav !== false) {
                      return (
                        <button key={childKey}
                          className={`${styles.topicItem} ${selectedTopic === childKey ? styles.topicActive : ''}`}
                          onClick={() => selectTopic(childKey)}>
                          {child.name || childKey}
                        </button>
                      );
                    }
                    return null;
                  })}
                </div>
              );
            })}
          </div>
        )}
      </aside>

      <article className={styles.article}>
        {selectedCategory ? (
          <div className={styles.categoryView}>
            <h2 className={styles.categoryTitle}>
              {topics[selectedCategory]?.name || selectedCategory}
            </h2>
            <p className={styles.categoryDesc}>
              选择一个子页查看内容；左侧列表不展开叶子。
            </p>
            {categoryChildren.length === 0 ? (
              <div className={styles.categoryEmpty}>暂无子页；后续补充文档后再生效。</div>
            ) : (
              <div className={styles.categoryGrid}>
                {categoryChildren.map(({ key, info }: { key: string; info: any }) => (
                  <button key={key} className={styles.categoryCard} onClick={() => selectTopic(key)}>
                    <span className={styles.categoryCardName}>{info.name || key}</span>
                    <span className={styles.categoryCardMeta}>
                      {info.no_docs ? '知识库暂无文档' : '打开子页'}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : loading ? (
          <div className={styles.loadingState}><div className={styles.spinner} /><span>Loading wiki page…</span></div>
        ) : !rawMarkdown ? (
          <div className={styles.emptyState}>
            <h3 className={styles.emptyTitle}>{topicName(selectedTopic)}</h3>
            <p className={styles.emptyDesc}>
              This topic has claims in the knowledge base, but its wiki page has not been generated yet.
              Generation is manual so a 4,000-topic KB does not trigger thousands of LLM calls.
            </p>
            <div className={styles.emptyActions}>
              <button className={styles.generateBtn} onClick={handleBuild} disabled={building || !selectedTopic}>
                {building ? 'Generating…' : 'Generate wiki page'}
              </button>
              <button className={styles.studioBtn} onClick={openStudio} disabled={!selectedTopic}>
                Prompt Studio
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className={styles.articleHeader}>
              <h1 className={styles.articleTitle}>{topicName(selectedTopic)}</h1>
              <div className={styles.articleMeta}>
                <span className={styles.builtAt}>Built {builtAt}</span>
                <button className={styles.studioBtnSmall} onClick={openStudio}>
                  Prompt Studio
                </button>
                <button className={styles.regenerateBtn} onClick={handleBuild} disabled={building}>
                  {building ? 'Regenerating…' : 'Regenerate'}
                </button>
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

      {studioOpen && (
        <div className={styles.studioBackdrop} onMouseDown={e => { if (e.target === e.currentTarget) setStudioOpen(false); }}>
          <div className={styles.studioPanel} onMouseDown={e => e.stopPropagation()}>
            <div className={styles.studioHeader}>
              <div>
                <h2 className={styles.studioTitle}>Prompt Studio</h2>
                <p className={styles.studioSub}>
                  Intervention 是可选输入，可空、一句话、章节规则或完整模板。先 Preview，满意后再 Apply；canonical wiki 不会被 Preview 修改。
                </p>
              </div>
              <button className={styles.studioClose} onClick={() => setStudioOpen(false)} aria-label="Close">✕</button>
            </div>

            <div className={styles.studioBody}>
              <label className={styles.studioLabel}>Intervention（可空）</label>
              <textarea
                className={styles.studioTextarea}
                value={promptText}
                onChange={e => setPromptText(e.target.value)}
                placeholder={"例：\n所有页面先给结论，再给证据；每个事实必须有 [n]。\n\n[SECTION: 寄存器与编程模型]\n用表格：Offset | Name | Access | Width | Reset | Description\n\n也可以直接粘贴一个完整模板。"}
              />

              <div className={styles.studioRow}>
                <div className={styles.studioField}>
                  <label className={styles.studioLabel}>Topics（逗号或换行分隔，最多 3 个）</label>
                  <input
                    className={styles.studioInput}
                    value={studioTopics}
                    onChange={e => setStudioTopics(e.target.value)}
                    placeholder={selectedTopic || 'rtc-register-map'}
                  />
                </div>
                <label className={styles.studioCheck}>
                  <input type="checkbox" checked={includeSaved} onChange={e => setIncludeSaved(e.target.checked)} />
                  叠加已保存的 interventions
                </label>
              </div>

              <div className={styles.studioActions}>
                <button className={styles.generateBtn} onClick={handlePreview} disabled={previewing || applying}>
                  {previewing ? 'Previewing…' : 'Preview'}
                </button>
                <button className={styles.studioSecondary} onClick={() => handleSaveIntervention('global')} disabled={saving || !promptText.trim()}>
                  Save global
                </button>
                <button className={styles.studioSecondary} onClick={() => handleSaveIntervention('group')} disabled={saving || !promptText.trim()}>
                  Save group ({currentGroup})
                </button>
                <button className={styles.studioSecondary} onClick={() => handleSaveIntervention('topic')} disabled={saving || !promptText.trim()}>
                  Save topic
                </button>
                <button className={styles.studioApply} onClick={handleApplyPrompts} disabled={applying || previewing || previewResults.length === 0}>
                  {applying ? 'Applying…' : 'Apply to topics'}
                </button>
              </div>

              {studioError && <div className={styles.studioError}>{studioError}</div>}
              {studioNotice && <div className={styles.studioNotice}>{studioNotice}</div>}

              <div className={styles.studioSaved}>
                <div className={styles.studioSectionTitle}>Saved interventions ({interventions.length})</div>
                {interventions.length === 0 ? (
                  <div className={styles.studioMuted}>None yet. Save a prompt after it previews well.</div>
                ) : (
                  interventions.map(inv => (
                    <div key={inv.id} className={styles.studioSavedItem}>
                      <div className={styles.studioSavedMeta}>
                        <span className={styles.studioScope}>{inv.scope}</span>
                        <button className={styles.studioDelete} onClick={() => handleDeleteIntervention(inv.id)}>Delete</button>
                      </div>
                      <div className={styles.studioSavedText}>{inv.text}</div>
                    </div>
                  ))
                )}
              </div>

              {previewResults.length > 0 && (
                <div className={styles.studioResults}>
                  <div className={styles.studioSectionTitle}>Preview results</div>
                  {previewResults.map((res, idx) => (
                    <div key={idx} className={styles.studioResult}>
                      <div className={styles.studioResultHead}>
                        <strong>{res.topic}</strong>
                        {res.error ? (
                          <span className={styles.studioErrorInline}>{res.error}</span>
                        ) : (
                          <span className={styles.studioResultMeta}>
                            {res.model || 'model?'} · {res.elapsed_ms ?? 0}ms · {res.citation_count ?? 0} citations · {res.headings?.length ?? 0} headings
                          </span>
                        )}
                      </div>
                      {!res.error && res.warnings && res.warnings.length > 0 && (
                        <ul className={styles.studioWarnings}>
                          {res.warnings.map((w, i) => <li key={i}>{w}</li>)}
                        </ul>
                      )}
                      {!res.error && res.headings && res.headings.length > 0 && (
                        <div className={styles.studioHeadings}>
                          {res.headings.map((h, i) => (
                            <span key={i} className={styles.studioHeadingChip}>{'·'.repeat(Math.max(0, h.level - 1))} {h.text}</span>
                          ))}
                        </div>
                      )}
                      {!res.error && (
                        <pre className={styles.studioPreviewContent}>{res.content}</pre>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
