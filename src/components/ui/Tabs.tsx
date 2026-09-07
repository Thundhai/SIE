import { KeyboardEvent, useRef } from 'react';
import { cn } from '../../lib/cn';

export interface TabItem {
  value: string;
  label: string;
}

export interface TabsProps {
  items: TabItem[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

/** An accessible tab list: `role="tablist"`/`role="tab"`,
 * `aria-selected`, and left/right arrow-key navigation between tabs
 * (roving tabindex) — not just a styled button row. Controlled: the
 * caller owns `value`/`onChange` and renders the corresponding panel
 * itself (no implicit panel management, kept intentionally simple).
 *
 * The only current caller is the Intelligence workspace, so the selected
 * state uses the SIE teal intelligence accent (SIE Milestone
 * UI-DESIGN-01) — a clear selected state via color/weight/underline,
 * deliberately no glow or gradient. */
export function Tabs({ items, value, onChange, className }: TabsProps) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    event.preventDefault();
    const direction = event.key === 'ArrowRight' ? 1 : -1;
    const nextIndex = (index + direction + items.length) % items.length;
    onChange(items[nextIndex].value);
    tabRefs.current[nextIndex]?.focus();
  };

  return (
    <div role="tablist" className={cn('flex gap-1 border-b border-border', className)}>
      {items.map((item, index) => {
        const selected = item.value === value;
        return (
          <button
            key={item.value}
            ref={(el) => {
              tabRefs.current[index] = el;
            }}
            role="tab"
            type="button"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.value)}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className={cn(
              'border-b-2 px-3 py-2 text-sm -mb-px transition-colors',
              'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600',
              selected
                ? 'border-teal-600 font-semibold text-teal-700'
                : 'border-transparent font-medium text-text-secondary hover:text-text-primary',
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
