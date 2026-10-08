import { useId, useState, type InputHTMLAttributes } from "react";

export type ComboOption = { value: string; label?: string; note?: string };

/** A text field that suggests matching entries as you type (arrow keys / Enter / click to pick).
 *  Typing anything else is fine too: the suggestions only help. */
export default function Combo({ value, onChange, options, onPick, className, ...props }: {
  value: string;
  onChange: (v: string) => void;
  options: ComboOption[];
  /** called with the picked option; by default the field just takes its value */
  onPick?: (o: ComboOption) => void;
} & Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const q = value.trim().toLowerCase();
  const shown = options
    .filter((o) => !q || (o.label ?? o.value).toLowerCase().includes(q) || o.value.toLowerCase().includes(q))
    // the ones starting with what's typed first
    .sort((a, b) => Number(!(a.label ?? a.value).toLowerCase().startsWith(q)) - Number(!(b.label ?? b.value).toLowerCase().startsWith(q)))
    .slice(0, 8);
  const visible = open && shown.length > 0 && !(shown.length === 1 && shown[0].value === value);

  const pick = (o: ComboOption) => {
    if (onPick) onPick(o);
    else onChange(o.value);
    setOpen(false);
  };

  return (
    <span className={`combo ${className ?? ""}`}>
      <input {...props} className="text-input" value={value} role="combobox" autoComplete="off"
        aria-expanded={visible} aria-controls={`${id}-list`} aria-autocomplete="list"
        aria-activedescendant={visible ? `${id}-${hi}` : undefined}
        onChange={(e) => { onChange(e.target.value); setOpen(true); setHi(0); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            if (!visible) return setOpen(true);
            setHi((h) => (h + (e.key === "ArrowDown" ? 1 : shown.length - 1)) % shown.length);
          } else if (e.key === "Enter" && visible) {
            e.preventDefault();
            pick(shown[Math.min(hi, shown.length - 1)]);
          } else if (e.key === "Escape" && visible) {
            e.stopPropagation();
            setOpen(false);
          }
        }} />
      {visible && (
        <ul className="combo-list" id={`${id}-list`} role="listbox" onMouseDown={(e) => e.preventDefault()}>
          {shown.map((o, i) => (
            <li key={`${o.value}-${i}`} id={`${id}-${i}`} role="option" aria-selected={i === hi}
              className={i === hi ? "on" : ""} onMouseEnter={() => setHi(i)} onClick={() => pick(o)}>
              <span>{o.label ?? o.value}</span>{o.note && <span className="muted">{o.note}</span>}
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}
