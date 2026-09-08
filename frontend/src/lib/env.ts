const rawApiBaseUrl = import.meta.env.VITE_API_BASE_URL;
const apiBaseUrl =
  rawApiBaseUrl ??
  (import.meta.env.PROD
    ? (() => {
        throw new Error(
          "VITE_API_BASE_URL is required in production. Set it to your backend URL (e.g. https://your-backend.onrender.com) in the Vercel environment variables.",
        );
      })()
    : "http://localhost:8000");

export const env = {
  apiBaseUrl,
  apiTimeoutMs: Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 60_000),
} as const;
