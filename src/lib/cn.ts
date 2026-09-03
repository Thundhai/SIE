/**
 * Joins conditional class-name fragments, dropping falsy values. A small,
 * dependency-free stand-in for `clsx` — the new SIE component layer is
 * small enough that pulling in a library for this one helper isn't
 * justified yet (see this milestone's own "don't over-engineer" guidance).
 */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}
