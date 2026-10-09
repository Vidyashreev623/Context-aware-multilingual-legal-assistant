import type { Language } from "../types";

const OPTIONS: { value: Language; label: string }[] = [
  { value: "auto", label: "Auto Detect" },
  { value: "en", label: "English" },
  { value: "kn", label: "ಕನ್ನಡ" },
  { value: "hi", label: "हिन्दी" },
];

interface Props {
  value: Language;
  onChange: (lang: Language) => void;
}

export default function LanguageSelector({ value, onChange }: Props) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-600">
      <span>Language:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as Language)}
        className="border border-slate-300 rounded-md px-2 py-1 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400"
      >
        {OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
