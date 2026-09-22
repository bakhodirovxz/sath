import { describe, expect, it, vi } from "vitest";
import { Annunciator, PATTERNS } from "./annunciator";

function fakeCtx(state: "running" | "suspended" = "running") {
  const ctx = {
    state,
    currentTime: 0,
    destination: {},
    resume: vi.fn(async () => { ctx.state = "running"; }),
    createOscillator: vi.fn(() => ({ type: "", frequency: { value: 0 }, connect: vi.fn(), start: vi.fn(), stop: vi.fn() })),
    createGain: vi.fn(() => ({ gain: { value: 0 }, connect: vi.fn() })),
  };
  return ctx;
}

describe("annunciator (F6)", () => {
  it("20 ta ketma-ket alarmda bitta kontekst, ovoz davom etadi", () => {
    const ctxs: ReturnType<typeof fakeCtx>[] = [];
    const a = new Annunciator({ contextFactory: () => { const c = fakeCtx(); ctxs.push(c); return c; }, setTimer: () => 1, clearTimer: () => undefined });
    for (let i = 0; i < 20; i++) expect(a.beep(i % 2 ? "critical" : "high")).toBe(true);
    expect(ctxs).toHaveLength(1); // yagona AudioContext (Chrome ~6 chegarasi buzilmaydi)
    expect(a.played).toBe(20);
    expect(ctxs[0].createOscillator).toHaveBeenCalledTimes(10 * 3 + 10 * 2);
    expect(a.health()).toBe("ok");
  });
  it("suspended → blocked; unlock() resume qiladi", async () => {
    const c = fakeCtx("suspended");
    const a = new Annunciator({ contextFactory: () => c });
    expect(a.health()).toBe("blocked");
    expect(a.beep("critical")).toBe(false);
    expect(await a.unlock()).toBe("ok");
    expect(c.resume).toHaveBeenCalled();
    expect(a.beep("critical")).toBe(true);
  });
  it("AudioContext yo'q → unsupported; xato yutilmaydi, sog'liqda ko'rinadi", () => {
    const a = new Annunciator({ contextFactory: () => { throw new Error("no audio"); } });
    expect(a.health()).toBe("unsupported");
    expect(a.beep("high")).toBe(false);
  });
  it("kritik ack gacha takrorlanadi; ack to'xtatadi; past ustuvorlik jim", () => {
    vi.useFakeTimers();
    const a = new Annunciator({ contextFactory: () => fakeCtx() });
    a.alarm(7, "critical");
    expect(a.played).toBe(1);
    vi.advanceTimersByTime(PATTERNS.critical.repeatMs * 3 + 10);
    expect(a.played).toBe(4);
    expect(a.repeating).toBe(1);
    a.ack(7);
    vi.advanceTimersByTime(PATTERNS.critical.repeatMs * 3);
    expect(a.played).toBe(4);
    expect(a.repeating).toBe(0);
    a.alarm(8, "high");
    vi.advanceTimersByTime(60_000);
    expect(a.played).toBe(5); // takrorsiz
    a.alarm(9, "low");
    expect(a.played).toBe(5);
    vi.useRealTimers();
  });
  it("silence muddat bilan; mute o'chiradi va takrorlarni to'xtatadi", () => {
    let now = 0;
    const a = new Annunciator({ contextFactory: () => fakeCtx(), now: () => now, setTimer: () => 1, clearTimer: () => undefined });
    a.alarm(1, "critical");
    a.silence(5);
    expect(a.health()).toBe("silenced");
    expect(a.repeating).toBe(0);
    expect(a.beep("critical")).toBe(false);
    now = 5 * 60_000 + 1;
    expect(a.health()).toBe("ok");
    a.setMuted(true);
    expect(a.health()).toBe("off");
    expect(a.beep("critical")).toBe(false);
    const seen: string[] = [];
    a.onChange(() => seen.push(a.health()));
    a.setMuted(false);
    expect(seen).toEqual(["ok"]);
  });
});
