import { useCallback, useEffect, useRef, useState } from "react";
import api from "../services/api";

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

/** Two roles only: admin (full access) and viewer (registered person). */
const ROLES = ["admin", "viewer"];

// ─────────────────────────────────────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────────────────────────────────────

function useDebounce(value, delay = 400) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// ─────────────────────────────────────────────────────────────────────────────
// Toast
// ─────────────────────────────────────────────────────────────────────────────

function Toast({ message, type = "success", onDismiss }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 4000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  const styles =
    type === "success"
      ? "border-emerald-800/40 bg-emerald-950/60 text-emerald-300"
      : "border-rose-800/40 bg-rose-950/60 text-rose-300";

  return (
    <div
      className={`fixed bottom-6 right-6 z-[60] flex max-w-sm items-start gap-3 rounded-2xl border px-5 py-4 shadow-2xl backdrop-blur-sm ${styles}`}
    >
      {type === "success" ? (
        <svg className="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
        </svg>
      ) : (
        <svg className="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
        </svg>
      )}
      <p className="text-sm font-medium leading-snug">{message}</p>
      <button
        onClick={onDismiss}
        className="ml-auto shrink-0 opacity-60 hover:opacity-100"
        aria-label="Dismiss"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Modal shell
// ─────────────────────────────────────────────────────────────────────────────

function Modal({ children, onClose, maxWidth = "max-w-lg" }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className={`w-full ${maxWidth} rounded-2xl border border-slate-800 bg-slate-900 shadow-2xl`}>
        {children}
      </div>
    </div>
  );
}

function ModalHeader({ title, subtitle, onClose }) {
  return (
    <div className="flex items-start justify-between border-b border-slate-800 px-6 py-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      <button
        onClick={onClose}
        className="ml-4 mt-0.5 rounded-lg p-1 text-slate-500 transition hover:bg-slate-800 hover:text-slate-300"
        aria-label="Close"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Role badge — admin (indigo) and viewer (slate)
// ─────────────────────────────────────────────────────────────────────────────

function RoleBadge({ role }) {
  const map = {
    admin:  "bg-indigo-500/15 text-indigo-400 ring-indigo-500/30",
    viewer: "bg-slate-700 text-slate-400 ring-slate-600/30",
  };
  const cls = map[role?.toLowerCase()] ?? "bg-slate-700 text-slate-400 ring-slate-600/30";
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ring-1 ${cls}`}>
      {role ?? "—"}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Status badge
// ─────────────────────────────────────────────────────────────────────────────

function StatusBadge({ active }) {
  return active ? (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-semibold text-emerald-400 ring-1 ring-emerald-500/30">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
      Active
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-700 px-2.5 py-0.5 text-xs font-semibold text-slate-400 ring-1 ring-slate-600/30">
      <span className="h-1.5 w-1.5 rounded-full bg-slate-500" />
      Inactive
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Avatar initials
// ─────────────────────────────────────────────────────────────────────────────

function Avatar({ username }) {
  const colors = [
    "bg-indigo-600/30 text-indigo-300",
    "bg-sky-600/30 text-sky-300",
    "bg-violet-600/30 text-violet-300",
    "bg-rose-600/30 text-rose-300",
    "bg-amber-600/30 text-amber-300",
    "bg-teal-600/30 text-teal-300",
  ];
  const idx = (username?.charCodeAt(0) ?? 0) % colors.length;
  return (
    <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${colors[idx]}`}>
      {username?.[0]?.toUpperCase() ?? "?"}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Edit User Modal
// ─────────────────────────────────────────────────────────────────────────────

function EditUserModal({ user, onClose, onSuccess }) {
  const [form, setForm] = useState({
    username:  user.username  ?? "",
    email:     user.email     ?? "",
    role:      user.role      ?? "viewer",
    is_active: user.is_active ?? true,
    password:  "",
  });
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const set = (key) => (e) => {
    const val = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setForm((prev) => ({ ...prev, [key]: val }));
  };

  const handleSubmit = async () => {
    if (!form.username.trim()) { setError("Username is required."); return; }
    setLoading(true);
    setError("");
    try {
      const payload = {
        username:  form.username.trim(),
        email:     form.email.trim() || null,
        role:      form.role,
        is_active: form.is_active,
      };
      if (form.password) payload.password = form.password;
      await api.patch(`/users/${user.id}`, payload);
      onSuccess(`${form.username} updated successfully.`);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : "Could not update user. Please try again."
      );
    } finally {
      setLoading(false);
    }
  };

  const inputCls =
    "block w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30";

  return (
    <Modal onClose={onClose}>
      <ModalHeader
        title="Edit User"
        subtitle={`ID ${user.id} · ${user.username}`}
        onClose={onClose}
      />
      <div className="space-y-4 p-6">
        {error && (
          <div className="rounded-xl border border-rose-800/40 bg-rose-950/40 px-4 py-3 text-sm text-rose-400">
            {error}
          </div>
        )}

        {/* Username */}
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-slate-400">Username</label>
          <input
            type="text"
            value={form.username}
            onChange={set("username")}
            placeholder="username"
            className={inputCls}
          />
        </div>

        {/* Email */}
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-slate-400">Email</label>
          <input
            type="email"
            value={form.email}
            onChange={set("email")}
            placeholder="user@example.com"
            className={inputCls}
          />
        </div>

        {/* Role — admin or viewer only */}
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-slate-400">Role</label>
          <select value={form.role} onChange={set("role")} className={inputCls}>
            {ROLES.map((r) => (
              <option key={r} value={r} className="capitalize">
                {r.charAt(0).toUpperCase() + r.slice(1)}
              </option>
            ))}
          </select>
        </div>

        {/* New password (optional) */}
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-slate-400">
            New Password{" "}
            <span className="font-normal text-slate-600">(leave blank to keep current)</span>
          </label>
          <input
            type="password"
            value={form.password}
            onChange={set("password")}
            placeholder="••••••••"
            autoComplete="new-password"
            className={inputCls}
          />
        </div>

        {/* Active toggle */}
        <div className="flex items-center justify-between rounded-xl border border-slate-700 bg-slate-800/50 px-4 py-3">
          <div>
            <p className="text-sm font-medium text-slate-200">Active</p>
            <p className="text-xs text-slate-500">Inactive users cannot sign in.</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={form.is_active}
            onClick={() => setForm((p) => ({ ...p, is_active: !p.is_active }))}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none ${
              form.is_active ? "bg-indigo-600" : "bg-slate-700"
            }`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-sm transition-transform ${
                form.is_active ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>

        {/* Actions */}
        <div className="flex gap-3 pt-1">
          <button
            onClick={onClose}
            className="flex-1 rounded-xl py-2.5 text-sm text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 hover:text-slate-200"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-indigo-600 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-60"
          >
            {loading && (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            )}
            Save Changes
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Delete confirm modal
// ─────────────────────────────────────────────────────────────────────────────

function DeleteModal({ user, onClose, onConfirm, loading }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-rose-500/15">
          <svg className="h-5 w-5 text-rose-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
        </div>
        <h2 className="text-sm font-semibold text-slate-100">Delete User</h2>
        <p className="mt-2 text-sm text-slate-400">
          Permanently delete{" "}
          <span className="font-medium text-slate-200">{user.username}</span>? This
          cannot be undone.
        </p>
        <div className="mt-5 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 rounded-xl py-2.5 text-sm text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-rose-600 py-2.5 text-sm font-semibold text-white transition hover:bg-rose-500 disabled:opacity-60"
          >
            {loading && (
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
            )}
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Create User Modal
// ─────────────────────────────────────────────────────────────────────────────

function CreateUserModal({ onClose, onSuccess }) {
  const [form, setForm] = useState({
    username: "",
    email:    "",
    role:     "viewer",
    password: "",
  });
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  const set = (key) => (e) => setForm((p) => ({ ...p, [key]: e.target.value }));

  const handleSubmit = async () => {
    if (!form.username.trim()) { setError("Username is required."); return; }
    if (!form.password)        { setError("Password is required."); return; }
    setLoading(true);
    setError("");
    try {
      await api.post("/users", {
        username: form.username.trim(),
        email:    form.email.trim() || null,
        role:     form.role,
        password: form.password,
      });
      onSuccess(`User "${form.username}" created successfully.`);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : "Could not create user. The username may already be taken."
      );
    } finally {
      setLoading(false);
    }
  };

  const inputCls =
    "block w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30";

  return (
    <Modal onClose={onClose}>
      <ModalHeader title="Create User" subtitle="Add a new system user account." onClose={onClose} />
      <div className="space-y-4 p-6">
        {error && (
          <div className="rounded-xl border border-rose-800/40 bg-rose-950/40 px-4 py-3 text-sm text-rose-400">
            {error}
          </div>
        )}

        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-slate-400">
            Username <span className="text-rose-400">*</span>
          </label>
          <input type="text" value={form.username} onChange={set("username")} placeholder="johndoe" className={inputCls} />
        </div>

        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-slate-400">Email</label>
          <input type="email" value={form.email} onChange={set("email")} placeholder="john@example.com" className={inputCls} />
        </div>

        {/* Role — admin or viewer only */}
        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-slate-400">Role</label>
          <select value={form.role} onChange={set("role")} className={inputCls}>
            {ROLES.map((r) => (
              <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <label className="block text-xs font-medium text-slate-400">
            Password <span className="text-rose-400">*</span>
          </label>
          <input type="password" value={form.password} onChange={set("password")} placeholder="••••••••" autoComplete="new-password" className={inputCls} />
        </div>

        <div className="flex gap-3 pt-1">
          <button onClick={onClose} className="flex-1 rounded-xl py-2.5 text-sm text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 hover:text-slate-200">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-indigo-600 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-60"
          >
            {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />}
            Create User
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Users table
// ─────────────────────────────────────────────────────────────────────────────

const COL_HEADERS = ["User", "Email", "Role", "Status", "Created", "Actions"];

function UsersTable({ users, loading, onEdit, onDelete }) {
  if (loading) {
    return (
      <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-lg">
        <div className="space-y-3 p-6">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-800" />
          ))}
        </div>
      </div>
    );
  }

  if (users.length === 0) {
    return (
      <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-lg">
        <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl border border-slate-800 bg-slate-900">
            <svg className="h-7 w-7 text-slate-600" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
            </svg>
          </div>
          <p className="text-sm font-medium text-slate-400">No users found</p>
          <p className="text-xs text-slate-600">Try adjusting your search or filters.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900 shadow-lg">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-800">
              {COL_HEADERS.map((h) => (
                <th
                  key={h}
                  className="px-5 py-3.5 text-left text-xs font-semibold uppercase tracking-wider text-slate-500"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {users.map((u) => (
              <tr key={u.id} className="group transition-colors hover:bg-slate-800/50">
                {/* User (avatar + username) */}
                <td className="px-5 py-3.5">
                  <div className="flex items-center gap-3">
                    <Avatar username={u.username} />
                    <div>
                      <p className="font-medium text-slate-200">{u.username}</p>
                      <p className="text-xs text-slate-600">ID {u.id}</p>
                    </div>
                  </div>
                </td>

                {/* Email */}
                <td className="px-5 py-3.5 text-slate-400">
                  {u.email ?? <span className="text-slate-600">—</span>}
                </td>

                {/* Role */}
                <td className="px-5 py-3.5">
                  <RoleBadge role={u.role} />
                </td>

                {/* Status */}
                <td className="px-5 py-3.5">
                  <StatusBadge active={u.is_active ?? true} />
                </td>

                {/* Created */}
                <td className="px-5 py-3.5 text-slate-400">
                  {u.created_at
                    ? new Date(u.created_at).toLocaleDateString("en-US", {
                        year:  "numeric",
                        month: "short",
                        day:   "numeric",
                      })
                    : <span className="text-slate-600">—</span>}
                </td>

                {/* Actions */}
                <td className="px-5 py-3.5">
                  <div className="flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      onClick={() => onEdit(u)}
                      className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-300 ring-1 ring-slate-700 transition hover:bg-slate-700 hover:text-white"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125" />
                      </svg>
                      Edit
                    </button>
                    <button
                      onClick={() => onDelete(u)}
                      className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-rose-400 ring-1 ring-rose-900/50 transition hover:bg-rose-600/20 hover:text-rose-300"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                      </svg>
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

const PAGE_SIZE = 20;

export default function UsersPage() {
  const [users,   setUsers]   = useState([]);
  const [total,   setTotal]   = useState(0);
  const [page,    setPage]    = useState(1);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  // Filters
  const [query,      setQuery]      = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const debouncedQuery = useDebounce(query, 350);

  // Modals
  const [editTarget,   setEditTarget]   = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting,     setDeleting]     = useState(false);
  const [createOpen,   setCreateOpen]   = useState(false);

  // Toast
  const [toast, setToast] = useState(null);
  const showToast = useCallback((message, type = "success") => {
    setToast({ message, type });
  }, []);

  // ── Fetch ─────────────────────────────────────────────────────────────────

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = { page, page_size: PAGE_SIZE };
      if (debouncedQuery) params.search = debouncedQuery;
      if (roleFilter)     params.role   = roleFilter;
      const { data } = await api.get("/users", { params });
      if (Array.isArray(data)) {
        setUsers(data);
        setTotal(data.length);
      } else {
        setUsers(data.items ?? data);
        setTotal(data.total ?? (data.items ?? data).length);
      }
    } catch {
      setError("Failed to load users. Check that you have admin privileges.");
    } finally {
      setLoading(false);
    }
  }, [page, debouncedQuery, roleFilter]);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  // Reset to page 1 when filters change
  useEffect(() => { setPage(1); }, [debouncedQuery, roleFilter]);

  // ── Handlers ─────────────────────────────────────────────────────────────

  const handleEditSuccess = useCallback((msg) => {
    setEditTarget(null);
    fetchUsers();
    showToast(msg);
  }, [fetchUsers, showToast]);

  const handleCreateSuccess = useCallback((msg) => {
    setCreateOpen(false);
    fetchUsers();
    showToast(msg);
  }, [fetchUsers, showToast]);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/users/${deleteTarget.id}`);
      const name = deleteTarget.username;
      setDeleteTarget(null);
      fetchUsers();
      showToast(`User "${name}" deleted.`);
    } catch {
      setDeleteTarget(null);
      showToast("Failed to delete user.", "error");
    } finally {
      setDeleting(false);
    }
  };

  // Client-side filter (instant, no extra round-trip)
  const displayed = users.filter((u) => {
    const q = debouncedQuery.toLowerCase();
    const matchesQuery =
      !q ||
      u.username?.toLowerCase().includes(q) ||
      u.email?.toLowerCase().includes(q);
    const matchesRole = !roleFilter || u.role === roleFilter;
    return matchesQuery && matchesRole;
  });

  const totalPages = Math.ceil(total / PAGE_SIZE);

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">

      {/* Modals */}
      {createOpen && (
        <CreateUserModal onClose={() => setCreateOpen(false)} onSuccess={handleCreateSuccess} />
      )}
      {editTarget && (
        <EditUserModal user={editTarget} onClose={() => setEditTarget(null)} onSuccess={handleEditSuccess} />
      )}
      {deleteTarget && (
        <DeleteModal
          user={deleteTarget}
          onClose={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
          loading={deleting}
        />
      )}

      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">User Management</h1>
          <p className="mt-1 text-sm text-slate-400">
            {loading ? "Loading…" : `${total.toLocaleString()} user${total !== 1 ? "s" : ""}`}
          </p>
        </div>
        <button
          onClick={() => setCreateOpen(true)}
          className="flex items-center gap-2 self-start rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-indigo-900/40 transition hover:bg-indigo-500 sm:self-auto"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Add User
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-rose-800/50 bg-rose-950/50 px-4 py-3 text-sm text-rose-400">
          <svg className="mt-0.5 h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row">
        {/* Search */}
        <div className="relative w-full sm:max-w-xs">
          <svg className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 15.803a7.5 7.5 0 0010.607 0z" />
          </svg>
          <input
            type="search"
            placeholder="Search by username or email…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-800 py-2.5 pl-10 pr-4 text-sm text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30"
          />
        </div>

        {/* Role filter — admin | viewer only */}
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value)}
          className="w-full rounded-xl border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30 sm:max-w-44"
        >
          <option value="">All roles</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
          ))}
        </select>

        {/* Clear */}
        {(query || roleFilter) && (
          <button
            onClick={() => { setQuery(""); setRoleFilter(""); }}
            className="self-start rounded-xl px-4 py-2.5 text-sm text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 hover:text-slate-200 sm:self-auto"
          >
            Clear
          </button>
        )}
      </div>

      {/* Table */}
      <UsersTable
        users={displayed}
        loading={loading}
        onEdit={setEditTarget}
        onDelete={setDeleteTarget}
      />

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-500">
            Page {page} of {totalPages} · {total.toLocaleString()} total
          </p>
          <div className="flex items-center gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              ← Prev
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 ring-1 ring-slate-700 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <Toast message={toast.message} type={toast.type} onDismiss={() => setToast(null)} />
      )}
    </div>
  );
}
