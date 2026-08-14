import axios, { AxiosError, type AxiosInstance } from "axios";

import { env } from "@/lib/env";
import { clearStoredTokens } from "@/lib/auth-storage";
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
  headers: {
    "Content-Type": "application/json",
  },
});

export function setAccessToken(token: string | null): void {
  if (token) {
    apiClient.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete apiClient.defaults.headers.common.Authorization;
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiEnvelope<unknown>>) => {
    if (error.response) {
      const { status, data } = error.response;
      if (status === 401 && error.config?.url !== "/auth/login") {
        clearStoredTokens();
        setAccessToken(null);
        window.location.assign("/login");
      }
      throw new ApiError(
        status,
        data?.error?.code ?? `http_${status}`,
        data?.error?.message ?? "Request failed.",
      );
    }
    throw new ApiError(0, "network_error", error.message || "Network error.");
  },
);
