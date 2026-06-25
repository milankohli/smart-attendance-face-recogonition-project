import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./hooks/useAuth";
import ProtectedRoute from "./components/ProtectedRoute";
import PublicOnlyRoute from "./components/PublicOnlyRoute";
import DashboardLayout from "./layouts/DashboardLayout";
import LoginPage from "./pages/LoginPage";
import ViewerRegisterPage from "./pages/ViewerRegisterPage";
import DashboardPage from "./pages/DashboardPage";
import StudentsPage from "./pages/StudentsPage";
import AttendancePage from "./pages/AttendancePage";
import AnalyticsPage from "./pages/AnalyticsPage";
import ExportPage from "./pages/ExportPage";
import UsersPage from "./pages/UsersPage";
import ViewerDashboardPage from "./pages/ViewerDashboardPage";

/**
 * App — root router
 * ─────────────────
 * Changes from previous version
 * ──────────────────────────────
 * • /register     — NEW public route for viewer self-registration.
 *                   Wrapped in PublicOnlyRoute so already-authenticated
 *                   users are bounced to their dashboard.
 *
 * • /login        — now wrapped in PublicOnlyRoute for the same reason.
 *
 * • /users        — kept as an admin-only route. The page is unchanged;
 *                   admins can still manage user accounts (PATCH /users,
 *                   DELETE /users) from here. What's removed is the ability
 *                   to trigger viewer account creation from the Students flow.
 *
 * Security invariants (enforced by ProtectedRoute)
 * ─────────────────────────────────────────────────
 * • Viewers  cannot access any /dashboard, /students, /attendance,
 *   /analytics, /export, or /users route.
 * • Admins   cannot access /viewer.
 * • Both are redirected to their correct home if they try.
 */
export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* ── Public (unauthenticated only) ─────────────────────────── */}
          <Route
            path="/login"
            element={
              <PublicOnlyRoute>
                <LoginPage />
              </PublicOnlyRoute>
            }
          />
          <Route
            path="/register"
            element={
              <PublicOnlyRoute>
                <ViewerRegisterPage />
              </PublicOnlyRoute>
            }
          />

          {/* ── Viewer portal — own layout, no admin sidebar ──────────── */}
          <Route
            path="/viewer"
            element={
              <ProtectedRoute roles={["viewer"]}>
                <ViewerDashboardPage />
              </ProtectedRoute>
            }
          />

          {/* ── Admin shell — all routes require role="admin" ──────────── */}
          <Route
            element={
              <ProtectedRoute roles={["admin"]}>
                <DashboardLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/dashboard"  element={<DashboardPage />} />
            <Route path="/students"   element={<StudentsPage />} />
            <Route path="/attendance" element={<AttendancePage />} />
            <Route path="/analytics"  element={<AnalyticsPage />} />
            <Route path="/export"     element={<ExportPage />} />
            <Route path="/users"      element={<UsersPage />} />
          </Route>

          {/* ── Fallback ───────────────────────────────────────────────── */}
          {/* Unauthenticated → /login (handled by ProtectedRoute).
              Authenticated admin  → /dashboard.
              Authenticated viewer → /viewer (handled by ProtectedRoute).
              The Navigate here covers direct hits to "/" only. */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
