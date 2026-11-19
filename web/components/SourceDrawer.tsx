'use client';

import type { Source } from '@/lib/api';
import { useT } from '@/lib/i18n';
import styles from './SourceDrawer.module.css';

interface SourceDrawerProps {
  source: Source;
  onClose: () => void;
}

export default function SourceDrawer({ source, onClose }: SourceDrawerProps) {
  const t = useT();
  return (
    <>
      <div className={styles.backdrop} onClick={onClose} aria-hidden="true" />
      <aside className={`${styles.drawer} animate-slideRight`} aria-label={t('source.aria')}>
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <span className={styles.headerIcon}>◈</span>
            <span className={styles.headerTitle}>{t('source.title')}</span>
          </div>
          <button
            id="source-drawer-close"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label={t('source.closeAria')}
          >✕</button>
        </div>

        <div className={styles.body}>
          {/* Citation number */}
          <div className={styles.citationNum}>
            [{source.citation_num}]
          </div>

          {/* Title */}
          <h2 className={styles.sourceTitle}>{source.title || t('source.untitled')}</h2>

          {/* Metadata grid */}
          <div className={styles.metaGrid}>
            {source.source_name && (
              <div className={styles.metaItem}>
                <span className={styles.metaLabel}>{t('source.fieldSource')}</span>
                <span className={styles.metaValue}>{source.source_name}</span>
              </div>
            )}
            {source.published_at && source.published_at !== 'Unknown' && (
              <div className={styles.metaItem}>
                <span className={styles.metaLabel}>{t('source.fieldPublished')}</span>
                <span className={styles.metaValue}>{source.published_at}</span>
              </div>
            )}
            {source.page_start != null && (
              <div className={styles.metaItem}>
                <span className={styles.metaLabel}>{t('source.fieldPages')}</span>
                <span className={styles.metaValue}>
                  {source.page_end != null && source.page_end !== source.page_start
                    ? `${source.page_start}–${source.page_end}`
                    : source.page_start}
                </span>
              </div>
            )}
            {source.score != null && (
              <div className={styles.metaItem}>
                <span className={styles.metaLabel}>{t('source.fieldRelevance')}</span>
                <div className={styles.scoreBar}>
                  <div
                    className={styles.scoreBarFill}
                    style={{ width: `${Math.min(100, source.score * 100).toFixed(0)}%` }}
                  />
                  <span className={styles.scoreText}>{(source.score * 100).toFixed(1)}%</span>
                </div>
              </div>
            )}
          </div>

          {/* Chunk text */}
          <div className={styles.section}>
            <div className={styles.sectionLabel}>{t('source.excerpt')}</div>
            <blockquote className={styles.excerpt}>{source.text}</blockquote>
          </div>

          {/* URL link */}
          {source.url && (
            <div className={styles.section}>
              <div className={styles.sectionLabel}>{t('source.originalUrl')}</div>
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
