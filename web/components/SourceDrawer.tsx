'use client';

import type { Source } from '@/lib/api';
import styles from './SourceDrawer.module.css';

interface SourceDrawerProps {
  source: Source;
  onClose: () => void;
}

export default function SourceDrawer({ source, onClose }: SourceDrawerProps) {
  return (
    <>
      <div className={styles.backdrop} onClick={onClose} aria-hidden="true" />
      <aside className={`${styles.drawer} animate-slideRight`} aria-label="Source detail">
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <span className={styles.headerIcon}>◈</span>
            <span className={styles.headerTitle}>Source Detail</span>
          </div>
          <button
            id="source-drawer-close"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Close source drawer"
          >✕</button>
        </div>

        <div className={styles.body}>
          {/* Citation number */}
          <div className={styles.citationNum}>
            [{source.citation_num}]
          </div>

          {/* Title */}
          <h2 className={styles.sourceTitle}>{source.title || 'Untitled Document'}</h2>

          {/* Metadata grid */}
          <div className={styles.metaGrid}>
            {source.source_name && (
              <div className={styles.metaItem}>
                <span className={styles.metaLabel}>Source</span>
                <span className={styles.metaValue}>{source.source_name}</span>
              </div>
            )}
            {source.published_at && source.published_at !== 'Unknown' && (
              <div className={styles.metaItem}>
                <span className={styles.metaLabel}>Published</span>
                <span className={styles.metaValue}>{source.published_at}</span>
              </div>
            )}
            <div className={styles.metaItem}>
              <span className={styles.metaLabel}>Relevance</span>
              <div className={styles.scoreBar}>
                <div
                  className={styles.scoreBarFill}
                  style={{ width: `${Math.min(100, source.score * 100).toFixed(0)}%` }}
                />
                <span className={styles.scoreText}>{(source.score * 100).toFixed(1)}%</span>
              </div>
            </div>
          </div>

          {/* Chunk text */}
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Relevant Excerpt</div>
            <blockquote className={styles.excerpt}>{source.text}</blockquote>
          </div>

          {/* URL link */}
          {source.url && (
            <div className={styles.section}>
              <div className={styles.sectionLabel}>Original URL</div>
              <a
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.urlLink}
                id="source-drawer-url"
              >
                <span className={styles.urlText}>{source.url}</span>
                <span className={styles.urlArrow}>↗</span>
              </a>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
