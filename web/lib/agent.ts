/** URL of the opencode browser agent (L1: separate process on :6111). */
export function agentWebUrl(): string {
  const configured = process.env.NEXT_PUBLIC_AGENT_WEB_URL;
  if (configured) return configured;
  if (typeof window === 'undefined') return 'http://localhost:6111';
  return `${window.location.protocol}//${window.location.hostname}:6111`;
}
