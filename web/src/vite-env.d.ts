/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly OWNER_API_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
