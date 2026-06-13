'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { apiListGraph } from '@/lib/api';
import type { GraphEntity, GraphRelationship } from '@/lib/api';
import styles from './GraphPanel.module.css';

interface Node {
  id: number;
  name: string;
  type: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface Edge {
  source: number;
  target: number;
  type: string;
}

const COLORS: Record<string, string> = {
  person: '#5588ff', character: '#5588ff',
  organization: '#22c55e', group: '#22c55e',
  concept: '#a78bfa', theme: '#a78bfa',
  event: '#f59e0b',
  location: '#22d3ee',
  work: '#ef4444',
  default: '#888',
};

function forceLayout(nodes: Node[], edges: Edge[], width: number, height: number) {
  const REP = 800, ATT = 0.005, CEN = 0.01, DAMP = 0.9, ITERS = 80;
  for (let iter = 0; iter < ITERS; iter++) {
    // repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        let dx = nodes[j].x - nodes[i].x;
        let dy = nodes[j].y - nodes[i].y;
        let dist = Math.sqrt(dx * dx + dy * dy) || 1;
        let force = REP / (dist * dist);
        nodes[i].vx -= (dx / dist) * force;
        nodes[i].vy -= (dy / dist) * force;
        nodes[j].vx += (dx / dist) * force;
        nodes[j].vy += (dy / dist) * force;
      }
    }
    // attraction along edges
    for (const e of edges) {
      const s = nodes.find(n => n.id === e.source);
      const t = nodes.find(n => n.id === e.target);
      if (!s || !t) continue;
      const dx = t.x - s.x, dy = t.y - s.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      s.vx += dx * ATT;
      s.vy += dy * ATT;
      t.vx -= dx * ATT;
      t.vy -= dy * ATT;
    }
    // centering
    for (const n of nodes) {
      n.vx += (width / 2 - n.x) * CEN;
      n.vy += (height / 2 - n.y) * CEN;
    }
    // apply velocity with damping
    for (const n of nodes) {
      n.vx *= DAMP;
      n.vy *= DAMP;
      n.x += n.vx;
      n.y += n.vy;
    }
  }
}

export default function GraphPanel() {
  const [entities, setEntities] = useState<GraphEntity[]>([]);
  const [relationships, setRelationships] = useState<GraphRelationship[]>([]);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const svgRef = useRef<SVGSVGElement>(null);
  const [dims, setDims] = useState({ w: 600, h: 400 });

  useEffect(() => {
    apiListGraph().then(r => {
      setEntities(r.entities);
      setRelationships(r.relationships);
      const nodeMap: Node[] = r.entities.map((e, i) => ({
        id: e.id,
        name: e.name,
        type: e.type || 'default',
        x: 200 + Math.random() * 400,
        y: 100 + Math.random() * 200,
        vx: 0, vy: 0,
      }));
      const edgeList: Edge[] = r.relationships.map(rr => ({
        source: rr.source_name === rr.target_name ? nodeMap.find(n => n.name === rr.source_name)?.id || 0 : nodeMap.find(n => n.name === rr.source_name)?.id || 0,
        target: nodeMap.find(n => n.name === rr.target_name)?.id || 0,
        type: rr.relation_type,
      })).filter(e => e.source && e.target && e.source !== e.target);
      setNodes(nodeMap);
      setEdges(edgeList);
      setTimeout(() => {
        const svg = svgRef.current;
        if (svg) {
          const rect = svg.parentElement!.getBoundingClientRect();
          const w = Math.max(rect.width, 400), h = Math.max(rect.height, 300);
          setDims({ w, h });
          forceLayout(nodeMap, edgeList, w, h);
          setNodes([...nodeMap]);
        }
      }, 100);
    }).catch(() => {});
  }, []);

  const selectedNode = selectedId ? nodes.find(n => n.id === selectedId) : null;
  const selectedRels = selectedId
    ? relationships.filter(r =>
        r.source_name === selectedNode?.name || r.target_name === selectedNode?.name)
    : [];

  const filteredEntities = entities.filter(e =>
    e.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className={styles.panel}>
      <div className={styles.sidebar}>
        <input className={styles.search} value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search entities…" />
        <div className={styles.entityList}>
          {filteredEntities.map(e => (
            <button key={e.id}
              className={`${styles.entityItem} ${selectedId === e.id ? styles.entityActive : ''}`}
              onClick={() => { setSelectedId(e.id); }}>
              <span className={styles.entityDot} style={{ background: COLORS[e.type || 'default'] }} />
              <span className={styles.entityName}>{e.name}</span>
            </button>
          ))}
        </div>
      </div>

      <div className={styles.graphArea}>
        <svg ref={svgRef} className={styles.svg}>
          {edges.map((e, i) => {
            const s = nodes.find(n => n.id === e.source);
            const t = nodes.find(n => n.id === e.target);
            if (!s || !t) return null;
            const isHighlighted = selectedId && (e.source === selectedId || e.target === selectedId);
            return (
              <g key={`e-${i}`}>
                <line x1={s.x} y1={s.y} x2={t.x} y2={t.y}
                  stroke={isHighlighted ? '#5588ff' : 'rgba(255,255,255,0.08)'}
                  strokeWidth={isHighlighted ? 2 : 1}
                  strokeDasharray={isHighlighted ? 'none' : '4,3'} />
              </g>
            );
          })}
          {nodes.map(n => {
            const isSelected = selectedId === n.id;
            const hasRel = selectedId && selectedRels.some(r =>
              r.source_name === n.name || r.target_name === n.name);
            const showLabel = isSelected || hasRel;
            const color = COLORS[n.type] || COLORS.default;
            return (
              <g key={`n-${n.id}`} className={styles.nodeGroup}
                onClick={() => setSelectedId(n.id)} style={{ cursor: 'pointer' }}>
                {(isSelected || hasRel) && (
                  <circle cx={n.x} cy={n.y} r={18} fill="none"
                    stroke="#5588ff" strokeWidth={2} opacity={0.4} />
                )}
                <circle cx={n.x} cy={n.y} r={isSelected ? 10 : 6}
                  fill={isSelected ? '#5588ff' : color}
                  stroke={isSelected ? '#fff' : 'none'}
                  strokeWidth={1.5}
                  opacity={isSelected ? 1 : 0.5} />
                {showLabel && (
                  <text x={n.x} y={n.y + 22} textAnchor="middle"
                    fill={isSelected ? '#fff' : 'rgba(255,255,255,0.6)'}
                    fontSize={10} fontWeight={isSelected ? '600' : '400'}
                    className={styles.nodeLabel}>
                    {n.name.length > 18 ? n.name.slice(0, 16) + '…' : n.name}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      {selectedNode && (
        <div className={styles.detail}>
          <div className={styles.detailHeader}>
            <span className={styles.detailDot} style={{ background: COLORS[selectedNode.type] || COLORS.default }} />
            <span className={styles.detailName}>{selectedNode.name}</span>
            <span className={styles.detailType}>{selectedNode.type}</span>
          </div>
          <div className={styles.detailRels}>
            {selectedRels.map(r => (
              <div key={r.id} className={styles.detailRel}>
                <span>{r.source_name}</span>
                <span className={styles.relArrow}>—{r.relation_type}→</span>
                <span>{r.target_name}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
