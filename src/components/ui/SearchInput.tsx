import { Search, X } from 'lucide-react';
import { InputHTMLAttributes, forwardRef, useId } from 'react';
import { cn } from '../../lib/cn';

export interface SearchInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: string;
  hideLabel?: boolean;
  onClear?: () => void;
}

/** A search-flavored `Input` (icon + optional clear button). Kept as a
 * separate component rather than an `Input` prop, since it has its own
 * icon layout and a clear affordance `Input` doesn't need. */
export const SearchInput = forwardRef<HTMLInputElement, SearchInputProps>(
  ({ label, hideLabel = true, onClear, value, className, id, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id ?? generatedId;

    return (
      <div className="flex flex-col gap-1">
        <label htmlFor={inputId} className={hideLabel ? 'sr-only' : 'text-xs font-medium text-text-secondary'}>
          {label}
        </label>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" aria-hidden="true" />
          <input
            ref={ref}
            id={inputId}
            type="search"
            value={value}
            className={cn(
              'w-full rounded-md border border-border-strong bg-surface py-2 pl-9 text-sm text-text-primary',
              onClear && value ? 'pr-9' : 'pr-3',
              'placeholder:text-text-muted',
              'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600',
              className,
            )}
            {...props}
          />
          {onClear && value ? (
            <button
              type="button"
              onClick={onClear}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-text-muted hover:bg-surface-muted hover:text-text-secondary"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          ) : null}
        </div>
      </div>
    );
  },
);
SearchInput.displayName = 'SearchInput';
