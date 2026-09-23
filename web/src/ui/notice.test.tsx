import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import NoticeHost from "./NoticeHost";
import { clearNotices, getNotices, notify } from "./notice";

/** UX-02: muvaffaqiyat/ma'lumot — xatodan alohida kanal (role=status), xato — role=alert. */
describe("bildirishnomalar", () => {
  afterEach(() => { cleanup(); clearNotices(); vi.useRealTimers(); });

  it("muvaffaqiyat — status, avtomatik yopiladi; xato — alert, qo'lda yopiladi", () => {
    vi.useFakeTimers();
    render(<NoticeHost />);
    act(() => { notify("Ish buyrug'i #5 yaratildi"); });
    const ok = screen.getByRole("status");
    expect(ok).toHaveTextContent("Ish buyrug'i #5 yaratildi");
    expect(ok.dataset.kind).toBe("success");
    act(() => { notify("Server javob bermadi", "error"); });
    expect(screen.getByRole("alert")).toHaveTextContent("Server javob bermadi");
    act(() => { vi.advanceTimersByTime(6500); });
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("alert")).toBeTruthy(); // xato o'z-o'zidan yo'qolmaydi
    act(() => { screen.getByRole("button", { name: "Yopish" }).click(); });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("bir xil matn takrorlanmaydi, eng ko'pi 4 ta", () => {
    notify("A"); notify("A");
    expect(getNotices()).toHaveLength(1);
    for (const x of ["B", "C", "D", "E"]) notify(x);
    expect(getNotices().map((n) => n.text)).toEqual(["B", "C", "D", "E"]);
  });
});
