import api from "./api";

export const attendanceService = {
  /** List attendance records with filters and pagination */
  async list({
    studentId,
    date,
    startDate,
    endDate,
    status,
    page = 1,
    pageSize = 50,
  } = {}) {
    const params = { page, page_size: pageSize };
    if (studentId) params.student_id = studentId;
    if (date) params.date = date;
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    if (status) params.status = status;
    const { data } = await api.get("/attendance", { params });
    return data; // { total, page, page_size, items }
  },

  /**
   * List attendance records for the currently authenticated viewer.
   * Calls GET /attendance/me — the backend derives student_id from the JWT.
   * No student_id parameter is sent; the server enforces isolation.
   */
  async listMine({ page = 1, pageSize = 200 } = {}) {
    const { data } = await api.get("/attendance/me", {
      params: { page, page_size: pageSize },
    });
    return data; // { total, page, page_size, items }
  },

  /** Get a single attendance record */
  async get(recordId) {
    const { data } = await api.get(`/attendance/${recordId}`);
    return data;
  },

  /** Manually mark attendance (admin override / backdating) */
  async markManual(payload) {
    // payload: { student_id, date?, time?, similarity_score?, confidence_band?, device_id? }
    const { data } = await api.post("/attendance/mark", payload);
    return data; // { already_marked, record, message }
  },

  /** Delete an attendance record — admin only */
  async delete(recordId) {
    await api.delete(`/attendance/${recordId}`);
  },

  /** Submit a single image frame to the recognition endpoint */
  async identify(file, deviceId) {
    const form = new FormData();
    form.append("image", file);
    const params = {};
    if (deviceId) params.device_id = deviceId;
    const { data } = await api.post("/recognition/identify", form, {
      headers: { "Content-Type": "multipart/form-data" },
      params,
    });
    return data; // RecognitionResponse
  },
};
