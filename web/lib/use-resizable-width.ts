'use client';

/**
 * Resizable side panel width, shared by the wiki rail and the assistant pane.
 *
 * Both panels sit on the right and are resized from their left edge, so the
 * mechanics are identical:
 *   - pointer capture (otherwise a drag over an <iframe> is swallowed by it),
 *   - drag deltas measured from the width at pointerdown,
 *   - clamp against a caller-supplied maximum,
 *   - persist after the drag settles,
 *   - double-tap on the handle resets — Chrome does not reliably synthesise
 *     `dblclick` once pointer capture is taken, so it is detected here.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';

interface Options {
  storageKey: string;
  defaultWidth: number;
  min: number;
  /** Upper bound; evaluated at drag time because it can depend on layout. */
  max: () => number;
}

export interface ResizableWidth {
  width: number;
  dragging: boolean;
  handleProps: {
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerMove: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerUp: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerCancel: () => void;
  };
}

export function useResizableWidth({ storageKey, defaultWidth, min, max }: Options): ResizableWidth {
  const [width, setWidth] = useState(defaultWidth);
  const [dragging, setDragging] = useState(false);

  const widthRef = useRef(width);
  widthRef.current = width;
  const dragRef = useRef<{ startX: number; startWidth: number; moved: boolean } | null>(null);
  const lastTapRef = useRef(0);

  const clamp = useCallback(
    (value: number) => Math.min(max(), Math.max(min, value)),
    [max, min],
  );

  // Restore the remembered width once.
  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem(storageKey));
      if (Number.isFinite(saved) && saved >= min) setWidth(clamp(saved));
    } catch {
      /* storage disabled: keep the default */
    }
    // max() is layout-dependent; evaluating it again here would resize the
    // panel on every re-render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey, min]);

  // Persist a settled width, not every frame of the drag.
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(storageKey, String(width));
      } catch {
        /* ignore */
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [width, storageKey]);

  const endDrag = useCallback(() => {
    if (!dragRef.current) return;
    dragRef.current = null;
    setDragging(false);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  // Safety net when the pointer is released outside the window.
  useEffect(() => {
    window.addEventListener('pointerup', endDrag);
    window.addEventListener('pointercancel', endDrag);
    return () => {
      window.removeEventListener('pointerup', endDrag);
      window.removeEventListener('pointercancel', endDrag);
    };
  }, [endDrag]);

  const onPointerDown = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    // No preventDefault: it also cancels the compatibility click events that
    // the double-tap reset relies on. user-select is suppressed instead.
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { startX: event.clientX, startWidth: widthRef.current, moved: false };
    setDragging(true);
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      const drag = dragRef.current;
      if (!drag) return;
      const delta = drag.startX - event.clientX;
      if (Math.abs(delta) > 4) drag.moved = true;
      setWidth(clamp(drag.startWidth + delta));
    },
    [clamp],
  );

  const onPointerUp = useCallback(
    (event: ReactPointerEvent<HTMLElement>) => {
      event.currentTarget.releasePointerCapture?.(event.pointerId);
      const moved = dragRef.current?.moved ?? false;
      endDrag();
      if (moved) {
        lastTapRef.current = 0;
        return;
      }
      const now = Date.now();
      if (now - lastTapRef.current < 320) {
        setWidth(clamp(defaultWidth));
        lastTapRef.current = 0;
      } else {
        lastTapRef.current = now;
      }
    },
    [clamp, defaultWidth, endDrag],
  );

  return {
    width,
    dragging,
    handleProps: {
      onPointerDown,
      onPointerMove,
      onPointerUp,
      onPointerCancel: endDrag,
    },
  };
}
