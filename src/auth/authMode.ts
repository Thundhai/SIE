/**
 * The single switch between development and production authentication —
 * SIE Milestone G3-1: Login & Production Session.
 *
 * Deliberately keyed off Vite's own native `import.meta.env.MODE`
 * ("production" after `vite build`, "development" under `vite dev`,
 * "test" under Vitest) rather than an app-defined environment variable.
 * `MODE` is derived from the build/dev command itself, not from an
 * arbitrary `.env` value a deployment could set by mistake — exactly the
 * property the G3-0 audit flagged as missing: `VITE_DEV_USER_ID`/
 * `VITE_DEV_ORGANIZATION_ID` being present in a production build's
 * environment must never be enough, on its own, to activate development
 * identity. See `devIdentity.ts`'s own production gate, which calls this.
 *
 * Not `import.meta.env.PROD`/`DEV` (the boolean mirrors of the same
 * value): those are awkward to stub in tests (Vitest's `vi.stubEnv` sets
 * string values), while `MODE` is a plain string every existing test in
 * this codebase already knows how to stub the same way as
 * `VITE_DEV_USER_ID`.
 */
export type AuthMode = 'dev' | 'production';

/** The only two values Vite's own tooling ever produces for this
 * repository: "development" (`vite dev`) and "test" (`vitest run`/
 * `vitest`). Deliberately an allowlist, not "anything that isn't
 * literally 'production'" — mirrors the backend's own `DEV_MODE:
 * bool = False` fail-closed default (`backend/app/core/config.py`): an
 * unrecognized or unexpected `MODE` value (e.g. a deployment that ran
 * `vite build --mode staging`) resolves to `'production'`, the more
 * restrictive outcome, rather than accidentally activating development
 * identity on a build nobody actually ran via `vite dev`. */
const DEV_MODES = new Set(['development', 'test']);

export function getAuthMode(): AuthMode {
  return DEV_MODES.has(import.meta.env.MODE) ? 'dev' : 'production';
}
