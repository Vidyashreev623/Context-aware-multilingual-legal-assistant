import type { ReactNode } from "react";

// Shared card shell for Login / Signup / ForgotPassword so the three
// screens look identical and a styling change happens in one place.
export default function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen w-screen flex items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl shadow-sm p-8">
        <h1 className="text-xl font-bold text-indigo-700 text-center leading-tight">
  Context-Aware Multilingual Legal Assistant
</h1>
        <h2 className="text-lg font-semibold text-slate-800 text-center mt-4">{title}</h2>
        {subtitle && <p className="text-sm text-slate-500 text-center mt-1 mb-5">{subtitle}</p>}
        {!subtitle && <div className="mb-5" />}
        {children}
      </div>
    </div>
  );
}

export const inputClass =
  "w-full border border-slate-300 rounded-xl px-3 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-400";
export const primaryButtonClass =
  "w-full bg-indigo-600 text-white py-2.5 rounded-xl font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed";

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="mb-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
      {message}
    </div>
  );
}

export function InfoBox({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="mb-3 text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
      {message}
    </div>
  );
}
