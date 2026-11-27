'use client';

import { useState, useEffect } from 'react';
import { apiListTimeline } from '@/lib/api';
import type { TimelineEvent } from '@/lib/api';
import { useT } from '@/lib/i18n';
import styles from './TimelinePanel.module.css';

export default function TimelinePanel({
  onNavigate,
}: {
  onNavigate?: (panel: 'claims', focus: { kind: 'claims'; topic?: string }) => void;
} = {}) {
  const t = useT();
  const [events, setEvents] = useState<TimelineEvent[]>([]);

  useEffect(() => {
    apiListTimeline().then(setEvents).catch(() => {});
  }, []);

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t('timeline.title')}</h1>
      </div>

      {events.length === 0 ? (
        <div className={styles.empty}>{t('timeline.empty')}</div>
      ) : (
        <>
      <div className={styles.list}>
        {events.map(ev => (
          <div key={ev.id} className={styles.event}>
            <div className={styles.date}>{ev.event_date}</div>
            <div className={styles.dot} />
            <div className={styles.content}>
              <div className={styles.eventTitle}>{ev.title}</div>
              {ev.description && <div className={styles.eventDesc}>{ev.description}</div>}
              {ev.topic && (
                <button
                  className={styles.topic}
                  title={onNavigate ? '查看该主题的论断' : undefined}
                  onClick={() => onNavigate?.('claims', { kind: 'claims', topic: ev.topic ?? undefined })}
                >
                  {ev.topic}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
        </>
      )}
    </div>
  );
}
