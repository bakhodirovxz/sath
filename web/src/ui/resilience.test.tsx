import { act } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ErrorBoundary from "./ErrorBoundary";
import { usePolling } from "../hooks/usePolling";
import { useOnline } from "../hooks/useOnline";

afterEach(cleanup);
/** F12: xatolar chegarasi, polling pauzasi/orqaga chekinish, offlayn holat. */

function Boom(): JSX.Element {
  throw new Error("panel yiqildi");
}

describe("ErrorBoundary (F12)", () => {
  const origError = console.error;
  beforeEach(() => { console.error = () => undefined; });
  afterEach(() => { console.error = origError; });

  it("bitta panel yiqilsa qo'shnisi ishlayveradi, xato paneli nomi bilan ko'rinadi", () => {
    render(
      <div>
        <ErrorBoundary name="A"><Boom /></ErrorBoundary>
        <ErrorBoundary name="B"><div data-testid="ok">sog'lom</div></ErrorBoundary>
      </div>,
    );
    expect(screen.getByTestId("ok")).toHaveTextContent("sog'lom");
    const err = screen.getByTestId("panel-error");
    expect(err).toHaveTextContent("A");
    expect(err).toHaveTextContent("panel yiqildi");
  });

  it("«Qayta urinish» bolalarni qayta chizadi", () => {
    let fail = true;
    function Maybe() { if (fail) throw new Error("x"); return <span data-testid="fixed">tuzaldi</span>; }
    render(<ErrorBoundary name="P"><Maybe /></ErrorBoundary>);
    expect(screen.getByTestId("panel-error")).toBeInTheDocument();
    fail = false;
    act(() => { screen.getByRole("button").click(); });
    expect(screen.getByTestId("fixed")).toBeInTheDocument();
  });
});

describe("usePolling (F12)", () => {
  let hidden = false;
  beforeEach(() => {
    vi.useFakeTimers();
    hidden = false;
    Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  });
  afterEach(() => { vi.useRealTimers(); });

  function Probe({ fn, key = "" }: { fn: () => Promise<unknown>; key?: string }) {
    const { error } = usePolling(fn, 1000, key);
    return <i data-testid="err">{error ?? ""}</i>;
  }

  it("intervalda chaqiradi; yashirin tabda chaqirmaydi; ko'rinish qaytganda darhol yangilaydi", async () => {
    const fn = vi.fn(() => Promise.resolve());
    render(<Probe fn={fn} />);
    await act(async () => { await Promise.resolve(); });
    expect(fn).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(fn).toHaveBeenCalledTimes(2);
    hidden = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(fn).toHaveBeenCalledTimes(2);
    hidden = false;
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); await Promise.resolve(); });
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it("xatoda eksponensial orqaga chekinadi (2×, 4×, ≤8×) va xatoni qaytaradi; muvaffaqiyatda tiklanadi", async () => {
    let ok = false;
    const fn = vi.fn(() => (ok ? Promise.resolve() : Promise.reject(new Error("tarmoq"))));
    render(<Probe fn={fn} />);
    await act(async () => { await Promise.resolve(); });
    expect(fn).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("err")).toHaveTextContent("tarmoq");
    await act(async () => { await vi.advanceTimersByTimeAsync(1999); });
    expect(fn).toHaveBeenCalledTimes(1); // 2× kutadi
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(fn).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(3999); });
    expect(fn).toHaveBeenCalledTimes(2); // 4×
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(fn).toHaveBeenCalledTimes(3);
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
    expect(fn).toHaveBeenCalledTimes(4); // 8× chegara
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
    expect(fn).toHaveBeenCalledTimes(5); // 16× emas, 8× da qoladi
    ok = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });
    expect(fn).toHaveBeenCalledTimes(6);
    expect(screen.getByTestId("err")).toHaveTextContent("");
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(fn).toHaveBeenCalledTimes(7); // interval tiklandi
  });
});

describe("useOnline (F12)", () => {
  it("navigator.onLine dan boshlanadi va online/offline hodisalariga ergashadi", () => {
    function P() { return <b data-testid="on">{useOnline() ? "on" : "off"}</b>; }
    Object.defineProperty(navigator, "onLine", { configurable: true, get: () => true });
    render(<P />);
    expect(screen.getByTestId("on")).toHaveTextContent("on");
    act(() => { window.dispatchEvent(new Event("offline")); });
    expect(screen.getByTestId("on")).toHaveTextContent("off");
    act(() => { window.dispatchEvent(new Event("online")); });
    expect(screen.getByTestId("on")).toHaveTextContent("on");
  });
});
