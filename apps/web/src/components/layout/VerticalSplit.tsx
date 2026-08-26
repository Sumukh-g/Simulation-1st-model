'use client';

import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

const STORAGE_KEY = 'gsip.workspaceSplitPct';
const DEFAULT_PCT = 65;
const MIN_PCT = 25;
const MAX_PCT = 80;

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function readStoredPct(): number {
  if (typeof window === 'undefined') return DEFAULT_PCT;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PCT;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? clamp(parsed, MIN_PCT, MAX_PCT) : DEFAULT_PCT;
  } catch {
    return DEFAULT_PCT;
  }
}

interface VerticalSplitProps {
  top: ReactNode;
  bottom: ReactNode;
}

/**
 * Drag the middle handle to grow/shrink the workspace vs chat panels.
 * Split ratio is persisted in localStorage.
 */
export function VerticalSplit({ top, bottom }: VerticalSplitProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [topPct, setTopPct] = useState(DEFAULT_PCT);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    setTopPct(readStoredPct());
  }, []);

  const applyFromClientY = useCallback((clientY: number) => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (rect.height <= 0) return;
    const next = clamp(((clientY - rect.top) / rect.height) * 100, MIN_PCT, MAX_PCT);
    setTopPct(next);
  }, []);

  useEffect(() => {
    if (!dragging) return;

    const onMove = (e: MouseEvent | TouchEvent) => {
      e.preventDefault();
      const clientY = 'touches' in e ? e.touches[0]?.clientY : e.clientY;
      if (clientY == null) return;
      applyFromClientY(clientY);
    };

    const onUp = () => {
      setDragging(false);
      setTopPct((current) => {
        try {
          window.localStorage.setItem(STORAGE_KEY, String(current));
        } catch {
          // ignore quota / private mode
        }
        return current;
      });
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchmove', onMove, { passive: false });
    window.addEventListener('touchend', onUp);

    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('touchend', onUp);
    };
  }, [dragging, applyFromClientY]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setTopPct((p) => {
        const next = clamp(p - 3, MIN_PCT, MAX_PCT);
        try {
          window.localStorage.setItem(STORAGE_KEY, String(next));
        } catch {
          /* ignore */
        }
        return next;
      });
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setTopPct((p) => {
        const next = clamp(p + 3, MIN_PCT, MAX_PCT);
        try {
          window.localStorage.setItem(STORAGE_KEY, String(next));
        } catch {
          /* ignore */
        }
        return next;
      });
    } else if (e.key === 'Home') {
      e.preventDefault();
      setTopPct(MIN_PCT);
      try {
        window.localStorage.setItem(STORAGE_KEY, String(MIN_PCT));
      } catch {
        /* ignore */
      }
    } else if (e.key === 'End') {
      e.preventDefault();
      setTopPct(MAX_PCT);
      try {
        window.localStorage.setItem(STORAGE_KEY, String(MAX_PCT));
      } catch {
        /* ignore */
      }
    }
  };

  return (
    <div ref={containerRef} className="flex-1 flex flex-col overflow-hidden min-h-0">
      <div
        className="flex flex-col overflow-hidden min-h-0"
        style={{ height: `calc(${topPct}% - 4px)` }}
      >
        {top}
      </div>

      <div
        role="separator"
        aria-orientation="horizontal"
        aria-valuenow={Math.round(topPct)}
        aria-valuemin={MIN_PCT}
        aria-valuemax={MAX_PCT}
        aria-label="Resize workspace and chat panels"
        tabIndex={0}
        onKeyDown={onKeyDown}
        onMouseDown={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onTouchStart={(e) => {
          setDragging(true);
          const y = e.touches[0]?.clientY;
          if (y != null) applyFromClientY(y);
        }}
        onDoubleClick={() => {
          setTopPct(DEFAULT_PCT);
          try {
            window.localStorage.setItem(STORAGE_KEY, String(DEFAULT_PCT));
          } catch {
            /* ignore */
          }
        }}
        className={`
          group relative z-10 h-2 flex-shrink-0 cursor-row-resize
          flex items-center justify-center
          border-y border-gray-200 bg-gray-50
          hover:bg-primary-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-400
          ${dragging ? 'bg-primary-100' : ''}
        `}
        title="Drag to resize · double-click to reset"
      >
        <div
          className={`
            h-1 w-10 rounded-full transition-colors
            ${dragging ? 'bg-primary-500' : 'bg-gray-300 group-hover:bg-primary-400'}
          `}
        />
      </div>

      <div
        className="flex flex-col overflow-hidden min-h-0 bg-white"
        style={{ height: `calc(${100 - topPct}% - 4px)` }}
      >
        {bottom}
      </div>
    </div>
  );
}
