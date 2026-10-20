import { useState } from "react";
import { dropAccount, MAX_ACCOUNTS, otherAccounts } from "../api";
import { useFocusOnReady, useNav } from "../App";
import { focusFirst } from "../nav";

// Theatre mode's Switch account (the rail, above Settings): the accounts signed in on this PC, switched with no
// password, like the web's. Each keeps its own sign-in (and its other servers) on this PC; api.ts stashAccount.

export default function Accounts() {
  const nav = useNav();
  const [others, setOthers] = useState(otherAccounts);
  useFocusOnReady(true);

  const drop = (id: number) => {
    dropAccount(id);
    setOthers(otherAccounts());
    setTimeout(() => focusFirst(document.querySelector("main") ?? document));
  };

  return (
    <div className="page settings">
      <div className="page-head"><h1>Switch account</h1></div>
      <section className="panel">
        <p className="big">Signed in as <strong>{nav.user?.name}</strong>.</p>
        {others.map((u) => (
          <div key={u.id} className="account-row" data-row>
            <button className="btn primary" data-fid={`acct-${u.id}`} onClick={() => nav.switchAccount(u.id)}>
              Switch to {u.name}</button>
            <button className="btn ghost" data-fid={`acct-out-${u.id}`} onClick={() => drop(u.id)}>Sign {u.name} out</button>
          </div>
        ))}
        {!others.length && <p>No other account is signed in on this PC yet. Add one: you can then switch between them
          here with no password.</p>}
        {others.length + 1 < MAX_ACCOUNTS && (
          <button className="btn" data-fid="acct-add" data-autofocus={!others.length || undefined} onClick={nav.addAccount}>
            Add an account</button>
        )}
        <p className="muted">Signing out (Settings) moves to the next account signed in here.</p>
      </section>
    </div>
  );
}
