// Vitest: React act() muhiti (hook/komponent testlari uchun)
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
// RTL avtomatik tozalash faqat `globals: true` da — aniq ulaymiz (testlar orasida DOM qolmasin)
afterEach(() => cleanup());
