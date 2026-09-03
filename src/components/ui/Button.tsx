import { ButtonHTMLAttributes, forwardRef } from 'react';
import { cn } from '../../lib/cn';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const VARIANT_STYLES: Record<ButtonVariant, string> = {
  primary: 'bg-navy-800 text-white hover:bg-navy-700 disabled:bg-navy-800/50',
  secondary: 'bg-surface text-text-primary border border-border-strong hover:bg-surface-muted',
  ghost: 'bg-transparent text-text-secondary hover:bg-surface-muted',
  danger: 'bg-critical text-white hover:brightness-95',
};

const SIZE_STYLES: Record<ButtonSize, string> = {
  sm: 'px-2.5 py-1.5 text-xs',
  md: 'px-3.5 py-2 text-sm',
};

/** The one button primitive for the new SIE frontend — semantic
 * `<button>` (never a styled `<div>`), a real `disabled` attribute
 * (never CSS-only disabled styling), and the shared focus-visible ring
 * (src/index.css). */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', className, type = 'button', ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-60',
        VARIANT_STYLES[variant],
        SIZE_STYLES[size],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = 'Button';
