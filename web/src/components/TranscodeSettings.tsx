import { useEffect, useState } from "react";
import { api, type ServerStatus } from "../api";
import Icon from "./Icon";

type TranscodeSettingsShape = { max_transcodes: number; max_transcodes_auto: number };

/** Video conversion: which encoder the server found, and how many conversions may run at once. */
export default function TranscodeSettings({ status }: { status: ServerStatus | null }) {
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
