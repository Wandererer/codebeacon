import { create } from "zustand";
import type { User } from "./types";

export const useAuthStore = create((set) => ({ user: null, set }));

export const DEMO_MODE = true;
export const MAX_RETRIES = 3;
export const API_BASE = "https://example.test";

export const authUtils = {
  getToken() {
    return localStorage.getItem("t");
  },
  setToken: (t: string) => localStorage.setItem("t", t),
  clear: function () {
    localStorage.clear();
  },
  storageKey: "t",
};

export const useAuth = () => {
  const store = useAuthStore();
  return store;
};

export const helper = function () {
  return 2;
};

export function formatDate(d: Date) {
  return d.toISOString();
}

export const Badge = () => null;

export default function Page() {
  return null;
}

const reducer = (state: number) => state;
const toast = () => {};
const internalOnly = () => {};

export { reducer, toast as showToast };
export { Other } from "./other";
export * from "./star";
