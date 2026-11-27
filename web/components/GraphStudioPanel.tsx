'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import styles from './GraphStudioPanel.module.css';

/* ---------- API types ---------- */

interface ApiEntity {
  id: number;
  name: string;
  type: string | null;
  description: string | null;
  degree?: number;
}

interface ApiRel {
  id: number;
  source_name: string;
  target_name: string;
  source_entity_id?: number | null;
  target_entity_id?: number | null;
  relation_type: string;
  description: string | null;
  confidence: number;
  weight?: number | null;
  evidence_count?: number | null;
  canonical_claim_id?: string | null;
  document_title?: string | null;
  document_id?: number | null;
  published_at?: string;
}

interface SubgraphResponse {
  root: string;
  entities: ApiEntity[];
  relationships: ApiRel[];
  truncated: boolean;
}

interface SearchItem {
  id: number;
  name: string;
  type: string | null;
  degree: number;
  matched_alias: string | null;
}

interface EntityClaim {
  id: string;
  text: string;
  actor: string;
  topic: string;
  status: string;
  confidence: number;
  evidence_count: number;
  page_start: number | null;
  page_end: number | null;
}

interface EntityDetail {
  entity: {
    id: number;
    name: string;
    type: string | null;
    description: string | null;
    aliases: string[];
    merged_from: string[];
  };
  degree: number;
  edges: ApiRel[];
  claims: EntityClaim[];
  wiki: { slug: string; content: string } | null;
}

interface PathResponse {
  nodes: { id: number; name: string; type: string | null }[];
  edges: ApiRel[];
  hops: number;
}

/* ---------- layout types ---------- */

interface Node extends ApiEntity {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  fixed?: boolean;
}

interface Edge {
  id: number;
  source: string;
  target: string;
  type: string;
  confidence: number;
  weight: number;
  claimId: string | null;
  documentTitle: string | null;
}

const TYPE_COLORS: Record<string, string> = {
  product: '#f472b6',
  ip_block: '#fb923c',
  architecture: '#60a5fa',
  protocol: '#34d399',
  instruction_set: '#a78bfa',
  feature: '#facc15',
  register: '#22d3ee',
  component: '#2dd4bf',
  standard: '#c084fc',
  organization: '#4ade80',
  concept: '#94a3b8',
  other: '#64748b',
};

const DEFAULT_COLOR = '#94a3b8';

function colorOf(type: string | null): string {
  return TYPE_COLORS[(type || 'other').toLowerCase()] ?? DEFAULT_COLOR;
}

function edgeKey(rel: ApiRel): number {
  return rel.id;
}

export default function GraphStudioPanel({
  onNavigate,
  focus,
}: {
  onNavigate?: (panel: 'claims', focus: { kind: 'claims'; q?: string; actor?: string }) => void;
  focus?: { kind: 'entity'; name: string } | { kind: 'claims' } | { kind: 'document'; documentId: number };
} = {}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const nodesRef = useRef<Map<string, Node>>(new Map());
  const edgesRef = useRef<Map<number, Edge>>(new Map());
  const viewRef = useRef({ scale: 1, tx: 0, ty: 0 });
  const animRef = useRef<number | null>(null);
  const dragRef = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);
  const fittedRef = useRef(false);
  const drawRef = useRef<(() => void) | null>(null);

  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const [stats, setStats] = useState<{ entities: number; relationships: number } | null>(null);
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<SearchItem[]>([]);
  const [pathFrom, setPathFrom] = useState('');
  const [pathTo, setPathTo] = useState('');
  const [path, setPath] = useState<PathResponse | null>(null);
  const [pathError, setPathError] = useState<string | null>(null);
  const [status, setStatus] = useState('Loading graph…');

  // A link from another panel: focus that entity in the canvas.
  useEffect(() => {
    if (!focus || focus.kind !== 'entity') return;
    const name = focus.name;
    const timer = setTimeout(() => {
      setQuery(name);
      void openEntity(name).then(() => expand(name)).catch(() => {});
    }, 200);
    return () => clearTimeout(timer);
  }, [focus]);

  // keep refs in sync for the render loop
  useEffect(() => {
    nodesRef.current = new Map(nodes.map((n) => [n.name, n]));
  }, [nodes]);
  useEffect(() => {
    edgesRef.current = new Map(edges.map((e) => [e.id, e]));
  }, [edges]);

  /* ---------- data loading ---------- */

  const mergeSubgraph = useCallback((body: SubgraphResponse) => {
    setNodes((prev) => {
      const map = new Map(prev.map((n) => [n.name, n]));
      // New nodes appear next to the entity they were expanded from. Random
      // placement in a 400px box made the layout lurch on every expand.
      const anchor = map.get(body.root) ?? null;
      for (const ent of body.entities) {
        if (map.has(ent.name)) continue;
        map.set(ent.name, {
          ...ent,
          x: (anchor?.x ?? 0) + (Math.random() - 0.5) * 120,
          y: (anchor?.y ?? 0) + (Math.random() - 0.5) * 120,
          vx: 0,
          vy: 0,
          radius: 6,
        });
      }
      return Array.from(map.values());
    });
    setEdges((prev) => {
      const map = new Map(prev.map((e) => [e.id, e]));
      for (const rel of body.relationships) {
        map.set(edgeKey(rel), {
          id: edgeKey(rel),
          source: rel.source_name,
          target: rel.target_name,
          type: rel.relation_type,
          confidence: rel.confidence,
          weight: rel.weight ?? 1,
          claimId: rel.canonical_claim_id ?? null,
          documentTitle: rel.document_title ?? null,
        });
      }
      return Array.from(map.values());
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [overviewRes, statusRes] = await Promise.all([
          fetch('/api/graph/overview?limit=45'),
          fetch('/api/status'),
        ]);
        if (!overviewRes.ok) throw new Error(`overview ${overviewRes.status}`);
        const overview = await overviewRes.json();
        if (cancelled) return;
        setNodes(
          (overview.entities as ApiEntity[]).map((ent) => ({
            ...ent,
            x: (Math.random() - 0.5) * 600,
            y: (Math.random() - 0.5) * 420,
            vx: 0,
            vy: 0,
            radius: Math.min(20, 6 + Math.log2(1 + (ent.degree ?? 1)) * 4),
          })),
        );
        setEdges(
          (overview.relationships as ApiRel[]).map((rel) => ({
            id: edgeKey(rel),
            source: rel.source_name,
            target: rel.target_name,
            type: rel.relation_type,
            confidence: rel.confidence,
            weight: rel.weight ?? 1,
            claimId: rel.canonical_claim_id ?? null,
            documentTitle: rel.document_title ?? null,
          })),
        );
        setStatus('');
        if (statusRes.ok) {
          const s = await statusRes.json();
          setStats({ entities: s.counts?.entities ?? 0, relationships: s.counts?.relationships ?? 0 });
        }
      } catch (err) {
        if (!cancelled) setStatus(`Failed to load graph: ${String(err)}`);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const expand = useCallback(
    async (name: string) => {
      try {
        const res = await fetch(
          `/api/graph/subgraph?entity=${encodeURIComponent(name)}&depth=1&limit=80`,
        );
        if (!res.ok) return;
        const body: SubgraphResponse = await res.json();
        mergeSubgraph(body);
      } catch {
        /* keep the current graph */
      }
    },
    [mergeSubgraph],
  );

  const openEntity = useCallback(
    async (name: string) => {
      setSelected(name);
      setDetailLoading(true);
      try {
        const res = await fetch(`/api/graph/entity?name=${encodeURIComponent(name)}`);
        if (!res.ok) {
          setDetail(null);
          return;
        }
        setDetail(await res.json());
      } finally {
        setDetailLoading(false);
      }
    },
    [],
  );

  /* ---------- search ---------- */

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setSuggestions([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/graph/search?q=${encodeURIComponent(q)}&limit=10`);
        if (!res.ok) return;
        const body = await res.json();
        setSuggestions(body.items ?? []);
      } catch {
        setSuggestions([]);
      }
    }, 180);
    return () => clearTimeout(timer);
  }, [query]);

  /* ---------- force layout ---------- */

  useEffect(() => {
    let ticks = 0;
    // After an expand, keep the current pan/zoom unless something new landed
    // outside the viewport.
    const anyNodeOffscreen = () => {
      const wrap = wrapRef.current;
      if (!wrap) return false;
      const { scale, tx, ty } = viewRef.current;
      const halfW = (wrap.clientWidth / (2 * scale)) * 1.05;
      const halfH = (wrap.clientHeight / (2 * scale)) * 1.05;
      const cx = -tx / scale;
      const cy = -ty / scale;
      for (const n of nodesRef.current.values()) {
        if (Math.abs(n.x - cx) > halfW || Math.abs(n.y - cy) > halfH) return true;
      }
      return false;
    };
    const step = () => {
      ticks += 1;
      const ns = nodesRef.current;
      const es = edgesRef.current;
      const arr = Array.from(ns.values());
      // Layout constants. The previous version used unbounded 1/d² repulsion
      // and no velocity cap, so two near-coincident nodes produced a huge
      // impulse and the cloud drifted outward forever.
      const MIN_DIST2 = 900;      // 30px floor between any two nodes
      const MAX_PAIR_FORCE = 42;  // per pair, per tick
      const DAMPING = 0.9;
      const MAX_SPEED = 6;        // world units per tick
      const CENTER_PULL = 0.0018; // keeps disconnected islands on screen
      const BOUND = 2600;         // soft world bound

      // repulsion
      for (let i = 0; i < arr.length; i += 1) {
        for (let j = i + 1; j < arr.length; j += 1) {
          const a = arr[i];
          const b = arr[j];
          let dx = b.x - a.x;
          let dy = b.y - a.y;
          let dist2 = dx * dx + dy * dy;
          if (dist2 < 1) {
            dx = (Math.random() - 0.5) * 2;
            dy = (Math.random() - 0.5) * 2;
            dist2 = dx * dx + dy * dy;
          }
          const dist = Math.sqrt(dist2);
          const force = Math.min(MAX_PAIR_FORCE, 2600 / Math.max(dist2, MIN_DIST2));
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx -= fx;
          a.vy -= fy;
          b.vx += fx;
          b.vy += fy;
        }
      }
      for (const e of es.values()) {
        const a = ns.get(e.source);
        const b = ns.get(e.target);
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        const target = 90;
        const force = Math.max(-MAX_PAIR_FORCE, Math.min(MAX_PAIR_FORCE, (dist - target) * 0.012));
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
      let maxSpeed = 0;
      for (const n of arr) {
        // gravity towards the origin, then damping, then a hard speed limit
        n.vx -= n.x * CENTER_PULL;
        n.vy -= n.y * CENTER_PULL;
        n.vx *= DAMPING;
        n.vy *= DAMPING;
        const speed = Math.hypot(n.vx, n.vy);
        if (speed > MAX_SPEED) {
          n.vx = (n.vx / speed) * MAX_SPEED;
          n.vy = (n.vy / speed) * MAX_SPEED;
        } else if (speed > maxSpeed) {
          maxSpeed = speed;
        }
        n.x += n.vx;
        n.y += n.vy;
        if (n.x > BOUND) { n.x = BOUND; n.vx = 0; }
        if (n.x < -BOUND) { n.x = -BOUND; n.vx = 0; }
        if (n.y > BOUND) { n.y = BOUND; n.vy = 0; }
        if (n.y < -BOUND) { n.y = -BOUND; n.vy = 0; }
      }
      // Fit the initial cloud to the viewport once the layout has settled.
      if (!fittedRef.current && ticks === 90) fitViewRef.current?.();
      if (fittedRef.current && ticks === 120 && anyNodeOffscreen()) fitViewRef.current?.();
      draw();
      // Stop once the layout is quiet instead of burning 320 frames.
      if (ticks < 320 && (ticks < 60 || maxSpeed > 0.05)) {
        animRef.current = requestAnimationFrame(step);
      } else {
        animRef.current = null;
      }
    };
    if (animRef.current !== null) cancelAnimationFrame(animRef.current);
    animRef.current = requestAnimationFrame(step);
    return () => {
      if (animRef.current !== null) cancelAnimationFrame(animRef.current);
      animRef.current = null;
    };
  }, [nodes.length, edges.length]);

  /* ---------- rendering ---------- */

  const pathNames = useMemo(() => new Set((path?.nodes ?? []).map((n) => n.name)), [path]);
  const pathEdgeIds = useMemo(() => new Set((path?.edges ?? []).map((e) => e.id)), [path]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const dpr = window.devicePixelRatio || 1;
    const width = wrap.clientWidth;
    const height = wrap.clientHeight;
    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr;
      canvas.height = height * dpr;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    // Canvas colours follow the active theme; read the tokens the CSS module
    // exposes on the wrapper instead of hardcoding a dark palette.
    const css = getComputedStyle(wrap);
    const token = (name: string, fallback: string) =>
      css.getPropertyValue(name).trim() || fallback;
    const canvasBg = token('--graph-canvas-bg', '#0b1220');
    const edgeColor = token('--graph-edge', 'rgba(148,163,184,0.38)');
    const edgeDim = token('--graph-edge-dim', 'rgba(148,163,184,0.12)');
    const labelColor = token('--graph-label', '#e2e8f0');
    const labelDim = token('--graph-label-dim', 'rgba(226,232,240,0.4)');
    const pathColor = token('--graph-path', '#fbbf24');
    const selectColor = token('--graph-select', '#38bdf8');
    const dimNode = token('--graph-node-dim', 'rgba(100,116,139,0.35)');

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.fillStyle = canvasBg;
    ctx.fillRect(0, 0, width, height);

    const { scale, tx, ty } = viewRef.current;
    ctx.translate(width / 2 + tx, height / 2 + ty);
    ctx.scale(scale, scale);

    const ns = nodesRef.current;
    const es = edgesRef.current;
    const active = hovered || selected;
    const neighbours = new Set<string>();
    if (active) {
      neighbours.add(active);
      for (const e of es.values()) {
        if (e.source === active) neighbours.add(e.target);
        if (e.target === active) neighbours.add(e.source);
      }
    }

    for (const e of es.values()) {
      const a = ns.get(e.source);
      const b = ns.get(e.target);
      if (!a || !b) continue;
      const onPath = pathEdgeIds.has(e.id);
      const dim = active ? !(neighbours.has(e.source) && neighbours.has(e.target)) : false;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.lineWidth = onPath
        ? 3.5
        : Math.min(3, 0.6 + Math.log2(1 + e.weight));
      ctx.strokeStyle = onPath ? pathColor : dim ? edgeDim : edgeColor;
      ctx.stroke();
    }

    for (const n of ns.values()) {
      const radius = n.radius + (n.name === selected ? 4 : 0);
      const color = colorOf(n.type);
      const dim = active ? !neighbours.has(n.name) : false;
      ctx.beginPath();
      ctx.arc(n.x, n.y, radius, 0, Math.PI * 2);
      ctx.fillStyle = dim ? dimNode : color;
      ctx.globalAlpha = dim ? 0.5 : 1;
      ctx.fill();
      ctx.globalAlpha = 1;
      if (pathNames.has(n.name) || n.name === selected) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius + 4, 0, Math.PI * 2);
        ctx.strokeStyle = pathNames.has(n.name) ? pathColor : selectColor;
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      if (scale > 0.55 && (!active || neighbours.has(n.name))) {
        ctx.fillStyle = dim ? labelDim : labelColor;
        ctx.font = '11px ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(n.name, n.x, n.y + radius + 13);
      }
    }
    ctx.restore();
  }, [hovered, selected, pathEdgeIds, pathNames]);

  // The animation loop may outlive a render; let it ask for a redraw/fit.
  drawRef.current = draw;

  useEffect(() => {
    draw();
  }, [draw, nodes, edges]);

  useEffect(() => {
    const onResize = () => draw();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [draw]);

  /**
   * Fit the whole graph into the viewport. Called once when the layout settles,
   * after expanding (new nodes may sit outside the viewport) and from the Fit
   * button. Kept in a ref so the animation loop can trigger it without being
   * torn down and restarted.
   */
  const fitView = useCallback(() => {
    const wrap = wrapRef.current;
    const arr = Array.from(nodesRef.current.values());
    if (!wrap || arr.length === 0) return;
    const xs = arr.map((n) => n.x);
    const ys = arr.map((n) => n.y);
    const spanX = Math.max(80, Math.max(...xs) - Math.min(...xs));
    const spanY = Math.max(80, Math.max(...ys) - Math.min(...ys));
    const scale = Math.max(0.2, Math.min(1.6, Math.min(wrap.clientWidth / (spanX + 220), wrap.clientHeight / (spanY + 180))));
    viewRef.current.scale = scale;
    viewRef.current.tx = -((Math.max(...xs) + Math.min(...xs)) / 2) * scale;
    viewRef.current.ty = -((Math.max(...ys) + Math.min(...ys)) / 2) * scale;
    fittedRef.current = true;
    drawRef.current?.();
  }, []);

  const fitViewRef = useRef<(() => void) | null>(null);
  fitViewRef.current = fitView;

  /* ---------- pointer interactions ---------- */

  const toWorld = useCallback((clientX: number, clientY: number) => {
    const wrap = wrapRef.current;
    if (!wrap) return { x: 0, y: 0 };
    const rect = wrap.getBoundingClientRect();
    const { scale, tx, ty } = viewRef.current;
    return {
      x: (clientX - rect.left - rect.width / 2 - tx) / scale,
      y: (clientY - rect.top - rect.height / 2 - ty) / scale,
    };
  }, []);

  const pick = useCallback(
    (clientX: number, clientY: number): Node | null => {
      const { x, y } = toWorld(clientX, clientY);
      let best: Node | null = null;
      let bestDist = 22;
      for (const n of nodesRef.current.values()) {
        const dist = Math.hypot(n.x - x, n.y - y);
        if (dist < bestDist) {
          best = n;
          bestDist = dist;
        }
      }
      return best;
    },
    [toWorld],
  );

  // Panning is middle-button only. A left click on blank space does nothing:
  // before, a left click started the drag but the drag ended on mouseup, so
  // left-drag never actually panned and the gesture felt broken.
  const onMouseDown = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    if (event.button !== 1) return;
    event.preventDefault();
    dragRef.current = {
      x: event.clientX,
      y: event.clientY,
      tx: viewRef.current.tx,
      ty: viewRef.current.ty,
    };
  }, []);

  const onClick = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      if (event.button !== 0) return;
      const node = pick(event.clientX, event.clientY);
      if (node) void openEntity(node.name);
    },
    [openEntity, pick],
  );

  const onDoubleClick = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      const node = pick(event.clientX, event.clientY);
      if (node) void expand(node.name);
    },
    [expand, pick],
  );

  const onMouseMove = useCallback(
    (event: React.MouseEvent<HTMLCanvasElement>) => {
      const drag = dragRef.current;
      if (drag) {
        viewRef.current.tx = drag.tx + (event.clientX - drag.x);
        viewRef.current.ty = drag.ty + (event.clientY - drag.y);
        draw();
        return;
      }
      const node = pick(event.clientX, event.clientY);
      if ((node?.name ?? null) !== hovered) setHovered(node?.name ?? null);
    },
    [draw, hovered, pick],
  );

  const onMouseUp = useCallback(() => {
    dragRef.current = null;
  }, []);

  const onWheel = useCallback(
    (event: React.WheelEvent<HTMLCanvasElement>) => {
      event.preventDefault();
      const wrap = wrapRef.current;
      if (!wrap) return;
      const rect = wrap.getBoundingClientRect();
      // Screen offset from the view centre; zoom must keep the world point
      // under the cursor fixed instead of drifting towards the origin.
      const mx = event.clientX - rect.left - rect.width / 2;
      const my = event.clientY - rect.top - rect.height / 2;
      const { scale, tx, ty } = viewRef.current;
      const factor = event.deltaY < 0 ? 1.12 : 0.9;
      const next = Math.max(0.25, Math.min(4, scale * factor));
      const wx = (mx - tx) / scale;
      const wy = (my - ty) / scale;
      viewRef.current.scale = next;
      viewRef.current.tx = mx - wx * next;
      viewRef.current.ty = my - wy * next;
      draw();
    },
    [draw],
  );

  const findPath = useCallback(async () => {
    if (!pathFrom.trim() || !pathTo.trim()) return;
    setPathError(null);
    try {
      const res = await fetch(
        `/api/graph/path?source=${encodeURIComponent(pathFrom)}&target=${encodeURIComponent(pathTo)}&max_hops=3`,
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        setPathError(err.detail || `No path (${res.status})`);
        setPath(null);
        return;
      }
      const body: PathResponse = await res.json();
      setPath(body);
      void expand(body.nodes[0]?.name ?? '');
    } catch (err) {
      setPathError(String(err));
    }
  }, [pathFrom, pathTo, expand]);

  /* ---------- render ---------- */

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.logo}>&gt;_</span>
          <div>
            <h1>Knowledge Graph Studio</h1>
            <p>ARM architecture · entities, relationships and claims in one view</p>
          </div>
        </div>
        <div className={styles.stats}>
          {stats ? (
            <>
              <span><strong>{stats.entities.toLocaleString()}</strong> entities</span>
              <span><strong>{stats.relationships.toLocaleString()}</strong> relationships</span>
            </>
          ) : null}
          <button type="button" className={styles.live} onClick={fitView} title="Fit graph to view">fit</button>
          <span className={styles.live}>live</span>
        </div>
      </header>

      <div className={styles.searchRow}>
        <div className={styles.searchBox}>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search an entity — Cortex-M55, AMBA AXI, PL031…"
            aria-label="Search entity"
          />
          {suggestions.length > 0 ? (
            <ul className={styles.suggestions}>
              {suggestions.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setQuery(item.name);
                      setSuggestions([]);
                      void openEntity(item.name).then(() => expand(item.name));
                    }}
                  >
                    <span className={styles.dot} style={{ background: colorOf(item.type) }} />
                    <span>{item.name}</span>
                    <span className={styles.meta}>{item.type || 'other'} · {item.degree} links</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <div className={styles.pathBox}>
          <input
            value={pathFrom}
            onChange={(event) => setPathFrom(event.target.value)}
            placeholder="from entity"
            aria-label="Path source"
          />
          <span className={styles.arrow}>→</span>
          <input
            value={pathTo}
            onChange={(event) => setPathTo(event.target.value)}
            placeholder="to entity"
            aria-label="Path target"
          />
          <button type="button" onClick={findPath}>Find path</button>
          {path ? <span className={styles.pathInfo}>{path.hops} hop{path.hops === 1 ? '' : 's'}</span> : null}
          {pathError ? <span className={styles.pathError}>{pathError}</span> : null}
        </div>
      </div>

      <div className={styles.body}>
        <div className={styles.canvasWrap} ref={wrapRef}>
          <canvas
            ref={canvasRef}
            className={styles.canvas}
            onMouseDown={onMouseDown}
            onClick={onClick}
            onDoubleClick={onDoubleClick}
            onMouseMove={onMouseMove}
            onMouseUp={onMouseUp}
            onAuxClick={(event) => event.preventDefault()}
            onContextMenu={(event) => event.preventDefault()}
            onMouseLeave={() => {
              dragRef.current = null;
              setHovered(null);
            }}
            onWheel={onWheel}
          />
          {status ? <div className={styles.status}>{status}</div> : null}
          <div className={styles.hint}>Click a node for details · double-click to expand · middle-drag to pan · wheel to zoom</div>
          <div className={styles.legend}>
            {Object.entries(TYPE_COLORS).slice(0, 8).map(([type, color]) => (
              <span key={type}><i style={{ background: color }} />{type.replace('_', ' ')}</span>
            ))}
          </div>
        </div>

        <aside className={styles.side}>
          {!selected ? (
            <div className={styles.empty}>
              <h2>Pick an entity</h2>
              <p>The card shows aliases, degree, the strongest relationships and the canonical claims attached to them.</p>
            </div>
          ) : detailLoading ? (
            <div className={styles.empty}>Loading {selected}…</div>
          ) : detail ? (
            <>
              <div className={styles.entityCard}>
                <span className={styles.typePill} style={{ borderColor: colorOf(detail.entity.type) }}>
                  {detail.entity.type || 'other'}
                </span>
                <h2>{detail.entity.name}</h2>
                <p className={styles.desc}>{detail.entity.description || 'No description extracted.'}</p>
                <div className={styles.metrics}>
                  <span><strong>{detail.degree}</strong> relationships</span>
                  <span><strong>{detail.claims.length}</strong> claims</span>
                  <span><strong>{detail.entity.aliases.length}</strong> aliases</span>
                </div>
                {detail.entity.aliases.length > 0 ? (
                  <div className={styles.aliases}>
                    {detail.entity.aliases.map((alias) => <code key={alias}>{alias}</code>)}
                  </div>
                ) : null}
              </div>

              <div className={styles.section}>
                <h3>Strongest relationships</h3>
                <ul className={styles.edgeList}>
                  {detail.edges.slice(0, 8).map((edge) => (
                    <li key={edge.id}>
                      <div className={styles.edgeHead}>
                        <span>{edge.source_name} <em>→</em> {edge.target_name}</span>
                        <span className={styles.badge}>{edge.relation_type}</span>
                      </div>
                      <div className={styles.edgeMeta}>
                        w{edge.weight ?? 1} · conf {edge.confidence?.toFixed(2)} · {edge.document_title || 'source'}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>

              <div className={styles.section}>
                <h3>Claims</h3>
                {detail.claims.length === 0 ? (
                  <p className={styles.muted}>No canonical claim attached yet.</p>
                ) : (
                  <ul className={styles.claimList}>
                    {detail.claims.slice(0, 6).map((claim) => (
                      <li key={claim.id}>
                        <p
                          role={onNavigate ? 'button' : undefined}
                          tabIndex={onNavigate ? 0 : undefined}
                          className={onNavigate ? styles.claimLink : undefined}
                          title={onNavigate ? '在论断中查看' : undefined}
                          onClick={() => onNavigate?.('claims', { kind: 'claims', q: claim.text.slice(0, 80), actor: claim.actor })}
                          onKeyDown={(event) => {
                            if (onNavigate && (event.key === 'Enter' || event.key === ' ')) {
                              event.preventDefault();
                              onNavigate('claims', { kind: 'claims', q: claim.text.slice(0, 80), actor: claim.actor });
                            }
                          }}
                        >
                          {claim.text}
                        </p>
                        <div className={styles.edgeMeta}>
                          <span className={claim.status === 'disputed' ? styles.disputed : styles.active}>{claim.status}</span>
                          {' · '}evidence {claim.evidence_count}
                          {claim.page_start ? ` · p.${claim.page_start}` : ''}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {detail.wiki ? (
                <div className={styles.section}>
                  <h3>Compiled wiki</h3>
                  <pre className={styles.wiki}>{detail.wiki.content.slice(0, 900)}</pre>
                </div>
              ) : null}
            </>
          ) : (
            <div className={styles.empty}>No details for {selected}.</div>
          )}
        </aside>
      </div>
    </div>
  );
}
