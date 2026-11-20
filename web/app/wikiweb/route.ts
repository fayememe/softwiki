export const dynamic = 'force-dynamic';

/**
 * Entry point for the static Wiki portal.
 *
 * The generated site itself is not part of this repository: it is a build
 * artifact (thousands of HTML files, tens of MB) produced per knowledge base.
 * It is mounted into the web container at `public/wikiweb`, so Next serves the
 * files, and this route only sends `/wikiweb` to its index.
 *
 * Without the mount this route still answers, but the redirect target is
 * missing — `/api/wiki/coverage` and the wiki panel hold the canonical content,
 * the portal is the publish layer.
 */
export function GET(request: Request) {
  const url = new URL('/wikiweb/index.html', request.url);
  const host = request.headers.get('x-forwarded-host') || request.headers.get('host');
  if (host) url.host = host;
  const proto = request.headers.get('x-forwarded-proto');
  if (proto) url.protocol = `${proto}:`;
  return Response.redirect(url, 307);
}
