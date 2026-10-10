import { useEffect, useState } from "react";
import { api, type ServerName } from "../api";

/** Settings (admins): what this server is called where apps list servers (TVs, other browsers' sidebars). */
export default function ServerNameSettings() {
  const [cur, setCur] = useState<ServerName | null>(null);
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get<{ server_name: ServerName }>("/api/settings")
      .then((s) => { setCur(s.server_name); setName(s.server_name.custom ? s.server_name.name : ""); })
      .catch((e) => setErr((e as Error).message));
  }, []);

  const save = async (value: string) => {
    setErr(null);
    setSaved(false);
    try {
      const r = await api.put<ServerName>("/api/settings/server-name", { name: value });
      setCur(r);
      setName(r.custom ? r.name : "");
      setSaved(true);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="lib-card">
      <div className="lib-head"><h3>Server name</h3>{cur && <span className="muted lib-counts">Now: {cur.name}</span>}</div>
      <p className="muted">How this server shows up on TVs and in other browsers that connect to it. Leave it empty
        for the default{cur ? <> (<strong>{cur.default}</strong>)</> : null}.</p>
      <form className="rename" onSubmit={(e) => { e.preventDefault(); void save(name); }}>
        <input value={name} maxLength={60} onChange={(e) => { setName(e.target.value); setSaved(false); }}
          placeholder={cur?.default ?? ""} aria-label="Server name" />
        <button className="btn primary small" disabled={!cur || name.trim() === (cur.custom ? cur.name : "")}>Save</button>
        {cur?.custom && <button type="button" className="btn ghost small" onClick={() => void save("")}>Use the default</button>}
        {saved && <span className="muted">Saved.</span>}
      </form>
      {err && <p className="key-msg bad">{err}</p>}
    </div>
  );
}
