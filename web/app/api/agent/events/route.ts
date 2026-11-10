export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const API_INTERNAL_URL =
  process.env.API_INTERNAL_URL ||
  `http://127.0.0.1:${process.env.NEXT_PUBLIC_API_PORT || '6200'}`;

export async function GET(request: Request) {
  const url = new URL(request.url);
  const controller = new AbortController();
  request.signal.addEventListener('abort', () => controller.abort());

  const headers: Record<string, string> = { Accept: 'text/event-stream' };
  const role = request.headers.get('x-softwiki-role');
  if (role) headers['x-softwiki-role'] = role;

  let upstream: Response;
  try {
    upstream = await fetch(`${API_INTERNAL_URL}/api/agent/events${url.search}`, {
      headers,
      cache: 'no-store',
      signal: controller.signal,
    });
  } catch {
    return new Response('event: error\ndata: {"detail":"agent event stream unavailable"}\n\n', {
      status: 503,
      headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
    });
  }

  if (!upstream.ok || !upstream.body) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { 'Content-Type': 'text/event-stream; charset=utf-8' },
    });
  }

  return new Response(upstream.body, {
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}
