// Small helpers around the sessionStorage keys the app already uses
// ("nyaya_token", "nyaya_email" -- same keys as hooks/useAuth.ts), plus
// "nyaya_name" for the profile menu. Kept in one place so Login, Signup,
// ForgotPassword and ProfileMenu can't drift apart on key names.
import type { AuthResult } from "./api";

const TOKEN_KEY = "nyaya_token";
const EMAIL_KEY = "nyaya_email";
const NAME_KEY = "nyaya_name";

export function saveSession(res: AuthResult): void {
  sessionStorage.setItem(TOKEN_KEY, res.access_token);
  sessionStorage.setItem(EMAIL_KEY, res.email);
  if (res.name) sessionStorage.setItem(NAME_KEY, res.name);
  else sessionStorage.removeItem(NAME_KEY);
}

export function clearSession(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(EMAIL_KEY);
  sessionStorage.removeItem(NAME_KEY);
}

export function getStoredUser(): { email: string | null; name: string | null } {
  return {
    email: sessionStorage.getItem(EMAIL_KEY),
    name: sessionStorage.getItem(NAME_KEY),
  };
}
