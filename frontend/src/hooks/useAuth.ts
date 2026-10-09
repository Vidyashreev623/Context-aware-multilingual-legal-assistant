import { useCallback, useState } from "react";
import { login as apiLogin } from "../services/api";
import { saveSession, clearSession } from "../services/session";

const TOKEN_KEY = "nyaya_token";
const EMAIL_KEY = "nyaya_email";

// Signup is no longer a single call: it's now email -> emailed code ->
// name + password (see pages/Signup.tsx), which ends by calling
// saveSession() directly. So this hook no longer exposes `signup`;
// it still exposes token/email/login/logout exactly as before.
export function useAuthLogic() {
  const [token, setToken] = useState<string | null>(() => sessionStorage.getItem(TOKEN_KEY));
  const [email, setEmail] = useState<string | null>(() => sessionStorage.getItem(EMAIL_KEY));
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const login = useCallback(async (emailInput: string, password: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await apiLogin({ email: emailInput, password });
      saveSession(res);
      setToken(res.access_token);
      setEmail(res.email);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to log in.");
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setToken(null);
    setEmail(null);
  }, []);

  return { token, email, isLoading, error, login, logout };
}
