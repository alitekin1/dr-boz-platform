export const getApiUrl = () => {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL;
  if (typeof window !== "undefined") {
    return `/api`;
  }
  return "http://localhost:7000/api";
};

export const API_URL = getApiUrl();
export const ADMIN_PASSWORD_KEY = "jgpti_admin_password";
