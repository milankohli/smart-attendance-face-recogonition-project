import api from "./api";

/**
 * authService
 * ───────────
 * Changes from previous version
 * ──────────────────────────────
 * • registerViewer()    — NEW. Calls POST /auth/register (public).
 *                         Returns { access_token, refresh_token, user_id, student_id }.
 * • loginWithTokens()   — NEW. Stores tokens directly without a network call.
 *                         Used after viewer self-registration to persist the
 *                         auto-issued tokens so subsequent API calls are auth'd.
 * • changePassword()    — NEW. Calls POST /auth/change-password.
 *                         Used by the viewer dashboard "Change Password" UI.
 * • login()             — unchanged.
 * • getMe()             — unchanged.
 * • logout()            — unchanged.
 * • isAuthenticated()   — unchanged.
 */
export const authService = {
  /**
   * Standard username + password login.
   * Stores tokens and returns the decoded user object from /auth/me.
   */
  async login(username, password) {
    const { data } = await api.post("/auth/login", { username, password });
    localStorage.setItem("access_token",  data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    return data;
  },

  /**
   * Public viewer self-registration (Step 1).
   *
   * Calls POST /auth/register with the viewer's details.
   * The backend always creates role=VIEWER regardless of payload.
   *
   * On success the backend returns tokens + IDs. This method stores the
   * tokens immediately so that subsequent face-capture API calls
   * (POST /students/{id}/capture/frame) are authenticated.
   *
   * @param {{ full_name, student_code, email, username, password, confirm_password, department? }} payload
   * @returns {{ access_token, refresh_token, user_id, student_id }}
   */
  async registerViewer(payload) {
    const { data } = await api.post("/auth/register", payload);
    localStorage.setItem("access_token",  data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    return data;
  },

  /**
   * Store tokens received from a registration response directly.
   * Useful when calling registerViewer() through useAuth so the hook's
   * state is updated at the same time.
   */
  loginWithTokens(accessToken, refreshToken) {
    localStorage.setItem("access_token",  accessToken);
    localStorage.setItem("refresh_token", refreshToken);
  },

  /**
   * Fetch the current authenticated user's profile.
   */
  async getMe() {
    const { data } = await api.get("/auth/me");
    return data;
  },

  /**
   * Change the currently authenticated user's password.
   *
   * @param {{ current_password, new_password, confirm_new_password }} payload
   */
  async changePassword(payload) {
    await api.post("/auth/change-password", payload);
  },

  /**
   * Clear stored tokens (logout).
   */
  logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  },

  /**
   * Returns true if an access token is present in storage.
   * Does not validate the token's expiry; that is handled by the API
   * interceptor via the refresh flow.
   */
  isAuthenticated() {
    return Boolean(localStorage.getItem("access_token"));
  },
};
