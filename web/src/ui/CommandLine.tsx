import { useRef, useState } from "react";
import Icon from "./Icon";
import { CommandHistory, parseCommand, suggest, type ParsedCommand } from "../viewer/commands";

interface Props {
  onCommand: (cmd: ParsedCommand) => void;
  log: string;
}

const INPUT_ID = "ws-cmd-input";
const LIST_ID = "ws-cmd-suggest";

/** Buyruqlar qatoriga fokus — faqat aniq tezkor tugma bilan (`:` 3D ko'rinishda yoki Ctrl+K), UX-10:
 * avvalgi "istalgan harf bosilsa fokusni tortib olish" panel/forma va ekran o'quvchi bilan to'qnashardi. */
export function focusCommandLine(): void {
  document.getElementById(INPUT_ID)?.focus();
}

/** AutoCAD uslubidagi buyruqlar qatori: Enter — bajarish, bo'sh Enter — oxirgisini takrorlash, ↑/↓ — tarix, Tab — to'ldirish. */
export default function CommandLine({ onCommand, log }: Props) {
  const [value, setValue] = useState("");
  const [sel, setSel] = useState(0);
  const history = useRef(new CommandHistory());
  const inputRef = useRef<HTMLInputElement>(null);
  const suggestions = value.includes(" ") ? [] : suggest(value);

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
        <div className="suggest" role="listbox" id={LIST_ID} aria-label="Buyruq takliflari">
          {suggestions.map((s, i) => (
            <div key={s.name} id={`${LIST_ID}-${i}`} role="option" aria-selected={i === sel} tabIndex={-1} className={i === sel ? "active" : ""} onMouseDown={(e) => { e.preventDefault(); run(s.name); }}>
              <b>{s.name}</b>
              <span>{s.usage ?? s.description}</span>
            </div>
          ))}
        </div>
      )}
      <span className="prompt"><Icon name="chevron-right" size={12} /></span>
      <input
        ref={inputRef}
        id={INPUT_ID}
        role="combobox"
        aria-expanded={suggestions.length > 0}
        aria-controls={LIST_ID}
        aria-autocomplete="list"
        aria-activedescendant={suggestions.length ? `${LIST_ID}-${sel}` : undefined}
        value={value}
        onChange={(e) => { setValue(e.target.value); setSel(0); }}
        onKeyDown={onKeyDown}
        placeholder="Buyruq ( : yoki Ctrl+K ) — HELP ro'yxat"
        spellCheck={false}
        aria-label="Buyruqlar qatori"
      />
      <span className="hint">{log}</span>
    </div>
  );
}
