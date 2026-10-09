import { useEffect, useRef, useState } from "react";
import { getCurrentUser } from "../services/api";
import { clearSession, getStoredUser, saveSession } from "../services/session";

// Top-right profile: a circle with the user's initial; click it to see
// their name + email and a Logout button.
export default function ProfileMenu() {
  const stored = getStoredUser();
  const [name, setName] = useState<string | null>(stored.name);
  const [email, setEmail] = useState<string | null>(stored.email);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Refresh name/email from the server (covers accounts created before
  // names existed, and a page reload with only the token stored). A 401
  // means the stored session is dead -> send the user to log in again.
  useEffect(() => {
    const token = sessionStorage.getItem("nyaya_token");
    if (!token) return;
    getCurrentUser()
      .then((u) => {
        setName(u.name);
        setEmail(u.email);
        saveSession({ access_token: token, email: u.email, name: u.name });
      })
      .catch((err: Error) => {
        if (/session|authenticated|expired/i.test(err.message)) {
          clearSession();
          window.location.assign("/login");
        }
      });
  }, []);

  // Close when clicking anywhere outside the menu.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const display = name || email || "User";
  const initial = display.trim().charAt(0).toUpperCase() || "U";

  const logout = () => {
    clearSession();
    window.location.assign("/login");
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title={display}
        className="w-9 h-9 rounded-full bg-indigo-600 text-white font-semibold flex items-center justify-center hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-300"
      >
        {initial}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-60 bg-white border border-slate-200 rounded-xl shadow-lg z-50 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100">
            <div className="font-semibold text-slate-800 truncate">{name || "Your account"}</div>
            {email && <div className="text-xs text-slate-500 truncate">{email}</div>}
          </div>
          <button
            type="button"
            onClick={logout}
            className="w-full text-left px-4 py-2.5 text-sm text-red-600 hover:bg-red-50"
          >
            Log out
          </button>
        </div>
      )}
    </div>
  );
}
