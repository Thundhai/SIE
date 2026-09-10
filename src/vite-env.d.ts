/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DEV_USER_ID?: string;
  readonly VITE_DEV_USER_NAME?: string;
  readonly VITE_DEV_USER_EMAIL?: string;
  readonly VITE_DEV_ORGANIZATION_ID?: string;
  readonly VITE_DEV_ORGANIZATION_NAME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
