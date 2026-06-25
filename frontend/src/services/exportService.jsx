import api from "./api";

export const exportService = {
  /**
   * Trigger a file download (CSV or JSON).
   * Uses a direct anchor-click approach so the browser saves the file.
   *
   * @param {object} opts
   * @param {"csv"|"json"} opts.format
   * @param {number|null}  opts.studentId
   * @param {string|null}  opts.startDate   YYYY-MM-DD
   * @param {string|null}  opts.endDate     YYYY-MM-DD
   * @param {string|null}  opts.status
   */
  async download({ format = "csv", studentId, startDate, endDate, status } = {}) {
    const params = { format };
    if (studentId) params.student_id = studentId;
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    if (status) params.status = status;

    // Fetch as blob so auth headers are included (avoids window.open pitfalls)
    const response = await api.get("/export/download", {
      params,
      responseType: "blob",
    });

    const contentDisposition = response.headers["content-disposition"] ?? "";
    const match = contentDisposition.match(/filename=([^;]+)/);
    const filename = match ? match[1].trim() : `attendance_export.${format}`;

    const url = URL.createObjectURL(response.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  /**
   * Stream CSV directly (no disk write on the server).
   * Returns the raw CSV text for preview or inline display.
   */
  async streamCSV({ studentId, startDate, endDate, status } = {}) {
    const params = {};
    if (studentId) params.student_id = studentId;
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    if (status) params.status = status;

    const response = await api.get("/export/stream/csv", {
      params,
      responseType: "text",
    });
    return response.data; // raw CSV string
  },
};
