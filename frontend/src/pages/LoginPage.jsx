import { useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

/**
 * LoginPage
 * ─────────
 * Two-tab login page:
 *   [Admin Login]  [Viewer Login]
 *
 * Below the card:
 *   "Don't have an account? Register as Viewer"
 *
 * Behaviour
 * ─────────
 * • Admin login  → redirects to /dashboard (or the saved "from" path).
 * • Viewer login → always redirects to /viewer.
 * • If an authenticated admin tries to access /viewer they are bounced back
 *   to /dashboard by ProtectedRoute (unchanged behaviour).
 */

const TABS = /** @type {const} */ (["admin", "viewer"]);

export default function LoginPage() {
  const { login }  = useAuth();
  const navigate   = useNavigate();
  const location   = useLocation();

  const from = location.state?.from?.pathname || null;

  const [activeTab, setActiveTab]       = useState(/** @type {"admin"|"viewer"} */ ("admin"));
  const [form, setForm]                 = useState({ username: "", password: "" });
  const [error, setError]               = useState("");
  const [loading, setLoading]           = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Reset form state when switching tabs
  const handleTabChange = (tab) => {
    if (tab === activeTab) return;
    setActiveTab(tab);
    setForm({ username: "", password: "" });
    setError("");
    setShowPassword(false);
  };

  const handleChange = (e) =>
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.username || !form.password) {
      setError("Both fields are required.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const me = await login(form.username, form.password);

      // Role-based redirect guard: if the tab and the actual role don't match,
      // show a clear error rather than silently routing them somewhere wrong.
      if (me.role === "viewer" && activeTab === "admin") {
        setError("This account does not have admin access. Use Viewer Login.");
        return;
      }
      if (me.role === "admin" && activeTab === "viewer") {
        setError("Admin accounts cannot use the Viewer Login.");
        return;
      }

      if (me.role === "viewer") {
        navigate("/viewer", { replace: true });
      } else {
        navigate(from && from !== "/login" ? from : "/dashboard", { replace: true });
      }
    } catch (err) {
      const msg =
        err?.response?.data?.detail ||
        "Unable to sign in. Check your credentials and try again.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const placeholderUsername = activeTab === "admin" ? "admin" : "your_username";

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4">
      {/* Background glow */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute left-1/2 top-1/3 h-[500px] w-[500px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-indigo-700/10 blur-3xl" />
      </div>

      <div className="relative w-full max-w-sm">
        {/* Logo mark */}
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 shadow-lg shadow-indigo-700/40">
            <svg className="h-7 w-7 text-white" fill="currentColor" viewBox="0 0 20 20">
              <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
              <path
                fillRule="evenodd"
                d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z"
                clipRule="evenodd"
              />
            </svg>
          </div>
          <div className="text-center">
            <h1 className="text-xl font-bold tracking-tight text-white">Smart Attendance</h1>
            <p className="text-sm text-slate-500">Sign in to your account</p>
          </div>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-2xl">

          {/* ── Role tabs ───────────────────────────────────────────────── */}
          <div className="mb-6 flex rounded-xl border border-slate-700 bg-slate-800 p-1">
            {TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => handleTabChange(tab)}
                className={[
                  "flex-1 rounded-lg py-2 text-sm font-medium transition-all",
                  activeTab === tab
                    ? "bg-indigo-600 text-white shadow"
                    : "text-slate-400 hover:text-slate-200",
                ].join(" ")}
              >
                {tab === "admin" ? "Admin Login" : "Viewer Login"}
              </button>
            ))}
          </div>

          {/* ── Form ────────────────────────────────────────────────────── */}
          <form onSubmit={handleSubmit} noValidate className="space-y-5">
            {/* Username */}
            <div className="space-y-1.5">
              <label htmlFor="username" className="block text-sm font-medium text-slate-300">
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                autoFocus
                value={form.username}
                onChange={handleChange}
                placeholder={placeholderUsername}
                className="block w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 transition-colors focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>

            {/* Password */}
            <div className="space-y-1.5">
              <label htmlFor="password" className="block text-sm font-medium text-slate-300">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={form.password}
                  onChange={handleChange}
                  placeholder="••••••••"
                  className="block w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 pr-10 text-sm text-slate-100 placeholder-slate-500 transition-colors focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? (
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    </svg>
                  ) : (
                    <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="flex items-center gap-2 rounded-xl border border-rose-800/50 bg-rose-950/50 px-4 py-3 text-sm text-rose-400">
                <svg className="h-4 w-4 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-indigo-700/30 transition-all hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading && (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              )}
              {loading ? "Signing in…" : `Sign in as ${activeTab === "admin" ? "Admin" : "Viewer"}`}
            </button>
          </form>
        </div>

        {/* ── Viewer registration link ─────────────────────────────────── */}
        <p className="mt-5 text-center text-sm text-slate-400">
          Don&apos;t have an account?{" "}
          <Link
            to="/register"
            className="font-medium text-indigo-400 underline-offset-2 hover:text-indigo-300 hover:underline"
          >
            Register as Viewer
          </Link>
        </p>

        <p className="mt-4 text-center text-xs text-slate-600">
          Smart Attendance System · Face Recognition
        </p>
      </div>
    </div>
  );
}
