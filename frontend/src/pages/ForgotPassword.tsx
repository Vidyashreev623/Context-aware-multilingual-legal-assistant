import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthLayout, { ErrorBox, InfoBox, inputClass, primaryButtonClass } from "../components/AuthLayout";
import CodeEntry from "../components/CodeEntry";
import { requestPasswordResetCode, resetPassword, verifyPasswordResetCode } from "../services/api";

type Step = "email" | "code" | "password" | "done";

// Forgot password: 1) enter email -> we email a 6-digit code
//                  2) enter the code
//                  3) choose a new password -> back to login
export default function ForgotPassword() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [verifiedToken, setVerifiedToken] = useState("");
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

  const finish = () => {
    if (password.length < 8) return setError("Password must be at least 8 characters.");
    if (password !== confirm) return setError("Passwords do not match.");
    run(async () => {
      await resetPassword({ email: email.trim(), verified_token: verifiedToken, new_password: password });
      setStep("done");
      setTimeout(() => navigate("/login"), 2000);
    });
  };

  return (
    <AuthLayout
      title="Reset your password"
      subtitle={
        step === "email"
          ? "Enter your email and we'll send you a reset code."
          : step === "code"
            ? "Enter the code we emailed you"
            : step === "password"
              ? "Choose a new password."
              : undefined
      }
    >
      {step === "email" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => {
              await requestPasswordResetCode(email.trim());
              setStep("code");
            });
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
            {busy ? "Sending code..." : "Send reset code"}
          </button>
        </form>
      )}

      {step === "code" && (
        <>
          <CodeEntry
            email={email}
            isBusy={busy}
            error={error}
            onVerify={(code) =>
              run(async () => {
                const res = await verifyPasswordResetCode(email.trim(), code);
                setVerifiedToken(res.verified_token);
                setStep("password");
              })
            }
            onResend={() =>
              run(async () => {
                await requestPasswordResetCode(email.trim());
                setInfo("A new code has been sent.");
              })
            }
            onChangeEmail={() => {
              setError(null);
              setStep("email");
            }}
          />
          <div className="mt-3"><InfoBox message={info} /></div>
        </>
      )}

      {step === "password" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            finish();
          }}
        >
          <ErrorBox message={error} />
          <input
            type="password"
            required
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="New password (min 8 characters)"
            className={`${inputClass} mb-3`}
          />
          <input
            type="password"
            required
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Confirm new password"
            className={inputClass}
          />
          <button type="submit" disabled={busy} className={`${primaryButtonClass} mt-4`}>
            {busy ? "Saving..." : "Reset password"}
          </button>
        </form>
      )}

      {step === "done" && (
        <InfoBox message="Your password has been reset. Redirecting you to log in..." />
      )}

      <p className="text-sm text-slate-500 text-center mt-5">
        <Link to="/login" className="text-indigo-600 font-medium hover:text-indigo-800">
          Back to log in
        </Link>
      </p>
    </AuthLayout>
  );
}
