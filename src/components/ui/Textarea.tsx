import { TextareaHTMLAttributes, forwardRef, useId } from 'react';
import { cn } from '../../lib/cn';

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  hideLabel?: boolean;
  helperText?: string;
  errorText?: string;
}

/** A multi-line counterpart to `Input`, built to the exact same
 * always-labeled contract — for a description/narrative/comment field
 * (e.g. Actions' create/edit forms), never a bare `<textarea>` at a call
 * site. */
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, hideLabel, helperText, errorText, id, className, rows = 4, ...props }, ref) => {
    const generatedId = useId();
    const textareaId = id ?? generatedId;
    const helperId = helperText ? `${textareaId}-helper` : undefined;
    const errorId = errorText ? `${textareaId}-error` : undefined;

    return (
      <div className="flex flex-col gap-1">
        <label htmlFor={textareaId} className={hideLabel ? 'sr-only' : 'text-xs font-medium text-text-secondary'}>
          {label}
        </label>
        <textarea
          ref={ref}
          id={textareaId}
          rows={rows}
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
Textarea.displayName = 'Textarea';
