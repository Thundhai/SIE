import { ChevronDown } from 'lucide-react';
import { SelectHTMLAttributes, forwardRef, useId } from 'react';
import { cn } from '../../lib/cn';

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children'> {
  label: string;
  hideLabel?: boolean;
  options: SelectOption[];
}

/** A native `<select>`, deliberately — not a custom listbox. A native
 * select gets keyboard navigation, screen-reader semantics, and mobile
 * platform pickers for free, which the legacy prototype's hand-rolled
 * dropdowns (`Header.tsx`'s show/hide `<div>`s) never had. */
export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, hideLabel, options, id, className, ...props }, ref) => {
    const generatedId = useId();
    const selectId = id ?? generatedId;

    return (
      <div className="flex flex-col gap-1">
        <label htmlFor={selectId} className={hideLabel ? 'sr-only' : 'text-xs font-medium text-text-secondary'}>
          {label}
        </label>
        <div className="relative">
          <select
            ref={ref}
            id={selectId}
            className={cn(
              'w-full appearance-none rounded-md border border-border-strong bg-surface py-2 pl-3 pr-8 text-sm text-text-primary',
              'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600',
              className,
            )}
            {...props}
          >
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <ChevronDown
            className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
            aria-hidden="true"
          />
        </div>
      </div>
    );
  },
);
Select.displayName = 'Select';
