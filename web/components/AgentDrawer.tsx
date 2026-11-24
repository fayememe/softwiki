'use client';

/**
 * Right-hand agent drawer.
 *
 * Opens next to whatever the user is looking at, with an explicit context chip
 * (kb / panel / subject) that is prepended to the first message. Nothing is
 * hidden in a system prompt: the agent's context is the same text the user can
 * read, and removing the chip removes the context.
 *
 * Pending proposals (agent found something, human must decide) are shown here
 * too — approving executes server-side, so the agent does not have to stay
 * alive waiting for a click.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AgentMessageView from './chat/AgentMessageView';
import { useAgentChat } from './chat/useAgentChat';
import type { AgentContextPayload } from './AgentDrawerContext';
import styles from './AgentDrawer.module.css';

interface PendingPlan {
  id: number;
  kind: string;
  proposed_by?: string;
  reason?: string;
  subjects: string[];
}

interface AgentDrawerProps {
  context: AgentContextPayload | null;
  onClose: () => void;
}

function contextLine(ctx: AgentContextPayload): string {
  const bits = [
    ctx.kb ? `kb=${ctx.kb}` : null,
    `panel=${ctx.panel}`,
    ctx.subject ? `subject=${ctx.subject}` : null,
    ctx.detail ? ctx.detail : null,
  ].filter(Boolean);
  return `[context: ${bits.join(' · ')}]`;
}

export default function AgentDrawer({ context, onClose }: AgentDrawerProps) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState('');
  const [width, setWidth] = useState(420);
  const [plans, setPlans] = useState<PendingPlan[]>([]);
  const [contextDropped, setContextDropped] = useState(false);
  const [acting, setActing] = useState(false);
  const [me, setMe] = useState<{ role?: string; capabilities?: string[] } | null>(null);
  const [showAbout, setShowAbout] = useState(false);
  const [actionError, setActionError] = useState('');
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  const chat = useAgentChat({
    agentSessionId: sessionId,
    onSessionCreated: (id) => setSessionId(id),
  });

  // A new context means a new conversation: reusing one would drag old
  // conclusions into a different subject.
  useEffect(() => {
    setSessionId(null);
    setInput('');
    setContextDropped(false);
    setPlans([]);
  }, [context?.kb, context?.panel, context?.subject]);

  useEffect(() => {
    fetch('/api/permissions', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setMe({ role: d.role, capabilities: d.capabilities || [] }))
      .catch(() => setMe(null));
  }, []);

  const canApprove = (me?.capabilities || []).some((c) => c === '*' || c.startsWith('wiki.apply'));

  const loadPlans = useCallback(async () => {
    const data = await fetch('/api/wiki/plans?status=pending', { cache: 'no-store' })
      .then((r) => r.json())
      .catch(() => null);
    if (data) setPlans(data.plans || []);
  }, []);

  useEffect(() => {
    void loadPlans();
  }, [loadPlans, chat.messages.length]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat.messages.length, chat.busy]);

  // Drag to resize; stored only for this mount.
  useEffect(() => {
    const onMove = (e: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const next = drag.startWidth + (drag.startX - e.clientX);
      setWidth(Math.min(760, Math.max(320, next)));
    };
    const onUp = () => { dragRef.current = null; };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
  }, []);

  const showContext = context && !contextDropped;

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || chat.busy) return;
    setInput('');
    const first = chat.messages.length === 0;
    const payload = first && showContext && context
      ? `${contextLine(context)}\n\n${text}`
      : text;
    await chat.send(payload);
    await loadPlans();
  }, [input, chat, showContext, context, loadPlans]);

  const decide = useCallback(async (id: number, approve: boolean) => {
    setActing(true);
    setActionError('');
    try {
      const res = await fetch(`/api/wiki/plans/${id}/${approve ? 'approve' : 'reject'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: '' }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      await loadPlans();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not update the plan');
    } finally {
      setActing(false);
    }
  }, [loadPlans]);

  const messages = useMemo(() => chat.messages, [chat.messages]);

  return (
    <aside className={styles.drawer} style={{ width }} aria-label="Assistant">
      <button
        className={styles.resizer}
        onPointerDown={(e) => {
          dragRef.current = { startX: e.clientX, startWidth: width };
        }}
        aria-label="Resize"
      />

      <header className={styles.head}>
        <span className={styles.title}>Assistant</span>
        {context?.kb && <span className={styles.chip}>{context.kb}</span>}
        {context?.panel && <span className={styles.chip}>{context.panel}</span>}
        {me?.role && <span className={styles.role}>{me.role.replace('wiki-', '')}</span>}
        <button
          className={styles.help}
          onClick={() => setShowAbout((v) => !v)}
          title="What this assistant can and cannot do"
        >?</button>
        <button className={styles.close} onClick={onClose} aria-label="Close">✕</button>
      </header>

      {plans.length > 0 && (
        <div className={styles.plans}>
          {plans.map((plan) => (
            <div key={plan.id} className={styles.plan}>
              <div className={styles.planText}>
                <strong>Plan #{plan.id}</strong> · {plan.kind.replace('_', ' ')} ·{' '}
                {plan.subjects.length} subject(s)
                {plan.reason ? <div className={styles.planReason}>{plan.reason}</div> : null}
                <div className={styles.planSubjects}>{plan.subjects.slice(0, 8).join(', ')}</div>
              </div>
              <div className={styles.planActions}>
                <button className={styles.approve} disabled={acting}
                        onClick={() => void decide(plan.id, true)}>
                  Approve
                </button>
                <button className={styles.reject} disabled={acting}
                        onClick={() => void decide(plan.id, false)}>
                  Reject
                </button>
              </div>
            </div>
          ))}
          {actionError && <div className={styles.error}>{actionError}</div>}
        </div>
      )}

      {showAbout && (
        <div className={styles.about}>
          <div className={styles.aboutRow}>
            <strong>What this is</strong>
            An assistant bound to the view you have open — not the global Chat.
            Switching subject starts a fresh conversation.
          </div>
          <div className={styles.aboutRow}>
            <strong>You are</strong>
            {me?.role ? `${me.role}` : 'unknown role'}
            {context?.kb ? ` on ${context.kb}` : ''}. It answers with your
            permissions and cannot see knowledge bases outside your scope.
          </div>
          <div className={styles.aboutRow}>
            <strong>It can</strong>
            read claims, pages, graph and timeline of this kb; search; explain
            what is wrong; <em>propose</em> deletions or rewrites.
          </div>
          <div className={styles.aboutRow}>
            <strong>It cannot</strong>
            approve its own proposals, change claim facts, or touch another kb.
          </div>
          <div className={styles.aboutRow}>
            <strong>Approval</strong>
            {canApprove
              ? 'You can approve plans here — approving executes them immediately.'
              : 'Your role cannot approve; a Manage/Admin user must do it.'}
          </div>
        </div>
      )}

      <div className={styles.body}>
        {messages.length === 0 && (
          <div className={styles.empty}>
            <div className={styles.emptyTitle}>
              Looking at {context?.kb || 'this kb'}
              {context?.subject ? ` › ${context.subject}` : ''}
            </div>
            <div>
              Ask what is wrong with it, or tell it what should change. It reads
              this kb only, proposes changes as a plan, and you approve them.
            </div>
            <div className={styles.suggestions}>
              <button onClick={() => setInput('Is this page worth keeping? Check its claims.')}>
                Is this page worth keeping?
              </button>
              <button onClick={() => setInput('Which pages in this kb look too generic or redundant?')}>
                Find low-value pages
              </button>
            </div>
          </div>
        )}
        {messages.map((message) => (
          <AgentMessageView key={message.info.id} message={message} streaming={chat.busy} />
        ))}
        <div ref={bottomRef} />
      </div>

      {showContext && context && (
        <div className={styles.contextBar}>
          <span>{contextLine(context)}</span>
          <button onClick={() => setContextDropped(true)} aria-label="Remove context">✕</button>
        </div>
      )}

      <div className={styles.composer}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask, or describe what should change…"
          rows={2}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <div className={styles.composerActions}>
          {chat.busy ? (
            <button className={styles.stop} onClick={() => void chat.stop()}>Stop</button>
          ) : (
            <button className={styles.send} onClick={() => void send()}
                    disabled={!input.trim() || !chat.connected && false}>
              Send
            </button>
          )}
        </div>
      </div>
      {chat.error && <div className={styles.error}>{chat.error}</div>}
    </aside>
  );
}
