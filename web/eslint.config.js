// ESLint 9 (flat config): TypeScript + React hooks + jsx-a11y qoidalari (F10, UX-10). CI da `npm run lint`.
import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**", "tools/**", "playwright-report/**", "test-results/**", "public/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrors: "none" }],
      "@typescript-eslint/no-explicit-any": "warn",
      "no-empty": ["error", { allowEmptyCatch: true }],
      "prefer-const": "error",
    },
  },
  // UX-10: klaviatura va ekran o'quvchi — bosiladigan elementlar tugma/havola, dialoglar modal (0 ogohlantirish)
  { files: ["src/**/*.tsx"], ...jsxA11y.flatConfigs.recommended },
  {
    files: ["src/**/*.tsx"],
    rules: {
      // 3D ko'rinish (role=application) o'z klaviatura boshqaruviga ega — Tab bilan yetib borilishi shart
      "jsx-a11y/no-noninteractive-tabindex": ["error", { tags: [], roles: ["tabpanel", "application"], allowExpressionValues: true }],
      // Maxsus maydon komponentlari (ichida <input>) — label ular bilan bog'langan hisoblanadi
      "jsx-a11y/label-has-associated-control": ["error", { controlComponents: ["DateField", "DateTimeField"], depth: 3 }],
    },
  },
  { files: ["**/*.test.{ts,tsx}", "e2e/**"], rules: { "@typescript-eslint/no-non-null-assertion": "off" } },
);
