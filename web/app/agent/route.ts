import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

/**
 * Redirect to the host-local opencode agent.
 *
 * Using a same-origin relative link avoids the server-rendered `localhost`
 * problem: the browser asks this host for /agent, and we forward to port 6111
 * on the same hostname.
 */
export function GET(request: NextRequest) {
  const host =
    request.headers.get('x-forwarded-host') ||
    request.headers.get('host') ||
    'localhost:6108';
  const proto = request.headers.get('x-forwarded-proto') || 'http';
  let hostname = 'localhost';
  try {
    hostname = new URL(`http://${host}`).hostname;
  } catch {
    hostname = host.split(':')[0] || 'localhost';
  }
  const target = new URL(`${proto}://${hostname}:6111/`);
  return NextResponse.redirect(target, 307);
}
