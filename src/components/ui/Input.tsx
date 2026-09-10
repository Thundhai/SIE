import { InputHTMLAttributes, forwardRef, useId } from 'react';
import { cn } from '../../lib/cn';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  /** Visually hides the label while keeping it in the accessibility
   * tree — use for a control whose purpose is already obvious from
   * context (e.g. inside a compact filter bar), never to skip labeling
   * altogether (§18: accessible form labels are required). */
  hideLabel?: boolean;
  helperText?: string;
  errorText?: string;
}

/** Always renders a real, associated `<label>` — every text input in
 * the new SIE frontend goes through this component specifically so that
 * guarantee can never be forgotten at a call site. */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, hideLabel, helperText, errorText, id, className, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id ?? generatedId;
    const helperId = helperText ? `${inputId}-helper` : undefined;
    const errorId = errorText ? `${inputId}-error` : undefined;

    return (
      <div className="flex flex-col gap-1">
        <label htmlFor={inputId} className={hideLabel ? 'sr-only' : 'text-xs font-medium text-text-secondary'}>
          {label}
        </label>
        <input
          ref={ref}
          id={inputId}
          aria-describedby={cn(helperId, errorId) || undefined}
          aria-invalid={errorText ? true : undefined}
          className={cn(
            'rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-text-primary',
            'placeholder:text-text-muted',
            'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600',
            errorText && 'border-critical',
            className,
          )}
          {...props}
        />
        {helperText && !errorText && (
          <p id={helperId} className="text-xs text-text-muted">
            {helperText}
          </p>
        )}
        {errorText && (
          <p id={errorId} className="text-xs text-critical">
            {errorText}
          </p>
        )}
      </div>
    );
  },
);
Input.displayName = 'Input';
