'use client';

import { useState, useEffect } from 'react';
import { apiListTimeline } from '@/lib/api';
import type { TimelineEvent } from '@/lib/api';
import { useT } from '@/lib/i18n';
import styles from './TimelinePanel.module.css';

export default function TimelinePanel() {
  const t = useT();
  const [events, setEvents] = useState<TimelineEvent[]>([]);

  useEffect(() => {
    apiListTimeline().then(setEvents).catch(() => {});
  }, []);

  if (events.length === 0) {
    return (
      <div className={styles.panel}>
        <div className={styles.empty}>{t('timeline.empty')}</div>
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t('timeline.title')}</h1>
      </div>
      <div className={styles.list}>
        {events.map(ev => (
          <div key={ev.id} className={styles.event}>
            <div className={styles.date}>{ev.event_date}</div>
            <div className={styles.dot} />
            <div className={styles.content}>
              <div className={styles.eventTitle}>{ev.title}</div>
              {ev.description && <div className={styles.eventDesc}>{ev.description}</div>}
              {ev.topic && <span className={styles.topic}>{ev.topic}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
