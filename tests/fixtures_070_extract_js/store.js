export const useAuthStore = create((set) => ({ user: null }));
export const DEMO_MODE = true;
export const authUtils = {
  getToken() {
    return 1;
  },
  setToken: (t) => t,
  storageKey: "t",
};
export const useAuth = () => useAuthStore();
export var legacyVar = 42;
export function formatDate() {}
const toast = () => {};
export { toast as showToast };
