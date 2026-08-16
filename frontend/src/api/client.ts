import axios, {
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";

import { env } from "@/lib/env";
import {
  clearStoredTokens,
  getStoredTokens,
  storeTokens,
} from "@/lib/auth-storage";
import {
  isRefreshableRequest,
  refreshAccessToken,
  type RefreshTokenPair,
  type TokenStorage,
} from "@/lib/token-refresh";
import type { ApiEnvelope } from "@/types";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: env.apiBaseUrl,
  timeout: env.apiTimeoutMs,
});

export function setAccessToken(token: string | null): void {
  if (token) {
    apiClient.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete apiClient.defaults.headers.common.Authorization;
  }
}

interface RefreshableRequestConfig extends InternalAxiosRequestConfig {
  _retried?: boolean;
}

const refreshApi = {
  async refresh(refreshToken: string): Promise<RefreshTokenPair> {
    const response = await axios.post<ApiEnvelope<RefreshTokenPair>>(
      `${env.apiBaseUrl}/auth/refresh`,
      { refresh_token: refreshToken },
      { timeout: env.apiTimeoutMs },
    );
    const pair = response.data?.data;
    if (!pair) {
      throw new Error("Refresh response did not include a token pair.");
    }
    return pair;
  },
};

const refreshStorage: TokenStorage = {
  getStoredTokens: () => getStoredTokens(),
  storeTokens: (tokens) => storeTokens(tokens),
  clearStoredTokens: () => clearStoredTokens(),
};

function logoutAndRedirect(): void {
  refreshStorage.clearStoredTokens();
  setAccessToken(null);
  window.location.assign("/login");
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiEnvelope<unknown>>) => {
    if (!error.response) {
      throw new ApiError(0, "network_error", error.message || "Network error.");
    }

    const { status, data } = error.response;
    const config = error.config as RefreshableRequestConfig | undefined;

    if (
      status === 401 &&
      config &&
      isRefreshableRequest(config.url, config._retried === true)
    ) {
      try {
        const newAccessToken = await refreshAccessToken(
          refreshApi,
          refreshStorage,
        );
        config.headers.set("Authorization", `Bearer ${newAccessToken}`);
        config._retried = true;
        return apiClient.request(config);
      } catch {
        logoutAndRedirect();
        throw new ApiError(
          status,
          "unauthorized",
          "Your session has expired. Please log in again.",
        );
      }
    }

    if (status === 401 && error.config?.url !== "/auth/login") {
      logoutAndRedirect();
    }

    throw new ApiError(
      status,
      data?.error?.code ?? `http_${status}`,
      data?.error?.message ?? "Request failed.",
    );
  },
);
