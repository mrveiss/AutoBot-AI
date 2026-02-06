/// <reference types="vite/client" />
/// <reference types="./src/types/pinia-persist" />
/// <reference types="./src/types/app-config" />

interface ImportMeta {
  readonly env: ImportMetaEnv
}

// Remove the module declaration since we have a proper TypeScript file now
