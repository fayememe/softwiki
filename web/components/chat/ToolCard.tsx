'use client';

import type { AgentPart } from '@/lib/api';
import styles from './ToolCard.module.css';

const INPUT_LIMIT = 2000;
const OUTPUT_LIMIT = 6000;

function statusLabel(status: string): string {
  if (status === 'completed') return 'done';
  if (status === 'error') return 'error';
  if (status === 'pending') return 'queued';
  return 'running';
}

function renderValue(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export default function ToolCard({ part }: { part: AgentPart }) {
  const state = part.state || {};
  const status = state.status || 'running';
  const input = renderValue(state.input);
  const output = state.output || '';
  const duration = part.time?.start && part.time?.end
    ? `${((part.time.end - part.time.start) / 1000).toFixed(1)}s`
    : '';
  const title = state.title || part.tool || 'tool';

  return (
    <details className={`${styles.card} ${styles[status] || ''}`} open={status !== 'completed'}>
      <summary className={styles.summary}>
        <span className={styles.dot} aria-hidden />
        <span className={styles.name}>{title}</span>
        <span className={`${styles.status} ${styles[`status_${status}`] || ''}`}>
          {statusLabel(status)}
        </span>
        {duration && <span className={styles.duration}>{duration}</span>}
      </summary>
      <div className={styles.body}>
        {input && (
          <div className={styles.block}>
            <div className={styles.label}>input</div>
            <pre className={styles.pre}>{input.slice(0, INPUT_LIMIT)}</pre>
          </div>
        )}
        {output && (
          <div className={styles.block}>
            <div className={styles.label}>output</div>
            <pre className={styles.pre}>{output.slice(0, OUTPUT_LIMIT)}</pre>
          </div>
        )}
        {state.error && (
          <div className={styles.block}>
            <div className={styles.label}>error</div>
            <pre className={styles.pre}>{state.error}</pre>
          </div>
        )}
      </div>
    </details>
  );
}
