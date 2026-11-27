/**
 * Cross-panel navigation.
 *
 * Panels used to be islands: a claim in the graph could not be opened in the
 * claims table, a document could not show its claims, and so on. `NavFocus` is
 * the small payload a panel hands to another one, e.g.
 *
 *   onNavigate?.('claims', { kind: 'claims', documentId: doc.id })
 *
 * Each panel only implements the kinds it understands; unknown kinds are
 * ignored, so adding a link never breaks the target.
 */

export type ClaimsFocus = {
  kind: 'claims';
  claimId?: number;
  actor?: string;
  topic?: string;
  documentId?: number;
  /** Free-text filter (claim text or subject name). */
  q?: string;
};

export type DocumentFocus = {
  kind: 'document';
  documentId: number;
};

export type EntityFocus = {
  kind: 'entity';
  name: string;
};

export type NavFocus = ClaimsFocus | DocumentFocus | EntityFocus;

export type Navigate = (panel: import('@/components/Sidebar').ActivePanel, focus?: NavFocus) => void;
