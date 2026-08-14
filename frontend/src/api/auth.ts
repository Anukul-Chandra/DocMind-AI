import { apiClient } from "@/api/client";
import type { ApiEnvelope } from "@/types";

export interface UserResponse {
  user_id: string;
  email: string;
  is_active: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export interface RegisterInput {
  email: string;
  password: string;
}

export async function loginUser(input: LoginInput): Promise<TokenResponse> {
  const response = await apiClient.post<ApiEnvelope<TokenResponse>>(
    "/auth/login",
    input,
  );
  return response.data.data!;
}

export async function registerUser(input: RegisterInput): Promise<UserResponse> {
  const response = await apiClient.post<ApiEnvelope<UserResponse>>(
    "/auth/register",
    input,
  );
  return response.data.data!;
}
