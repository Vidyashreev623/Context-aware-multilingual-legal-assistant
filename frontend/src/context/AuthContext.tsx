import { createContext, useContext, type ReactNode } from "react";
import { useAuthLogic } from "../hooks/useAuth";

type AuthContextType = ReturnType<typeof useAuthLogic>;

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const auth = useAuthLogic();
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}