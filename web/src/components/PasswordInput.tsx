import { useState, type InputHTMLAttributes } from "react";
import Icon from "./Icon";

/** A password field with a show/hide button, so people can check what they typed. */
export default function PasswordInput({ className, ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const [reveal, setReveal] = useState(false);
  return (
    <span className={`pw-input${className ? ` ${className}` : ""}`}>
      <input {...props} type={reveal ? "text" : "password"} spellCheck={false} />
      <button type="button" className="icon-btn" onClick={() => setReveal(!reveal)}
        aria-label={reveal ? "Hide password" : "Show password"} title={reveal ? "Hide password" : "Show password"}>
        <Icon name={reveal ? "eyeOff" : "eye"} size={18} />
      </button>
    </span>
  );
}
