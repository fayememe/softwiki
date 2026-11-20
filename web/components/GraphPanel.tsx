'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { apiGraphOverview, apiGraphSubgraph, apiListGraph } from '@/lib/api';
import type { GraphEntity, GraphRelationship } from '@/lib/api';
import { useT } from '@/lib/i18n';
import styles from './GraphPanel.module.css';

/** A node as laid out on screen. */
interface Node {
  id: number;
  name: string;
  type: string;
  description: string | null;
  degree: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  /** True when the node was expanded by the user rather than seeded. */
  expanded: boolean;
}

interface Edge {
  id: number | string;
  source: string;
  target: string;
  type: string;
  description: string | null;
  confidence: number;
}

interface View {
  scale: number;
  tx: number;
  ty: number;
}

const TYPE_COLORS: Record<string, string> = {
  person: '#5588ff',
  character: '#5588ff',
  organization: '#22c55e',
  group: '#22c55e',
  concept: '#a78bfa',
  theme: '#a78bfa',
  event: '#f59e0b',
  location: '#22d3ee',
  place: '#22d3ee',
  work: '#ef4444',
  product: '#f472b6',
  topic: '#facc15',
};
const DEFAULT_COLOR = '#94a3b8';

const MIN_SCALE = 0.25;
const MAX_SCALE = 4;

function colorOf(type: string): string {
  return TYPE_COLORS[type] ?? DEFAULT_COLOR;
}

function typeLabel(entity: GraphEntity): string {
  return (entity.type || 'default').toLowerCase();
}

function radiusOf(degree: number): number {
  // sqrt keeps hub sizes readable without letting one node swallow the screen.
  return Math.min(22, 5 + Math.sqrt(Math.max(0, degree)) * 1.6);
}

/**
 * Force layout in a Web Worker-free but frame-bounded form.
 *
 * The previous implementation computed a full layout synchronously over every
 * node pair (O(n^2) per iteration, 80 iterations) inside render, which froze the
 * tab on real graphs. Here the work is bounded by the subgraph actually drawn,
 * runs off the render path, and integrates gradually so the picture animates
 * instead of appearing after a long stall.
 */
function simulate(nodes: Node[], edges: Edge[], width: number, height: number, ticks: number) {
  const byName = new Map(nodes.map((n) => [n.name, n]));
  const repulsion = 900;
  const spring = 0.02;
  const damping = 0.82;
  const center = 0.012;

  for (let tick = 0; tick < ticks; tick++) {
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let dist2 = dx * dx + dy * dy;
        if (dist2 < 0.01) {
          // Coincident nodes would divide by zero; nudge them apart.
          dx = Math.random() - 0.5;
          dy = Math.random() - 0.5;
          dist2 = dx * dx + dy * dy;
        }
        const dist = Math.sqrt(dist2);
        const force = repulsion / dist2;
        a.vx -= (dx / dist) * force;
        a.vy -= (dy / dist) * force;
        b.vx += (dx / dist) * force;
        b.vy += (dy / dist) * force;
      }
    }

    for (const edge of edges) {
      const s = byName.get(edge.source);
      const t = byName.get(edge.target);
      if (!s || !t) continue;
      const dx = t.x - s.x;
      const dy = t.y - s.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const ideal = 70 + s.radius + t.radius;
      const force = (dist - ideal) * spring;
      s.vx += (dx / dist) * force;
      s.vy += (dy / dist) * force;
      t.vx -= (dx / dist) * force;
      t.vy -= (dy / dist) * force;
    }

    for (const node of nodes) {
      node.vx += (width / 2 - node.x) * center;
      node.vy += (height / 2 - node.y) * center;
      node.vx *= damping;
      node.vy *= damping;
      node.x = Math.max(node.radius, Math.min(width - node.radius, node.x + node.vx));
      node.y = Math.max(node.radius, Math.min(height - node.radius, node.y + node.vy));
    }
  }
}

export default function GraphPanel() {
  const t = useT();
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [truncated, setTruncated] = useState(false);
  const [stats, setStats] = useState({ entities: 0, relationships: 0 });
  const [view, setView] = useState<View>({ scale: 1, tx: 0, ty: 0 });

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const nodesRef = useRef<Node[]>([]);
  const edgesRef = useRef<Edge[]>([]);
  const viewRef = useRef<View>(view);
  const dragRef = useRef<{ name: string; dx: number; dy: number } | null>(null);
  const panRef = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);
  const frameRef = useRef<number | null>(null);
  const sizeRef = useRef({ w: 800, h: 600 });

  nodesRef.current = nodes;
  edgesRef.current = edges;
  viewRef.current = view;

  /** Candidate list for the sidebar: search is backed by the full entity table. */
  const [allEntities, setAllEntities] = useState<GraphEntity[]>([]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiGraphOverview(80)
      .then((res) => {
        if (cancelled) return;
        const laid = res.entities.map((entity) => ({
          id: entity.id,
          name: entity.name,
          type: typeLabel(entity),
          description: entity.description,
          degree: entity.degree ?? 0,
          x: Math.random() * 400,
          y: Math.random() * 300,
          vx: 0,
          vy: 0,
          radius: radiusOf(entity.degree ?? 0),
          expanded: true,
        }));
        const wired: Edge[] = res.relationships.map((rel) => ({
          id: rel.id,
          source: rel.source_name,
          target: rel.target_name,
          type: rel.relation_type,
          description: rel.description,
          confidence: rel.confidence,
        }));
        setNodes(laid);
        setEdges(wired);
        setStats({
          entities: res.total_entities,
          relationships: res.total_relationships,
        });
        setError(null);
      })
      .catch((err: Error) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));

    // The sidebar needs names that are not in the drawn subset yet.
    apiListGraph()
      .then((res) => !cancelled && setAllEntities(res.entities))
      .catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, []);

  /** Merge one neighbourhood into the current picture. */
  const merge = useCallback((entities: GraphEntity[], relationships: GraphRelationship[]) => {
    const existing = new Set(nodesRef.current.map((n) => n.name));
    const added: Node[] = entities
      .filter((entity) => !existing.has(entity.name))
      .map((entity) => ({
        id: entity.id,
        name: entity.name,
        type: typeLabel(entity),
        description: entity.description,
        degree: 0,
        x: sizeRef.current.w / 2 + (Math.random() - 0.5) * 200,
        y: sizeRef.current.h / 2 + (Math.random() - 0.5) * 200,
        vx: 0,
        vy: 0,
        radius: 7,
        expanded: false,
      }));
    if (!added.length && !relationships.length) return;

    const known = new Set(edgesRef.current.map((e) => e.id));
    const newEdges: Edge[] = relationships
      .filter((rel) => !known.has(rel.id) && rel.source_name !== rel.target_name)
      .map((rel) => ({
        id: rel.id,
        source: rel.source_name,
        target: rel.target_name,
        type: rel.relation_type,
        description: rel.description,
        confidence: rel.confidence,
      }));

    setNodes([...nodesRef.current, ...added]);
    setEdges([...edgesRef.current, ...newEdges]);
  }, []);

  const expand = useCallback(
    (name: string) => {
      apiGraphSubgraph(name, 1, 40)
        .then((res) => {
          merge(res.entities, res.relationships);
          setTruncated((prev) => prev || res.truncated);
        })
        .catch((err: Error) => setError(err.message));
    },
    [merge],
  );

  // ── animation loop ────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let running = true;
    let settle = 0;

    const draw = () => {
      if (!running) return;
      const { w, h } = sizeRef.current;
      const dpr = window.devicePixelRatio || 1;
      if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
        canvas.width = Math.floor(w * dpr);
        canvas.height = Math.floor(h * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const list = nodesRef.current;
      const links = edgesRef.current;
      if (list.length && settle < 220) {
        simulate(list, links, w, h, 1);
        settle += 1;
      }

      const v = viewRef.current;
      ctx.save();
      ctx.translate(v.tx, v.ty);
      ctx.scale(v.scale, v.scale);

      const focus = hovered ?? selected;
      const neighbor = new Set<string>();
      if (focus) {
        neighbor.add(focus);
        for (const edge of links) {
          if (edge.source === focus) neighbor.add(edge.target);
          if (edge.target === focus) neighbor.add(edge.source);
        }
      }

      const byName = new Map(list.map((n) => [n.name, n]));

      for (const edge of links) {
        const s = byName.get(edge.source);
        const tg = byName.get(edge.target);
        if (!s || !tg) continue;
        const active = focus
          ? edge.source === focus || edge.target === focus
          : false;
        const dim = focus && !active;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(tg.x, tg.y);
        ctx.strokeStyle = active ? 'rgba(85,136,255,0.9)' : 'rgba(148,163,184,0.22)';
        ctx.lineWidth = active ? 2 : 1;
        ctx.globalAlpha = dim ? 0.15 : 1;
        ctx.stroke();

        if (active) {
          // Direction marker one third along, so the arrow reads at any zoom.
          const ratio = 0.12 + s.radius / 140;
          const ax = s.x + (tg.x - s.x) * ratio;
          const ay = s.y + (tg.y - s.y) * ratio;
          const angle = Math.atan2(tg.y - s.y, tg.x - s.x);
          ctx.beginPath();
          ctx.moveTo(ax, ay);
          ctx.lineTo(
            ax - 9 * Math.cos(angle - 0.4),
            ay - 9 * Math.sin(angle - 0.4),
          );
          ctx.lineTo(
            ax - 9 * Math.cos(angle + 0.4),
            ay - 9 * Math.sin(angle + 0.4),
          );
          ctx.closePath();
          ctx.fillStyle = 'rgba(85,136,255,0.9)';
          ctx.fill();
        }
      }
      ctx.globalAlpha = 1;

      for (const node of list) {
        const isFocus = focus === node.name;
        const close = neighbor.has(node.name);
        const dim = focus && !close;
        ctx.globalAlpha = dim ? 0.2 : 1;

        if (isFocus || close) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, node.radius + 6, 0, Math.PI * 2);
          ctx.strokeStyle = isFocus ? 'rgba(255,255,255,0.75)' : 'rgba(85,136,255,0.45)';
          ctx.lineWidth = isFocus ? 2 : 1.5;
          ctx.stroke();
        }

        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
        const gradient = ctx.createRadialGradient(
          node.x - node.radius / 3,
          node.y - node.radius / 3,
          node.radius / 6,
          node.x,
          node.y,
          node.radius,
        );
        const base = colorOf(node.type);
        gradient.addColorStop(0, '#ffffff');
        gradient.addColorStop(0.35, base);
        gradient.addColorStop(1, base);
        ctx.fillStyle = gradient;
        ctx.fill();
        if (isFocus) {
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 2;
          ctx.stroke();
        }

        const showLabel = isFocus || close || (!focus && node.radius >= 9) || v.scale > 1.4;
        if (showLabel) {
          ctx.font = `${isFocus ? 600 : 400} 11px system-ui, sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillStyle = isFocus ? '#ffffff' : 'rgba(226,232,240,0.85)';
          const label = node.name.length > 22 ? `${node.name.slice(0, 20)}…` : node.name;
          ctx.fillText(label, node.x, node.y + node.radius + 10);
        }
      }
      ctx.globalAlpha = 1;
      ctx.restore();

      frameRef.current = requestAnimationFrame(draw);
    };

    frameRef.current = requestAnimationFrame(draw);
    return () => {
      running = false;
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [hovered, selected]);

  // ── sizing ────────────────────────────────────────────────────────────
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const observer = new ResizeObserver(() => {
      const rect = wrap.getBoundingClientRect();
      sizeRef.current = { w: Math.max(240, rect.width), h: Math.max(240, rect.height) };
    });
    observer.observe(wrap);
    const rect = wrap.getBoundingClientRect();
    sizeRef.current = { w: Math.max(240, rect.width), h: Math.max(240, rect.height) };
    return () => observer.disconnect();
  }, []);

  // ── hit testing ───────────────────────────────────────────────────────
  const hitTest = useCallback((clientX: number, clientY: number): Node | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const v = viewRef.current;
    const x = (clientX - rect.left - v.tx) / v.scale;
    const y = (clientY - rect.top - v.ty) / v.scale;
    let best: Node | null = null;
    let bestDist = Infinity;
    for (const node of nodesRef.current) {
      const dist = Math.hypot(node.x - x, node.y - y);
      if (dist <= node.radius + 6 && dist < bestDist) {
        best = node;
        bestDist = dist;
      }
    }
    return best;
  }, []);

  const localPoint = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const v = viewRef.current;
    return {
      x: (clientX - rect.left - v.tx) / v.scale,
      y: (clientY - rect.top - v.ty) / v.scale,
    };
  }, []);

  const onPointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const hit = hitTest(event.clientX, event.clientY);
    if (hit) {
      const point = localPoint(event.clientX, event.clientY);
      dragRef.current = { name: hit.name, dx: hit.x - point.x, dy: hit.y - point.y };
      setSelected(hit.name);
    } else {
      const v = viewRef.current;
      panRef.current = { x: event.clientX, y: event.clientY, tx: v.tx, ty: v.ty };
    }
  };

  const onPointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = event.currentTarget;
    if (dragRef.current) {
      const point = localPoint(event.clientX, event.clientY);
      const name = dragRef.current.name;
      setNodes((prev) =>
        prev.map((node) =>
          node.name === name
            ? { ...node, x: point.x + dragRef.current!.dx, y: point.y + dragRef.current!.dy, vx: 0, vy: 0 }
            : node,
        ),
      );
      return;
    }
    if (panRef.current) {
      const dx = event.clientX - panRef.current.x;
      const dy = event.clientY - panRef.current.y;
      setView((v) => ({ ...v, tx: panRef.current!.tx + dx, ty: panRef.current!.ty + dy }));
      return;
    }
    const hit = hitTest(event.clientX, event.clientY);
    const name = hit?.name ?? null;
    if (name !== hovered) setHovered(name);
    canvas.style.cursor = hit ? 'pointer' : 'grab';
  };

  const onPointerUp = () => {
    dragRef.current = null;
    panRef.current = null;
  };

  const onDoubleClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const hit = hitTest(event.clientX, event.clientY);
    if (hit) expand(hit.name);
  };

  const onWheel = (event: React.WheelEvent<HTMLCanvasElement>) => {
    event.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    const v = viewRef.current;
    const factor = Math.exp(-event.deltaY * 0.0015);
    const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale * factor));
    // Keep the point under the cursor fixed while zooming.
    const tx = px - ((px - v.tx) / v.scale) * scale;
    const ty = py - ((py - v.ty) / v.scale) * scale;
    setView({ scale, tx, ty });
  };

  const focusNode = (name: string) => {
    setSelected(name);
    const node = nodesRef.current.find((n) => n.name === name);
    if (!node) {
      expand(name);
      return;
    }
    const { w, h } = sizeRef.current;
    const scale = Math.max(1.1, viewRef.current.scale);
    setView({ scale, tx: w / 2 - node.x * scale, ty: h / 2 - node.y * scale });
  };

  // ── sidebar list ──────────────────────────────────────────────────────
  const candidates = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const pool = allEntities.length ? allEntities : (nodes as unknown as GraphEntity[]);
    const filtered = needle
      ? pool.filter((entity) => entity.name.toLowerCase().includes(needle))
      : pool;
    return filtered
      .slice()
      .sort((a, b) => a.name.localeCompare(b.name))
      .slice(0, 300);
  }, [allEntities, nodes, search]);

  const selectedNode = selected ? nodes.find((n) => n.name === selected) : null;
  const selectedEdges = selected
    ? edges.filter((e) => e.source === selected || e.target === selected)
    : [];

  return (
    <div className={styles.panel}>
      <div className={styles.sidebar}>
        <input
          className={styles.search}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('graph.searchPlaceholder')}
        />
        <div className={styles.hint}>
          {t('graph.shown', { shown: nodes.length, total: stats.entities })}
        </div>
        <div className={styles.entityList}>
          {candidates.map((entity) => (
            <button
              key={entity.id}
              className={`${styles.entityItem} ${selected === entity.name ? styles.entityActive : ''}`}
              onClick={() => focusNode(entity.name)}
              title={entity.name}
            >
              <span
                className={styles.entityDot}
                style={{ background: colorOf(typeLabel(entity)) }}
              />
              <span className={styles.entityName}>{entity.name}</span>
            </button>
          ))}
        </div>
        <button className={styles.resetButton} onClick={() => setView({ scale: 1, tx: 0, ty: 0 })}>
          {t('graph.resetView')}
        </button>
      </div>

      <div className={styles.graphArea} ref={wrapRef}>
        <canvas
          ref={canvasRef}
          className={styles.canvas}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={() => setHovered(null)}
          onDoubleClick={onDoubleClick}
          onWheel={onWheel}
        />
        {loading && <div className={styles.overlay}>{t('graph.loading')}</div>}
        {error && !loading && <div className={styles.overlay}>{error}</div>}
        {!loading && !error && !nodes.length && (
          <div className={styles.overlay}>{t('graph.empty')}</div>
        )}
        {truncated && <div className={styles.badge}>{t('graph.truncated')}</div>}
        <div className={styles.legend}>
          {Object.keys(TYPE_COLORS)
            .slice(0, 6)
            .map((type) => (
              <span key={type} className={styles.legendItem}>
                <span className={styles.entityDot} style={{ background: TYPE_COLORS[type] }} />
                {type}
              </span>
            ))}
        </div>
      </div>

      {selectedNode && (
        <div className={styles.detail}>
          <div className={styles.detailHeader}>
            <span className={styles.detailDot} style={{ background: colorOf(selectedNode.type) }} />
            <span className={styles.detailName}>{selectedNode.name}</span>
            <span className={styles.detailType}>{selectedNode.type}</span>
          </div>
          {selectedNode.description && (
            <p className={styles.detailDescription}>{selectedNode.description}</p>
          )}
          <div className={styles.detailActions}>
            <button className={styles.actionButton} onClick={() => expand(selectedNode.name)}>
              {t('graph.expand')}
            </button>
            <button
              className={styles.actionButton}
              onClick={() => {
                setNodes((prev) => prev.filter((n) => n.name === selectedNode.name || n.expanded));
                setEdges((prev) =>
                  prev.filter(
                    (e) =>
                      e.source === selectedNode.name ||
                      e.target === selectedNode.name ||
                      nodesRef.current.find((n) => n.name === e.source)?.expanded ||
                      nodesRef.current.find((n) => n.name === e.target)?.expanded,
                  ),
                );
              }}
            >
              {t('graph.prune')}
            </button>
          </div>
          <div className={styles.detailRels}>
            {selectedEdges.slice(0, 60).map((edge) => (
              <div key={edge.id} className={styles.detailRel}>
                <span className={styles.detailRelName}>{edge.source}</span>
                <span className={styles.relArrow}>{edge.type}</span>
                <span className={styles.detailRelName}>{edge.target}</span>
              </div>
            ))}
            {!selectedEdges.length && <div className={styles.hint}>{t('graph.noRelations')}</div>}
          </div>
        </div>
      )}
    </div>
  );
}
