export const dynamic = 'force-dynamic';

/**
 * Entry point for the static Wiki portal.
 *
 * The portal itself is a per-kb artifact kept with the data (see
 * `[...path]/route.ts`). This route only decides *which* kb to open: the one the
 * caller is currently looking at. It used to redirect to a fixed
 * `WIKIWEB_ENTRY` from the container environment, which is why every kb showed
 * the ARM portal.
 */

const API = process.env.API_INTERNAL_URL || 'http://127.0.0.1:6200';

export async function GET(request: Request) {
  let active = '';
  try {
    const res = await fetch(`${API}/api/kb`, { cache: 'no-store' });
    if (res.ok) {
      const body = await res.json();
      active = body.active || body.kbs?.[0]?.name || '';
    }
  } catch {
    /* fall through to the redirect below; the catch-all explains the 404 */
  }

  const url = new URL(active ? `/wikiweb/${encodeURIComponent(active)}/` : '/wikiweb/', request.url);
  const host = request.headers.get('x-forwarded-host') || request.headers.get('host');
  if (host) url.host = host;
  const proto = request.headers.get('x-forwarded-proto');
  if (proto) url.protocol = `${proto}:`;
  return Response.redirect(url, 307);
}
