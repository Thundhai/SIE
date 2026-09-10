import { X } from 'lucide-react';
import { ReactNode, useEffect, useId, useRef } from 'react';
import { cn } from '../../lib/cn';

export interface OverlayProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** `'center'` (Modal) or `'right'` (Drawer). */
  placement: 'center' | 'right';
}

/**
 * Shared implementation behind `Modal` and `Drawer` — a real
 * `role="dialog"`/`aria-modal` overlay with: focus moved into the panel
 * on open, focus returned to the trigger on close, Escape-to-close, and
 * backdrop-click-to-close (§18: "accessible modal/drawer behaviour").
 * Not a native `<dialog>` element — jsdom's support for
 * `showModal()`/the top-layer is inconsistent enough that a manually
 * managed overlay is both more portable and more straightforward to
 * unit test (see the Phase J test suite).
 */
export function Overlay({ isOpen, onClose, title, children, placement }: OverlayProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    if (!isOpen) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    panelRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previouslyFocused.current?.focus();
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex" role="presentation">
      <div className="fixed inset-0 bg-navy-950/40" onClick={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          'relative z-10 flex flex-col bg-surface shadow-lg outline-none',
          placement === 'center' && 'm-auto max-h-[85vh] w-full max-w-lg rounded-lg border border-border',
          placement === 'right' && 'ml-auto h-full w-full max-w-md border-l border-border',
        )}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 id={titleId} className="text-sm font-semibold text-text-primary">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-text-muted hover:bg-surface-muted hover:text-text-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
}
