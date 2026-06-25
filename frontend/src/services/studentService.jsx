import api from "./api";

/**
 * studentService
 * ──────────────
 * Changes from previous version
 * ──────────────────────────────
 * • getMyStudentRecord() — NEW. Calls GET /students/me.
 *   Used by the viewer dashboard to fetch the viewer's own Student record
 *   (profile, department, student_code) without needing to know their
 *   numeric student ID.
 *
 * All other methods are unchanged.
 */
export const studentService = {
  /**
   * Return the Student record belonging to the currently authenticated viewer.
   * Matches username → student_code on the backend.
   *
   * Used by: ViewerDashboardPage — profile panel.
   */
  async getMyStudentRecord() {
    const { data } = await api.get("/students/me");
    return data; // StudentRead
  },

  /** List active students with optional filters (admin only) */
  async list({ department, page = 1, pageSize = 50 } = {}) {
    const params = { page, page_size: pageSize };
    if (department) params.department = department;
    const { data } = await api.get("/students", { params });
    return data; // { total, page, page_size, items }
  },

  /** Get a single student with embedding metadata (admin only) */
  async get(studentId) {
    const { data } = await api.get(`/students/${studentId}`);
    return data;
  },

  /**
   * Register a new student (admin only).
   * Creates ONLY a student record — does NOT create a user account.
   */
  async create(payload) {
    // payload: { name, student_code, email?, department? }
    const { data } = await api.post("/students", payload);
    return data;
  },

  /** Partially update a student (admin only) */
  async update(studentId, payload) {
    const { data } = await api.put(`/students/${studentId}`, payload);
    return data;
  },

  /** Permanently delete a student and their face embeddings (admin only) */
  async delete(studentId) {
    await api.delete(`/students/${studentId}`);
  },

  /** Upload a single face image for a student */
  async captureFace(studentId, file) {
    const form = new FormData();
    form.append("image", file);
    const { data } = await api.post(`/students/${studentId}/capture`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data; // FaceEmbeddingRead
  },

  /** Upload multiple face images at once */
  async captureFaceBatch(studentId, files) {
    const form = new FormData();
    files.forEach((f) => form.append("images", f));
    const { data } = await api.post(`/students/${studentId}/capture/batch`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data; // list[FaceEmbeddingRead]
  },

  /**
   * Send a single webcam frame (Blob/File) to the backend for face detection
   * and embedding generation.
   *
   * Called by WebcamCaptureModal (admin flow) and ViewerRegisterPage Step 2
   * (self-registration flow) in a polling loop until sample_count reaches 30.
   *
   * Returns:
   *   { face_detected: bool, saved: bool, sample_count: int, message: string }
   */
  async captureWebcamFrame(studentId, blob) {
    const form = new FormData();
    form.append("image", blob, "frame.jpg");
    const { data } = await api.post(`/students/${studentId}/capture/frame`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data; // FrameCaptureResponse
  },

  /** List embedding metadata for a student */
  async listEmbeddings(studentId) {
    const { data } = await api.get(`/students/${studentId}/embeddings`);
    return data;
  },

  /** Delete one embedding */
  async deleteEmbedding(studentId, embeddingId) {
    await api.delete(`/students/${studentId}/embeddings/${embeddingId}`);
  },

  /** Clear all embeddings (admin only) */
  async clearEmbeddings(studentId) {
    await api.delete(`/students/${studentId}/embeddings`);
  },
};
