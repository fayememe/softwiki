'use client';

/**
 * Context for the right-hand agent drawer.
 *
 * Any panel can call `openAgent({ kb, panel, subject })` to get an assistant
 * that knows what the user is looking at. The drawer is deliberately *not* the
 * Chat panel: Chat is for open-ended research, the drawer acts on the current
 * view and is where proposals get approved.
 */

import { createContext, useContext } from 'react';

export interface AgentContextPayload {
  kb?: string | null;
  panel: string;
  subject?: string | null;
  detail?: string | null;
}

export interface AgentDrawerApi {
  openAgent: (context: AgentContextPayload) => void;
  closeAgent: () => void;
}

export const AgentDrawerContext = createContext<AgentDrawerApi>({
  openAgent: () => {},
  closeAgent: () => {},
});

export function useAgentDrawer(): AgentDrawerApi {
  return useContext(AgentDrawerContext);
}
