'use client';

/**
 * Standalone route kept for bookmarks and direct links. The graph UI itself
 * lives in `components/GraphStudioPanel` because it is also embedded as a
 * regular panel inside the app (no new tab, same chrome).
 */

import GraphStudioPanel from '@/components/GraphStudioPanel';

export default function GraphStudioPage() {
  return <GraphStudioPanel />;
}
