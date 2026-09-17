import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";
import { CommandHistory, parseCommand, suggest, type ParsedCommand } from "../viewer/commands";

interface Props {
  onCommand: (cmd: ParsedCommand) => void;
  log: string;
}

/** AutoCAD uslubidagi buyruqlar qatori: Enter — bajarish, bo'sh Enter — oxirgisini takrorlash, ↑/↓ — tarix, Tab — to'ldirish. */
export default function CommandLine({ onCommand, log }: Props) {
  const [value, setValue] = useState("");
  const [sel, setSel] = useState(0);
  const history = useRef(new CommandHistory());
  const inputRef = useRef<HTMLInputElement>(null);
  const suggestions = value.includes(" ") ? [] : suggest(value);

  // Canvas ustida yozishni boshlasa — fokus buyruqlar qatoriga (AutoCAD odati)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      if (e.defaultPrevented) return; // viewport tezkor tugmasi (Blender: G/R/S/Z/H…) ishlatilgan — buyruq qatoriga o'tmaymiz
      if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
        inputRef.current?.focus();
      } else if (e.key === "Escape") {
        onCommand({ name: "ESC", args: [], raw: "ESC" });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCommand]);

  function run(text: string) {
    const parsed = parseCommand(text) ?? (history.current.last ? parseCommand(history.current.last) : null);
    if (!parsed) return;
    history.current.push(parsed.raw);
    onCommand(parsed);
    setValue("");
    setSel(0);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (suggestions.length && value && !value.includes(" ") && suggestions[sel] && suggestions[sel].name !== value.toUpperCase()) {
        // aniq mos kelmasa — tanlangan taklifni bajaradi
        const exact = suggestions.find((s) => s.name === value.toUpperCase() || s.aliases.includes(value.toUpperCase()));
        run(exact ? value : suggestions[sel].name);
      } else run(value);
    } else if (e.key === "Escape") {
      e.preventDefault();
      if (value) setValue("");
      else onCommand({ name: "ESC", args: [], raw: "ESC" });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (suggestions.length) setSel((s) => Math.max(0, s - 1));
      else setValue(history.current.prev() ?? "");
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (suggestions.length) setSel((s) => Math.min(suggestions.length - 1, s + 1));
      else setValue(history.current.next() ?? "");
    } else if (e.key === "Tab" && suggestions.length) {
      e.preventDefault();
      setValue(suggestions[sel].name + " ");
    }
  }

  return (
    <div className="ws-cmd">
      {suggestions.length > 0 && (
        <div className="suggest">
          {suggestions.map((s, i) => (
            <div key={s.name} className={i === sel ? "active" : ""} onMouseDown={(e) => { e.preventDefault(); run(s.name); }}>
              <b>{s.name}</b>
              <span>{s.usage ?? s.description}</span>
            </div>
          ))}
        </div>
      )}
      <span className="prompt"><Icon name="chevron-right" size={12} /></span>
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => { setValue(e.target.value); setSel(0); }}
        onKeyDown={onKeyDown}
        placeholder="Buyruq kiriting (HELP — ro'yxat)"
        spellCheck={false}
        aria-label="Buyruqlar qatori"
      />
      <span className="hint">{log}</span>
    </div>
  );
}
