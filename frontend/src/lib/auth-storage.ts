export interface StoredTokens {
  accessToken: string;
  refreshToken: string;
}

const AUTH_STORAGE_KEY = "docmind.auth";

export function getStoredTokens(): StoredTokens | null {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      typeof (parsed as StoredTokens).accessToken === "string" &&
      typeof (parsed as StoredTokens).refreshToken === "string"
    ) {
      return parsed as StoredTokens;
    }
    return null;
  } catch {
    return null;
  }
}

export function storeTokens(tokens: StoredTokens): void {
  localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(tokens));
}

export function clearStoredTokens(): void {
  localStorage.removeItem(AUTH_STORAGE_KEY);
}
