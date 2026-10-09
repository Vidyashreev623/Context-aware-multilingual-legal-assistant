import { useState } from "react";
import { Link } from "react-router-dom";
import AuthLayout, { ErrorBox, inputClass, primaryButtonClass } from "../components/AuthLayout";
import { login } from "../services/api";
import { saveSession } from "../services/session";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await login({ email: email.trim(), password });
      saveSession(res);
      // Full navigation so the app's auth state re-reads the session.
      window.location.assign("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to log in.");
      setBusy(false);
    }
  };

  return (
    <AuthLayout title="Welcome back" subtitle="Log in to continue to NyayaAI.">
      <form onSubmit={submit}>
        <ErrorBox message={error} />
        <input
          type="email"
          required
          autoFocus
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          className={`${inputClass} mb-3`}
        />
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className={inputClass}
        />
        <div className="text-right mt-2">
          <Link to="/forgot-password" className="text-sm text-indigo-600 hover:text-indigo-800">
            Forgot password?
          </Link>
        </div>
        <button type="submit" disabled={busy || !email || !password} className={`${primaryButtonClass} mt-4`}>
          {busy ? "Logging in..." : "Log in"}
        </button>
      </form>
      <p className="text-sm text-slate-500 text-center mt-5">
        New here?{" "}
        <Link to="/signup" className="text-indigo-600 font-medium hover:text-indigo-800">
          Create an account
        </Link>
      </p>
    </AuthLayout>
  );
}
