import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { authService } from "../services/authService";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null);
  const [loading, setLoading] = useState(true); // true while bootstrapping

  // Bootstrap: hydrate user from stored token on first mount.
  // If the stored token is expired or invalid the server returns 401;
  // we clear the token so the login page is shown rather than retrying.
  useEffect(() => {
    (async () => {
      if (authService.isAuthenticated()) {
        try {
          const me = await authService.getMe();
          setUser(me);
        } catch {
          // 401 = token expired/invalid; any other error also clears state
          // to avoid a broken session.
          authService.logout();
          setUser(null);
        }
      }
      setLoading(false);
    })();
  }, []);

  const login = useCallback(async (username, password) => {
    // authService.login() stores the token before returning so that the
    // subsequent getMe() call has it available immediately.
    await authService.login(username, password);
    const me = await authService.getMe();
    setUser(me);
    return me; // caller uses me.role to decide redirect target
  }, []);

  const logout = useCallback(() => {
    authService.logout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        logout,
        isAuthenticated: !!user,
        isAdmin:  user?.role === "admin",
        isViewer: user?.role === "viewer",
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
