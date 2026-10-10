import { useEffect, useRef, useState } from "react";
import { getServer, hello, normalizeServer, setServer, type Hello } from "../api";
import { focusFirst } from "../nav";
import { localIp } from "../tizen";

const PORT = 8484;

type Found = { url: string; hello: Hello };

/** Pick the BAMS server: found by looking around the TV's network, or typed in. */
export default function Connect({ onConnected }: { onConnected: () => void }) {
  const [found, setFound] = useState<Found[]>([]);
  const [scanning, setScanning] = useState<{ done: number; total: number } | null>(null);
  const [addr, setAddr] = useState(() => getServer()?.replace(/^https?:\/\//, "") ?? "");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [looked, setLooked] = useState<string | null>(null);
  const stop = useRef(false);

  useEffect(() => {
    setTimeout(() => focusFirst());
    void scan();
    return () => { stop.current = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Ask every address of the TV's /24 network for /api/hello on BAMS's port, a few dozen at a time. */
  async function scan() {
    const ip = await localIp();
    const saved = getServer();
    const candidates: string[] = [];
    if (saved) candidates.push(saved);
    if (location.protocol.startsWith("http")) {
      candidates.push(`http://${location.hostname}:${PORT}`);  // developing in a browser on the server's PC
    }
    // the TV's own /24, or (when the TV won't say its address) the networks home routers use most
    const nets = ip ? [ip.split(".").slice(0, 3).join(".")] : ["192.168.1", "192.168.0", "10.0.0", "192.168.86"];
    setLooked(nets.map((n) => `${n}.x`).join(", "));
    for (const net of nets) {
      for (let n = 1; n < 255; n++) if (`${net}.${n}` !== ip) candidates.push(`http://${net}.${n}:${PORT}`);
    }
    const list = Array.from(new Set(candidates));
    setScanning({ done: 0, total: list.length });
    let done = 0;
    const next = async (): Promise<void> => {
      const url = list.shift();
      if (!url || stop.current) return;
      const h = await hello(url, 1500);
      done++;
      setScanning((s) => (s ? { ...s, done } : s));
      if (h) setFound((f) => (f.some((x) => x.url === url) ? f : [...f, { url, hello: h }]));
      return next();
    };
    await Promise.all(Array.from({ length: 32 }, next));
    if (!stop.current) setScanning(null);
  }

  async function connect(url: string | null) {
    setErr(null);
    if (!url) return setErr("That doesn't look like an address. Type it like 192.168.1.20 or 192.168.1.20:8484.");
    setBusy(true);
    const h = await hello(url, 4000);
    setBusy(false);
    if (!h) {
      return setErr(`No BAMS server answered at ${url.replace(/^https?:\/\//, "")}. Check the address, that BAMS is ` +
        "running, and that it accepts connections from the network (not only from its own PC).");
    }
    setServer(url);
    onConnected();
  }

  return (
    <div className="center-screen connect">
      <img className="wordmark" src="bams-wordmark.png" alt="BAMS" />
      <h1>Find your BAMS server</h1>
      <div className="found">
        {found.map((f, i) => (
          <button key={f.url} className="btn server" data-autofocus={i === 0 || undefined} onClick={() => void connect(f.url)}>
            <strong>{f.hello.name}</strong>
            <span>{f.url.replace(/^https?:\/\//, "")} · BAMS {f.hello.version}</span>
          </button>
        ))}
        {scanning && <p className="muted">Looking on your network{looked ? ` (${looked})` : ""}… {scanning.done} of {scanning.total}</p>}
        {!scanning && !found.length && <p className="muted">No server found{looked ? ` on ${looked}` : ""}. Type its address below.</p>}
      </div>
      <form className="addr" onSubmit={(e) => { e.preventDefault(); void connect(normalizeServer(addr)); }}>
        <input className="text-input" value={addr} placeholder="Address, e.g. 192.168.1.20:8484" onChange={(e) => setAddr(e.target.value)} />
        <button className="btn primary" disabled={busy}>{busy ? "Connecting…" : "Connect"}</button>
      </form>
      {err && <p className="error">{err}</p>}
      <p className="muted small">The address is shown on the PC that runs BAMS (the one in the browser's address bar
        when you open BAMS there, but with the PC's network address instead of “localhost”).</p>
    </div>
  );
}
