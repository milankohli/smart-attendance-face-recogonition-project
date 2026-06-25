import api from "./api";

export const analyticsService = {
  /** Top-level dashboard stat cards */
  async getSummary() {
    const { data } = await api.get("/analytics/summary");
    return data; // AnalyticsSummary
  },

  /**
   * Per-day attendance counts for a date range.
   * @param {string} startDate  YYYY-MM-DD
   * @param {string} endDate    YYYY-MM-DD
   */
  async getDaily(startDate, endDate) {
    const params = {};
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    const { data } = await api.get("/analytics/daily", { params });
    return data; // { start_date, end_date, points: DailyAttendancePoint[] }
  },

  /**
   * Per-student attendance frequency over an optional date range.
   * @param {object} opts  { startDate?, endDate?, limit? }
   */
  async getByStudent({ startDate, endDate, limit = 50 } = {}) {
    const params = { limit };
    if (startDate) params.start_date = startDate;
    if (endDate) params.end_date = endDate;
    const { data } = await api.get("/analytics/by-student", { params });
    return data; // { items: StudentAttendanceFrequency[] }
  },

  /**
   * Monthly attendance totals.
   * @param {number|null} year  Optional year filter
   */
  async getMonthly(year) {
    const params = {};
    if (year) params.year = year;
    const { data } = await api.get("/analytics/monthly", { params });
    return data; // { points: MonthlyAttendancePoint[] }
  },
};
