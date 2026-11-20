'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  apiCreateKb,
  apiKbRegistry,
  apiKbTemplates,
  apiRegisterKb,
  apiUnregisterKb,
} from '@/lib/kb-api';
import type { KbCreatePlan, KbRegistryRow } from '@/lib/kb-api';
import { useT } from '@/lib/i18n';
import styles from './KbWizardPanel.module.css';

const NAME_PATTERN = /^[A-Za-z0-9._-]{1,64}$/;

function validate(name: string): string | null {
  const value = name.trim();
  if (!value) return 'name-required';
  if (!NAME_PATTERN.test(value)) return 'name-invalid';
  if (value.startsWith('.')) return 'name-invalid';
  return null;
}

export default function KbWizardPanel() {
  const t = useT();
  const [step, setStep] = useState(1);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [language, setLanguage] = useState('zh');
  const [template, setTemplate] = useState('generic');
  const [templates, setTemplates] = useState<{ name: string; has_files: boolean }[]>([]);
  const [plan, setPlan] = useState<KbCreatePlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [registry, setRegistry] = useState<KbRegistryRow[]>([]);

  const loadRegistry = useCallback(() => {
    apiKbRegistry()
      .then((res) => setRegistry(res.kbs))
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    apiKbTemplates()
      .then((res) => setTemplates(res.templates))
      .catch(() => setTemplates([{ name: 'generic', has_files: false }]));
    loadRegistry();
  }, [loadRegistry]);

  const nameError = validate(name);

  const preview = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await apiCreateKb({
        name: name.trim(),
        template,
        description,
        language,
        dry_run: true,
      });
      setPlan(res.plan);
      setStep(3);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await apiCreateKb({
        name: name.trim(),
        template,
        description,
        language,
        dry_run: false,
      });
      setDone(res.result?.name ?? name.trim());
      setPlan(null);
      setStep(1);
      setName('');
      setDescription('');
      loadRegistry();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const toggleRegistration = async (row: KbRegistryRow) => {
    setBusy(true);
    setError(null);
    try {
      if (row.status === 'registered') {
        await apiUnregisterKb(row.name);
      } else {
        await apiRegisterKb(row.name);
      }
      loadRegistry();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={styles.panel}>
      <header className={styles.header}>
        <h2 className={styles.title}>{t('kbWizard.title')}</h2>
        <p className={styles.subtitle}>{t('kbWizard.subtitle')}</p>
      </header>

      {done && (
        <div className={styles.success}>
          {t('kbWizard.created', { name: done })}
          <button className={styles.linkButton} onClick={() => setDone(null)}>
            ×
          </button>
        </div>
      )}
      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.steps}>
        {[1, 2, 3].map((n) => (
          <span
            key={n}
            className={`${styles.step} ${step === n ? styles.stepActive : ''} ${step > n ? styles.stepDone : ''}`}
          >
            {n}. {t(`kbWizard.step${n}`)}
          </span>
        ))}
      </div>

      {step === 1 && (
        <section className={styles.card}>
          <label className={styles.field}>
            <span className={styles.label}>{t('kbWizard.name')}</span>
            <input
              className={styles.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('kbWizard.namePlaceholder')}
              autoFocus
            />
            <span className={styles.help}>
              {nameError ? t(`kbWizard.${nameError}`) : t('kbWizard.nameHelp')}
            </span>
          </label>
          <label className={styles.field}>
            <span className={styles.label}>{t('kbWizard.description')}</span>
            <textarea
              className={styles.textarea}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t('kbWizard.descriptionPlaceholder')}
              rows={3}
            />
            <span className={styles.help}>{t('kbWizard.descriptionHelp')}</span>
          </label>
          <div className={styles.row}>
            <label className={styles.field}>
              <span className={styles.label}>{t('kbWizard.template')}</span>
              <select
                className={styles.input}
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
              >
                {templates.map((tpl) => (
                  <option key={tpl.name} value={tpl.name}>
                    {tpl.name}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span className={styles.label}>{t('kbWizard.language')}</span>
              <select
                className={styles.input}
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
              >
                <option value="zh">中文</option>
                <option value="en">English</option>
                <option value="ja">日本語</option>
              </select>
            </label>
          </div>
          <div className={styles.actions}>
            <button className={styles.primary} disabled={!!nameError || busy} onClick={preview}>
              {t('kbWizard.preview')}
            </button>
          </div>
        </section>
      )}

      {step === 3 && plan && (
        <section className={styles.card}>
          <h3 className={styles.cardTitle}>{t('kbWizard.planTitle', { name: plan.name })}</h3>
          <p className={styles.help}>{t('kbWizard.planHelp')}</p>
          <ul className={styles.planList}>
            {plan.steps.map((item, index) => (
              <li key={`${item.kind}-${index}`} className={styles.planItem}>
                <span className={styles.planKind}>{item.kind}</span>
                <span className={styles.planText}>{item.description}</span>
                {item.exists && <span className={styles.planWarn}>{t('kbWizard.exists')}</span>}
              </li>
            ))}
          </ul>
          {plan.warnings.length > 0 && (
            <ul className={styles.warnings}>
              {plan.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
          <div className={styles.actions}>
            <button className={styles.secondary} onClick={() => setStep(1)} disabled={busy}>
              {t('kbWizard.back')}
            </button>
            <button className={styles.primary} onClick={create} disabled={busy}>
              {t('kbWizard.create')}
            </button>
          </div>
        </section>
      )}

      <section className={styles.card}>
        <h3 className={styles.cardTitle}>{t('kbWizard.registryTitle')}</h3>
        <p className={styles.help}>{t('kbWizard.registryHelp')}</p>
        <div className={styles.registry}>
          {registry.map((row) => (
            <div key={row.name} className={styles.registryRow}>
              <span
                className={`${styles.status} ${row.status === 'registered' ? styles.statusOn : styles.statusOff}`}
              >
                {row.status === 'registered' ? t('kbWizard.registered') : t('kbWizard.unregistered')}
              </span>
              <span className={styles.registryName}>{row.name}</span>
              <span className={styles.registryMeta}>{row.template}</span>
              {row.created_at && <span className={styles.registryMeta}>{row.created_at}</span>}
              <button
                className={styles.linkButton}
                disabled={busy}
                onClick={() => toggleRegistration(row)}
              >
                {row.status === 'registered' ? t('kbWizard.unhook') : t('kbWizard.rehook')}
              </button>
            </div>
          ))}
          {!registry.length && <div className={styles.help}>{t('kbWizard.registryEmpty')}</div>}
        </div>
      </section>
    </div>
  );
}
