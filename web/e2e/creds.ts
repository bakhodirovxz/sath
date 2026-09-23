/** E2E admin hisobi (sof funksiya — vitest da ham tekshiriladi).
 *  - CI da (CI=true) E2E_PASS majburiy — standart parol bilan sinov "o'tib ketmasin".
 *  - Lokal ishlab chiqishda E2E_PASS berilmasa `admin123` (dev server `GES_ADMIN_PASSWORD=admin123`
 *    bilan ishga tushirilgan — README/e2e hujjatlashtirilgan qiymat). */
export function adminCreds(env: Record<string, string | undefined>): { username: string; password: string } {
  const password = env.E2E_PASS;
  if (!password && env.CI) throw new Error("E2E_PASS berilmagan: CI da admin paroli env orqali berilishi shart");
  return { username: env.E2E_USER ?? "admin", password: password ?? "admin123" };
}
