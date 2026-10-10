import { useSearchParams } from "react-router-dom";
import { TvSettings } from "../components/TvSettings";

/** /link: where the TV app sends people (its QR code opens /link?code=…). Signing in first is handled by the
 *  AuthProvider, which keeps this address. */
export default function LinkTv() {
  const [params] = useSearchParams();
  return (
    <div className="page narrow">
      <div className="page-head"><h1>Link a TV</h1></div>
      <div className="lib-list"><TvSettings code={params.get("code") ?? ""} /></div>
    </div>
  );
}
