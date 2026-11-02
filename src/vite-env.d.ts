/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DEV_USER_ID?: string;
  readonly VITE_DEV_USER_NAME?: string;
  readonly VITE_DEV_USER_EMAIL?: string;
  readonly VITE_DEV_ORGANIZATION_ID?: string;
  readonly VITE_DEV_ORGANIZATION_NAME?: string;
  /** "true" adds OIDC `prompt=create` to the email + password invitation sign-up, for providers that support it. */
  readonly VITE_OIDC_SIGNUP_PROMPT_CREATE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
