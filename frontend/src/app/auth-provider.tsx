import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { loginUser, registerUser } from "@/api/auth";
import { setAccessToken } from "@/api/client";
import {
  clearStoredTokens,
  getStoredTokens,
  storeTokens,
} from "@/lib/auth-storage";

export interface AuthContextValue {
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(
    () => getStoredTokens() !== null,
  );

  useEffect(() => {
    setAccessToken(getStoredTokens()?.accessToken ?? null);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await loginUser({ email, password });
    storeTokens({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
    });
    setAccessToken(tokens.access_token);
    setIsAuthenticated(true);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    await registerUser({ email, password });
  }, []);

  const logout = useCallback(() => {
    clearStoredTokens();
    setAccessToken(null);
    setIsAuthenticated(false);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ isAuthenticated, login, register, logout }),
    [isAuthenticated, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
