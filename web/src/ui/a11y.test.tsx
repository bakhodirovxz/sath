import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { BList, BPanel } from "./BlenderUI";
import CommandLine, { focusCommandLine } from "./CommandLine";
import Dialog, { isModalOpen } from "./Dialog";

/** UX-10: modal dialog steki, fokus-tuzoq, fokus qaytishi; buyruqlar qatori fokusni o'g'irlamaydi; UIList klaviaturasi. */

function Stack() {
  const [outer, setOuter] = useState(false);
  const [inner, setInner] = useState(false);
  return (
    <>
      <button onClick={() => setOuter(true)}>ochish</button>
      {outer && (
        <Dialog title="Tashqi" onClose={() => setOuter(false)}>
          <input aria-label="nom" />
          <button onClick={() => setInner(true)}>ichki</button>
          {inner && (
            <Dialog title="Ichki" onClose={() => setInner(false)}>
              <button>ha</button>
              <button>yo'q</button>
            </Dialog>
          )}
        </Dialog>
      )}
    </>
  );
}

describe("Dialog (UX-10)", () => {
  it("aria-modal, sarlavha bilan nomlangan, birinchi maydonga fokus", () => {
    render(<Stack />);
    fireEvent.click(screen.getByText("ochish"));
    const dlg = screen.getByRole("dialog", { name: "Tashqi" });
    expect(dlg).toHaveAttribute("aria-modal", "true");
    expect(document.activeElement).toBe(screen.getByLabelText("nom"));
    expect(isModalOpen()).toBe(true);
  });

  it("ustma-ust dialoglar: Esc faqat yuqoridagini yopadi; fokus chaqiruvchiga qaytadi", () => {
    render(<Stack />);
    const opener = screen.getByText("ochish");
    opener.focus();
    fireEvent.click(opener);
    const innerBtn = screen.getByText("ichki");
    innerBtn.focus();
    fireEvent.click(innerBtn);
    expect(screen.getByRole("dialog", { name: "Ichki" })).toBeInTheDocument();
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Ichki" })).toBeNull();
    expect(screen.getByRole("dialog", { name: "Tashqi" })).toBeInTheDocument();
    expect(document.activeElement).toBe(innerBtn); // ichki yopilgach fokus uni ochgan tugmaga
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
    expect(isModalOpen()).toBe(false);
  });

  it("Tab fokusni dialog ichida aylantiradi", () => {
    render(<Stack />);
    fireEvent.click(screen.getByText("ochish"));
    fireEvent.click(screen.getByText("ichki"));
    const [ha, yoq] = [screen.getByText("ha"), screen.getByText("yo'q")];
    expect(document.activeElement).toBe(ha);
    yoq.focus();
    fireEvent.keyDown(yoq, { key: "Tab" });
    expect(document.activeElement).toBe(ha);
    fireEvent.keyDown(ha, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(yoq);
  });
});

describe("CommandLine (UX-10)", () => {
  it("oddiy harf bosilganda fokusni o'g'irlamaydi; faqat focusCommandLine() bilan", () => {
    const onCommand = vi.fn();
    render(<><button>boshqa</button><CommandLine onCommand={onCommand} log="" /></>);
    const other = screen.getByText("boshqa");
    other.focus();
    fireEvent.keyDown(other, { key: "h" });
    expect(document.activeElement).toBe(other);
    focusCommandLine();
    expect(document.activeElement).toBe(screen.getByRole("combobox", { name: "Buyruqlar qatori" }));
  });
});

describe("BlenderUI (UX-10)", () => {
  it("BPanel sarlavhasi — aria-expanded li tugma", () => {
    render(<BPanel id="t-a11y" title="Panel">ichida</BPanel>);
    const b = screen.getByRole("button", { name: /Panel/ });
    expect(b).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(b);
    expect(b).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("ichida")).toBeNull();
  });

  it("BList: listbox, roving tabindex, ↑/↓ tanlash, Enter ochish", () => {
    const onActivate = vi.fn();
    function L() {
      const [a, setA] = useState<number | null>(null);
      return <BList label="ro'yxat" items={[1, 2, 3]} keyOf={(x) => x} render={(x) => `qator ${x}`} activeKey={a} onSelect={setA} onActivate={onActivate} />;
    }
    render(<L />);
    const opts = screen.getAllByRole("option");
    expect(opts.map((o) => o.tabIndex)).toEqual([0, -1, -1]);
    opts[0].focus();
    fireEvent.keyDown(opts[0], { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(document.activeElement!, { key: "ArrowDown" });
    const now = screen.getAllByRole("option");
    expect(now[1]).toHaveAttribute("aria-selected", "true");
    expect(document.activeElement).toBe(now[1]);
    fireEvent.keyDown(now[1], { key: "Enter" });
    expect(onActivate).toHaveBeenCalledWith(2);
  });
});
