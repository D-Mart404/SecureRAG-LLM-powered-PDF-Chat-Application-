import React, { useEffect, useRef } from 'react';
import gsap from 'gsap';

interface ThinkingPanelProps {
  isVisible: boolean;
  retrievedChunks?: Array<{
    content: string;
    page: number;
    chunkId: string;
    score: number;
  }>;
}

export const ThinkingPanel: React.FC<ThinkingPanelProps> = ({ isVisible, retrievedChunks = [] }) => {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;

    gsap.fromTo(el, { y: -6, opacity: 0 }, { y: 0, opacity: 1, duration: 0.28, ease: 'power2.out' });
  }, [isVisible]);

  if (!isVisible) return null;

  return (
    <div ref={rootRef} className="mb-4 rounded-xl border border-border bg-paper-muted p-4">
      <div className="mb-3 flex items-center gap-2">
        <div className="h-2 w-2 animate-pulse rounded-full bg-accent" />
        <p className="m-0 text-sm font-semibold text-ink">Thinking...</p>
      </div>

      {retrievedChunks.length > 0 && (
        <div>
          <p className="mb-2 mt-3 text-xs font-medium text-ink-muted">
            Retrieved Context ({retrievedChunks.length} chunks):
          </p>

          <div className="flex max-h-52 flex-col gap-2 overflow-y-auto pr-1">
            {retrievedChunks.map((chunk, idx) => (
              <div key={idx} className="rounded-lg border border-border bg-paper-soft p-2.5">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-accent">
                    Page {chunk.page}
                  </span>
                  <span className="rounded bg-paper-muted px-2 py-0.5 text-[10px] text-ink-muted">
                    Score: {(chunk.score * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="m-0 max-h-10 overflow-hidden text-ellipsis text-xs leading-5 text-ink-text">
                  {chunk.content}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
