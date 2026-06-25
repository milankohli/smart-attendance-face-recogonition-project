import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

/**
 * ProtectedRoute
 * ──────────────
 * Wraps routes that require authentication.
 *
 * Props
 * ─────
 * children  — content to render when access is granted.
 * roles     — optional string[] of allowed roles (e.g. ["admin"], ["viewer"]).
 *             When omitted, any authenticated user is allowed.
 *
 * Behaviour
 * ─────────
 * • While the auth state is bootstrapping (loading=true) renders a spinner
 *   to avoid a flash-redirect before the stored token is validated.
 * • Unauthenticated users are redirected to /login with the intended path
 *   preserved in location state so LoginPage can redirect back after sign-in.
 * • Authenticated users whose role is not in `roles` are redirected to the
 *   appropriate home page for their role:
 *     admin  → /dashboard
 *     viewer → /viewer
 *
 * Security notes (new flow)
 * ─────────────────────────
 * • Admin routes  (/dashboard, /students, /attendance, /analytics, /export,
 *   /users) all pass roles={["admin"]}.  A viewer hitting these is sent to
 *   /viewer.
 * • Viewer route  (/viewer) passes roles={["viewer"]}.  An admin hitting
 *   /viewer is sent to /dashboard.
 * • /login and /register are handled by PublicOnlyRoute (separate component)
 *   so authenticated users are bounced away from those pages too.
 */
export default function ProtectedRoute({ children, roles }) {
  const { user, loading, isAuthenticated } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <span className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Role guard: send each role to their own home rather than a generic 403.
  if (roles && !roles.includes(user?.role)) {
    const home = user?.role === "admin" ? "/dashboard" : "/viewer";
    return <Navigate to={home} replace />;
  }

  return children;
}
