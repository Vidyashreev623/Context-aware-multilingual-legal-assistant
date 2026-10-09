import { useEffect, useState } from "react";
import { ErrorBox, inputClass, primaryButtonClass } from "./AuthLayout";

const RESEND_SECONDS = 30;

// The "enter the 6-digit code we emailed you" step, shared by signup
// and forgot-password (identical UI, different API calls).
export default function CodeEntry({
  email,
  isBusy,
  error,
  onVerify,
  onResend,
  onChangeEmail,
}: {
  email: string;
  isBusy: boolean;
  error: string | null;
  onVerify: (code: string) => void;
  onResend: () => void;
  onChangeEmail: () => void;
}) {
  const [code, setCode] = useState("");
  const [secondsLeft, setSecondsLeft] = useState(RESEND_SECONDS);

  useEffect(() => {
    if (secondsLeft <= 0) return;
    const t = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [secondsLeft]);

  return (
    <div>
      <p className="text-sm text-slate-600 mb-4 text-center">
        We sent a 6-digit code to <span className="font-medium text-slate-800">{email}</span>.
      </p>
      <ErrorBox message={error} />
      <input
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
        inputMode="numeric"
        autoComplete="one-time-code"
        placeholder="000000"
        maxLength={6}
        className={`${inputClass} text-center text-2xl tracking-[0.5em] font-mono`}
      />
      <button
        type="button"
        disabled={isBusy || code.length !== 6}
        onClick={() => onVerify(code)}
        className={`${primaryButtonClass} mt-4`}
      >
        {isBusy ? "Verifying..." : "Verify code"}
      </button>
      <div className="flex items-center justify-between mt-4 text-sm">
        <button type="button" onClick={onChangeEmail} className="text-slate-500 hover:text-slate-700">
          Change email
        </button>
        <button
          type="button"
          disabled={secondsLeft > 0 || isBusy}
          onClick={() => {
            setCode("");
            setSecondsLeft(RESEND_SECONDS);
            onResend();
          }}
          className="text-indigo-600 hover:text-indigo-800 disabled:text-slate-400 disabled:cursor-not-allowed"
        >
          {secondsLeft > 0 ? `Resend code in ${secondsLeft}s` : "Resend code"}
        </button>
      </div>
    </div>
  );
}
