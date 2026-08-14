export const env = {
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
  apiTimeoutMs: Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 60_000),
} as const;
