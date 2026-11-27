import { promises as fs } from 'node:fs';
import path from 'node:path';

export const dynamic = 'force-dynamic';

/**
 * Static wiki portals, one per knowledge base.
 *
 * The portal is an artifact kept with the data:
 *
 *   <WORKSPACES_ROOT>/<kb>/exports/wikiweb/assets/...   shared css/js
 *   <WORKSPACES_ROOT>/<kb>/exports/wikiweb/<kb>/...     the pages themselves
 *
 * Two URL shapes are served:
 *
 *   /wikiweb/<kb>/...        multi-kb layout (which kb you are looking at)
 *   /wikiweb/...             legacy single-kb links (assets/..., <kb>/...)
 *
 * Relative links inside a generated page (`../../assets/x.css`) land under
 * `/wikiweb/<kb>/assets/...`, so `assets` is resolved from the kb's export root
 * while everything else comes from its `<kb>/` subtree.
 *
 * Previously the web container mounted one kb's export directory at
 * `public/wikiweb` with `WIKIWEB_ENTRY=armkb/index.html`: every kb showed the
 * ARM portal, no matter which one was active.
 */

const ROOT = process.env.WORKSPACES_ROOT || '/data/workspaces';
const API = process.env.API_INTERNAL_URL || 'http://127.0.0.1:6200';

const CONTENT_TYPES: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.xml': 'application/xml; charset=utf-8',
};

interface KbList {
  active: string;
  names: string[];
}

async function kbList(): Promise<KbList> {
  try {
    const res = await fetch(`${API}/api/kb`, { cache: 'no-store' });
    if (!res.ok) return { active: '', names: [] };
    const body = await res.json();
    const names = (body.kbs || []).map((kb: { name: string }) => kb.name);
    return { active: body.active || names[0] || '', names };
  } catch {
    return { active: '', names: [] };
  }
}

function notFound(kb: string, reason: string): Response {
  return new Response(
    `<!doctype html><meta charset="utf-8"><title>Wiki portal</title>
     <body style="font:14px/1.6 system-ui;padding:48px;color:#444">
     <h1 style="font-size:18px">Wiki portal</h1>
     <p>${reason}</p>
     <p style="color:#777">kb: <code>${kb || 'unknown'}</code></p></body>`,
    { status: 404, headers: { 'Content-Type': 'text/html; charset=utf-8' } },
  );
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ path?: string[] }> },
) {
  const { path: segments = [] } = await params;
  const { active, names } = await kbList();

  if (!active) return notFound('', 'No knowledge base is available on this instance.');

  // /wikiweb -> the active kb's portal, always with a trailing slash so the
  // generated site's relative links resolve inside the kb's URL space.
  if (segments.length === 0) {
    return Response.redirect(new URL(`/wikiweb/${encodeURIComponent(active)}/`, request.url), 307);
  }

  const first = segments[0];
  const scoped = names.includes(first);
  const kb = scoped ? first : active;
  const rest = scoped ? segments.slice(1) : segments;
  const base = path.join(ROOT, kb, 'exports', 'wikiweb');

  // `assets` sits at the export root; pages sit one level down under the kb name.
  const target =
    rest.length === 0
      ? path.join(base, kb, 'index.html')
      : rest[0] === 'assets'
        ? path.join(base, ...rest)
        : path.join(base, kb, ...rest);

  const resolved = path.resolve(target);
  if (!resolved.startsWith(path.resolve(base) + path.sep)) {
    return notFound(kb, 'Invalid path.');
  }

  let body: Buffer;
  try {
    const stat = await fs.stat(resolved);
    if (!stat.isFile()) throw new Error('not a file');
    body = await fs.readFile(resolved);
  } catch {
    return notFound(kb, `No portal has been generated for this knowledge base yet.`);
  }

  return new Response(new Uint8Array(body), {
    headers: {
      'Content-Type': CONTENT_TYPES[path.extname(resolved).toLowerCase()] || 'application/octet-stream',
      // Portals are rebuilt by a script; do not let a browser pin an old page.
      'Cache-Control': 'no-cache',
    },
  });
}
