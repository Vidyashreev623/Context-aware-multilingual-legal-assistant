import { useState } from "react";
import { Link } from "react-router-dom";
import AuthLayout, { ErrorBox, InfoBox, inputClass, primaryButtonClass } from "../components/AuthLayout";
import CodeEntry from "../components/CodeEntry";
import { completeSignup, requestSignupCode, verifySignupCode } from "../services/api";
import { saveSession } from "../services/session";

type Step = "email" | "code" | "details";

// Signup: 1) enter email -> we email a 6-digit code
//         2) enter the code -> email is verified
//         3) enter name + choose password -> account created, logged in
export default function Signup() {
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [verifiedToken, setVerifiedToken] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  const sendCode = () =>
    run(async () => {
      await requestSignupCode(email.trim());
      setStep("code");
    });

  const verify = (code: string) =>
    run(async () => {
      const res = await verifySignupCode(email.trim(), code);
      setVerifiedToken(res.verified_token);
      setStep("details");
    });

  const finish = () => {
    if (password.length < 8) return setError("Password must be at least 8 characters.");
    if (password !== confirm) return setError("Passwords do not match.");
    run(async () => {
      const res = await completeSignup({
        email: email.trim(),
        verified_token: verifiedToken,
        name: name.trim(),
        password,
      });
      saveSession(res);
      // Full navigation so the app's auth state re-reads the session.
      window.location.assign("/chat");
    });
  };

  return (
    <AuthLayout
      title="Create your account"
      subtitle={
        step === "email"
          ? "Enter your email and we'll send you a verification code."
          : step === "code"
            ? "Verify your email"
            : "Almost done — tell us your name and set a password."
      }
    >
      {step === "email" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            sendCode();
          }}
        >
          <ErrorBox message={error} />
          <input
            type="email"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className={inputClass}
          />
          <button type="submit" disabled={busy || !email} className={`${primaryButtonClass} mt-4`}>
            {busy ? "Sending code..." : "Send verification code"}
          </button>
        </form>
      )}

      {step === "code" && (
        <CodeEntry
          email={email}
          isBusy={busy}
          error={error}
          onVerify={verify}
          onResend={() =>
            run(async () => {
              await requestSignupCode(email.trim());
              setInfo("A new code has been sent.");
            })
          }
          onChangeEmail={() => {
            setError(null);
            setStep("email");
          }}
        />
      )}
      {step === "code" && <div className="mt-3"><InfoBox message={info} /></div>}

      {step === "details" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            finish();
          }}
        >
          <ErrorBox message={error} />
          <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 mb-3">
            ✓ {email} verified
          </p>
          <input
            required
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Full name"
            className={`${inputClass} mb-3`}
          />
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password (min 8 characters)"
            className={`${inputClass} mb-3`}
          />
          <input
            type="password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Confirm password"
            className={inputClass}
          />
          <button type="submit" disabled={busy || !name.trim()} className={`${primaryButtonClass} mt-4`}>
            {busy ? "Creating account..." : "Create account"}
          </button>
        </form>
      )}

      <p className="text-sm text-slate-500 text-center mt-5">
        Already have an account?{" "}
        <Link to="/login" className="text-indigo-600 font-medium hover:text-indigo-800">
          Log in
        </Link>
      </p>
    </AuthLayout>
  );
}
