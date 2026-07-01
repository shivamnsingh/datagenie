const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const API_BASE_URL = `${API_URL.replace(/\/$/, "")}/api`;