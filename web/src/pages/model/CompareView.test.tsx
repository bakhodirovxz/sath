import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Diff, Version } from "../../api/client";

/** UX-12: versiyalarni yonma-yon / slayder bilan taqqoslash — ikki viewport, sinxron kamera, farq ranglari. */
const made: FakeViewer[] = [];
class FakeViewer {
  listeners: (() => void)[] = [];
  init = vi.fn(async () => undefined);
  loadFragments = vi.fn(async () => undefined);
  loadIfc = vi.fn(async () => undefined);
  applyDiff = vi.fn(async () => undefined);
  fitAll = vi.fn(async () => undefined);
  lookAtFrom = vi.fn();
  dispose = vi.fn();
  onViewChange(cb: () => void) { this.listeners.push(cb); return () => { this.listeners = this.listeners.filter((x) => x !== cb); }; }
  constructor() { made.push(this); }
}
vi.mock("../../viewer/Viewer", () => ({ Viewer: FakeViewer }));
vi.mock("../../api/client", async (orig) => ({ ...(await orig<typeof import("../../api/client")>()), api: { versionFragments: vi.fn(async () => new Uint8Array([1])), versionFile: vi.fn() } }));

const v = (id: number, number: number) => ({ id, number } as Version);
const diff = { from_version_id: 1, to_version_id: 2, added: [], deleted: [], changed: [], summary: { added: 3, changed: 1, deleted: 2 } } as Diff;

afterEach(() => { cleanup(); made.length = 0; });

describe("CompareView", () => {
  it("ikki viewport, farq ikkala tomonda, kamera sinxron, slayder, yopilganda tozalanadi", async () => {
    const { default: CompareView } = await import("./CompareView");
    const main = { tag: "main" };
    (window as unknown as { __gesViewer?: unknown }).__gesViewer = main;
    const onClose = vi.fn();
    render(<CompareView modelName="Zal" from={v(1, 1)} to={v(2, 2)} diff={diff} onClose={onClose} />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("+3 qo'shilgan"));
    const [a, b] = made;
    expect(a.loadFragments).toHaveBeenCalledWith(expect.any(Uint8Array), "Zal v1");
    expect(b.loadFragments).toHaveBeenCalledWith(expect.any(Uint8Array), "Zal v2");
    expect(a.applyDiff).toHaveBeenCalledWith(diff);
    expect(b.applyDiff).toHaveBeenCalledWith(diff);
    b.lookAtFrom.mockClear();
    act(() => a.listeners.forEach((f) => f())); // chap kamera harakati → o'ng ergashadi
    expect(b.lookAtFrom).toHaveBeenCalledWith(a);
    expect(a.lookAtFrom).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("cmp-slider-mode"));
    expect(screen.getByTestId("compare-view").dataset.mode).toBe("slider");
    fireEvent.change(screen.getByTestId("cmp-range"), { target: { value: "30" } });
    expect((document.querySelector(".cmp-right") as HTMLElement).style.clipPath).toBe("inset(0 0 0 30%)");
    fireEvent.click(screen.getByRole("button", { name: "Yopish" }));
    expect(onClose).toHaveBeenCalled();
    cleanup();
    expect(a.dispose).toHaveBeenCalled();
    expect(b.dispose).toHaveBeenCalled();
    expect((window as unknown as { __gesViewer?: unknown }).__gesViewer).toBe(main);
  });
});
