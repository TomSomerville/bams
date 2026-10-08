import { useEffect, useState } from "react";
import { api } from "../api";
import Icon from "./Icon";

type Output = "aac" | "flac";

/** On/off for online music identification (no key needed: the services are open), and what music browsers
 *  can't play is converted to. */
export default function MusicSettings() {
  const [on, setOn] = useState<boolean | null>(null);
  const [output, setOutput] = useState<Output | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ music_lookup: boolean; music_output: Output }>("/api/settings")
      .then((s) => { setOn(s.music_lookup); setOutput(s.music_output); })
      .catch((e) => setErr(e.message));
  }, []);

  const pickOutput = async (o: Output) => {
    setErr(null);
    try {
      setOutput((await api.put<{ music_output: Output }>("/api/settings/music-output", { output: o })).music_output);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const toggle = async () => {
    setErr(null);
    try {
      setOn((await api.put<{ music_lookup: boolean }>("/api/settings/music-lookup", { enabled: !on })).music_lookup);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <section className="lib-card settings-card">
      <div className="lib-head">
        <h3>Music identification</h3>
        {on !== null && (on
          ? <span className="status-pill ok"><Icon name="check" size={14} /> On</span>
          : <span className="status-pill warn">Off</span>)}
      </div>
      <p className="muted">
        After each scan of a music library, BAMS looks up new albums and artists on{" "}
        <a href="https://musicbrainz.org" target="_blank" rel="noreferrer">MusicBrainz</a> (album names, original
        release years, track titles for untagged files), takes missing covers from the{" "}
        <a href="https://coverartarchive.org" target="_blank" rel="noreferrer">Cover Art Archive</a>, and artist
        bios and photos from Wikipedia and Wikimedia Commons. No account or key is needed. Your own tags, genres and
        cover images always come first. When it's off, music is identified from tags and folders only.
      </p>
      <div className="key-row">
        <button className={`btn small ${on ? "ghost" : "primary"}`} onClick={toggle} disabled={on === null}>
          {on ? "Turn off" : "Turn on"}
        </button>
        <span className="muted">Albums it couldn't identify can be fixed from the album page ("Fix match").</span>
      </div>
      <p className="fine-print">
        Only artist and album names are sent to these services. MusicBrainz data is CC0; Wikipedia text is CC BY-SA
        and each photo shows its own author and licence. Identified albums and artists are looked up again every
        few months.
      </p>

      <h4 className="settings-sub">Converted music</h4>
      <p className="muted">
        Formats browsers can't play (ALAC, AIFF, WMA, APE, WavPack, DSD…) are converted while they stream. FLAC is
        lossless and plays gaplessly, but uses about four times the data of AAC: best on your home network.
      </p>
      <div className="segmented" role="radiogroup" aria-label="Convert music to">
        {([["aac", "AAC 256 kbps"], ["flac", "FLAC (lossless)"]] as const).map(([k, label]) => (
          <button key={k} role="radio" aria-checked={output === k} className={output === k ? "on" : ""}
            disabled={output === null} onClick={() => output !== k && pickOutput(k)}>
            {label}
          </button>
        ))}
      </div>
      {err && <p className="key-msg bad">{err}</p>}
    </section>
  );
}
