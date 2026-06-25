import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

/**
 * PublicOnlyRoute
 * ───────────────
 * Wraps routes that should only be accessible to unauthenticated users
 * (e.g. /login, /register).
 *
 * If the user is already authenticated, they are redirected to their
 * role-appropriate home page rather than being shown the login or
 * register page again:
 *   admin  → /dashboard
 *   viewer → /viewer
 *
 * While the auth state is bootstrapping (loading=true) a spinner is shown
 * to avoid a premature redirect before the stored token is validated.
 */
export default function PublicOnlyRoute({ children }) {
  const { user, loading, isAuthenticated } = useAuth();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <span className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  if (isAuthenticated && user) {
    const home = user.role === "admin" ? "/dashboard" : "/viewer";
    return <Navigate to={home} replace />;
  }

  return children;
}
