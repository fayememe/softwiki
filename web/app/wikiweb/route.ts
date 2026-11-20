export const dynamic = 'force-dynamic';

/**
 * Entry point for the static Wiki portal.
 *
 * The generated site is not part of this repository: it is a build artifact
 * (thousands of HTML files, tens of MB) produced per knowledge base, and it
 * lives with the data inside that knowledge base's workspace:
 *
 *   <workspace>/exports/wikiweb/assets/...     shared CSS/JS
 *   <workspace>/exports/wikiweb/<kb>/...       the site itself
 *
 * One portal per knowledge base on purpose: a portal that linked to another
 * kb's pages would bypass `kb_scope`. Each web container mounts only its own
 * workspace, and `WIKIWEB_ENTRY` names the sub-directory to open
 * (e.g. `coffee/index.html`). Page links inside the generated site are
 * depth-relative (`../assets/...`), so the kb directory must stay one level
 * below the mount root.
 */
export function GET(request: Request) {
  const entry = (process.env.WIKIWEB_ENTRY || 'index.html').replace(/^\/+/, '');
  const url = new URL(`/wikiweb/${entry}`, request.url);
  const host = request.headers.get('x-forwarded-host') || request.headers.get('host');
  if (host) url.host = host;
  const proto = request.headers.get('x-forwarded-proto');
  if (proto) url.protocol = `${proto}:`;
  return Response.redirect(url, 307);
}
