import { useEffect, useState } from "react";
import { api, type ServerStatus } from "../api";
import Icon from "./Icon";

type TranscodeSettingsShape = { max_transcodes: number; max_transcodes_auto: number };
type Encoders = {
  choice: string | null; active: string | null; automatic: string | null; forced: boolean;
  options: { id: string; name: string; hardware: boolean }[];
};

/** CPU or GPU: every H.264 encoder that works on the server (each is test-encoded once, so this can take a moment). */
function EncoderChoice({ onChange }: { onChange?: () => void }) {
  const [enc, setEnc] = useState<Encoders | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get<Encoders>("/api/settings/encoders").then(setEnc).catch((e) => setErr(e.message));
  }, []);

  const pick = async (id: string) => {
    setErr(null);
    setBusy(true);
    try {
      setEnc(await api.put<Encoders>("/api/settings/encoder", { encoder: id || null }));
      onChange?.();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // Media Foundation is Windows' own encoder: it may run on the GPU or the CPU, Windows decides
  const label = (o: Encoders["options"][number]) => (o.id === "h264_mf" ? "Windows Media Foundation"
    : `${o.name.replace(" (CPU)", "")} (${o.hardware ? "GPU" : "CPU"})`);
  if (!enc) return err ? <p className="key-msg bad">{err}</p> : <p className="muted">Checking which encoders work…</p>;
  if (!enc.options.length) return null;
  const auto = enc.options.find((o) => o.id === enc.automatic);
  return (
    <>
      <div className="key-row">
        <label htmlFor="video-encoder">Convert with</label>
        <select id="video-encoder" className="select" value={enc.choice ?? ""} disabled={enc.forced || busy}
          onChange={(e) => pick(e.target.value)}>
          <option value="">{auto ? `Automatic: ${label(auto)}` : "Automatic"}</option>
          {enc.options.map((o) => <option key={o.id} value={o.id}>{label(o)}</option>)}
        </select>
      </div>
      {enc.forced && <p className="fine-print">Set by the server's <code>BAMS_VIDEO_ENCODER</code> setting.</p>}
      {!enc.forced && <p className="fine-print">The GPU converts faster and keeps the CPU free; the CPU (x264) can look a
        little better at the same size. Videos already playing keep what they started with.</p>}
      {err && <p className="key-msg bad">{err}</p>}
    </>
  );
}

/** Video conversion: which encoder the server found, and how many conversions may run at once. */
export default function TranscodeSettings({ status, onChange }: { status: ServerStatus | null; onChange?: () => void }) {
  const [s, setS] = useState<TranscodeSettingsShape | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.get<TranscodeSettingsShape>("/api/settings").then(setS).catch((e) => setErr(e.message));
  }, []);

  const save = async (n: number) => {
    setErr(null);
    try {
      await api.put("/api/settings/transcoding", { max_transcodes: n });
      setS((old) => old && { ...old, max_transcodes: n });
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const enc = status?.video_encoder;
  return (
    <section className="lib-card settings-card">
      <div className="lib-head">
        <h3>Video conversion</h3>
        {status && (enc
          ? <span className="status-pill ok"><Icon name="check" size={14} /> {enc.name}{enc.hardware ? " (GPU)" : ""}</span>
          : <span className="status-pill warn">Unavailable</span>)}
      </div>
      <p className="muted">
        Videos a browser can't decode (Xvid, MPEG-2, VC-1, HEVC in Firefox…) are converted to H.264 while you watch,
        and the player's quality menu converts any video to a smaller size.
        {enc && (enc.hardware
          ? ` The server uses the GPU (${enc.name})${enc.hw_decode ? " to decode and encode" : ""}, up to 4K.`
          : " The server uses the CPU, up to 1080p.")}
      </p>
      {status?.ffmpeg && !enc && (
        <p className="key-msg warn">FFmpeg has no working H.264 encoder, so these videos can't be converted. Install an
          FFmpeg build with libx264 or GPU encoding and restart the server.</p>
      )}
      {status && !status.ffmpeg && (
        <p className="key-msg warn">FFmpeg wasn't found by the server, so nothing can be converted.</p>
      )}
      {status?.ffmpeg && <EncoderChoice onChange={() => { onChange?.(); api.get<TranscodeSettingsShape>("/api/settings").then(setS).catch(() => {}); }} />}
      {s && (
        <>
          <div className="key-row">
            <label htmlFor="max-transcodes">Convert at most</label>
            <select id="max-transcodes" className="select" value={s.max_transcodes}
              onChange={(e) => save(Number(e.target.value))}>
              <option value={0}>Automatic ({s.max_transcodes_auto})</option>
              {[1, 2, 3, 4, 6, 8, 12, 16].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <span>videos at once</span>
            {status?.transcodes && <span className="muted">({status.transcodes.running} now)</span>}
          </div>
          <p className="fine-print">Each player converting a video holds a place until it's closed. Anyone over the
            limit gets a "server busy" message.</p>
        </>
      )}
      {err && <p className="key-msg bad">{err}</p>}
    </section>
  );
}
