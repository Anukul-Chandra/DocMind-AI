// Token refresh orchestration for the API client.
//
// The pure refresh logic (single-flight deduplication and loop protection)
// lives here with injected dependencies so it can be exercised directly by
// Node via type stripping, matching the repository's focused-script test
// style. The axios response interceptor in src/api/client.ts is thin glue that
// supplies the real storage and network implementations.

export interface StoredTokens {
  accessToken: string;
  refreshToken: string;
}

export interface RefreshTokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface RefreshApi {
  refresh(refreshToken: string): Promise<RefreshTokenPair>;
}

export interface TokenStorage {
  getStoredTokens(): StoredTokens | null;
  storeTokens(tokens: StoredTokens): void;
  clearStoredTokens(): void;
}

// Paths that must never trigger a refresh attempt. A failed refresh on
// /auth/login or /auth/refresh must not cascade into another refresh.
const REFRESH_EXCLUDED_PATHS = ["/auth/login", "/auth/refresh"];

export function isRefreshableRequest(
  url: string | undefined,
  alreadyRetried: boolean,
): boolean {
  if (alreadyRetried) return false;
  if (!url) return true;
  const path = url.split("?")[0];
  return !REFRESH_EXCLUDED_PATHS.includes(path);
}

let singleFlight: Promise<string> | null = null;

export function resetTokenRefresh(): void {
  singleFlight = null;
}

export function refreshAccessToken(
  api: RefreshApi,
  storage: TokenStorage,
): Promise<string> {
  if (singleFlight) return singleFlight;
  const attempt = (async (): Promise<string> => {
    const stored = storage.getStoredTokens();
    if (!stored) {
      throw new Error("No stored refresh token.");
    }
    const pair = await api.refresh(stored.refreshToken);
    storage.storeTokens({
      accessToken: pair.access_token,
      refreshToken: pair.refresh_token,
    });
    return pair.access_token;
  })();
  singleFlight = attempt.finally(() => {
    singleFlight = null;
  });
  return singleFlight;
}