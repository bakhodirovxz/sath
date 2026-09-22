import { create } from "zustand";
import { api, refreshSession, setToken, setUnauthorizedHandler, type User } from "../api/client";

interface AuthState {
  user: User | null;
  ready: boolean;
  init: () => Promise<void>;
  login: (username: string, password: string, otp?: string) => Promise<void>;
  /** Profil o'zgargach (MFA, parol) foydalanuvchini qayta o'qish */
  refresh: () => Promise<void>;
  logout: () => void;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  ready: false,
  async init() {
    setUnauthorizedHandler(() => set({ user: null }));
    // Sahifa yuklanganda: HttpOnly refresh cookie bo'lsa yangi access token (L2); bo'lmasa login sahifasi
    if (!(await refreshSession())) return set({ ready: true });
    try {
      set({ user: await api.me(), ready: true });
    } catch {
      setToken(null);
      set({ user: null, ready: true });
    }
  },
  async login(username, password, otp) {
    await api.login(username, password, otp);
    set({ user: await api.me() });
  },
  async refresh() {
    set({ user: await api.me() });
  },
  logout() {
    void api.logout().catch(() => undefined); // sessiya serverda bekor (refresh cookie o'chadi)
    setToken(null);
    set({ user: null });
  },
}));
