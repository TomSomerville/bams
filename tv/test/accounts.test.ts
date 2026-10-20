// Theatre mode's Switch account (src/api.ts stashAccount…): several accounts signed in on one PC, each with its own
// token and its own other servers; switching, signing out and dropping one never mixes them up.
import { dropAccount, extras, getToken, nextAccount, otherAccounts, savedUser, setServer, setSession, stashAccount,
  switchAccount } from "../src/api";
import { local } from "../src/platform";
import type { User } from "../../web/src/api";
import { eq as same, test } from "./harness";

// compares lists too (the harness's eq is ===)
const eq = (got: unknown, want: unknown, what: string) => same(JSON.stringify(got), JSON.stringify(want), what);

const user = (id: number, name: string) => ({ id, name, is_admin: false }) as unknown as User;

test("accounts: switch, sign out to the next one, drop one; each keeps its own servers", () => {
  const saved = ["bams.server", "bams.token", "bams.user", "bams.servers", "bams.others"].map((k) => [k, local.get(k)] as const);
  try {
    setServer(null);  // no requests from this test
    setSession("tok-mum", user(1, "mum"));
    local.set("bams.servers", JSON.stringify([{ id: 1, url: "http://x", name: "X", token: "t", libraries: [], hidden: {} }]));
    stashAccount();  // Add an account
    eq(getToken(), null, "signing another in starts with no session");
    eq(extras().length, 0, "nor mum's other servers");
    setSession("tok-kid", user(2, "kid"));
    eq(otherAccounts().map((u) => u.name), ["mum"], "mum waits");

    eq(switchAccount(1), true, "switch to mum");
    eq([getToken(), savedUser()?.name], ["tok-mum", "mum"], "mum is current");
    eq(extras().map((e) => e.name), ["X"], "with her servers back");
    eq(otherAccounts().map((u) => u.name), ["kid"], "kid waits now");
    eq(switchAccount(99), false, "an account not signed in here");

    setSession(null);  // mum signs out
    eq(nextAccount(), true, "kid takes over");
    eq([getToken(), savedUser()?.name, extras().length], ["tok-kid", "kid", 0], "kid, without mum's servers");
    eq(otherAccounts().length, 0, "nobody waits");
    eq(nextAccount(), false, "nobody to move to");

    stashAccount();
    setSession("tok-mum2", user(1, "mum"));
    dropAccount(2);
    eq(otherAccounts().length, 0, "kid signed out of this PC");
    eq(getToken(), "tok-mum2", "the current account stays");
  } finally {
    for (const [k, v] of saved) if (v === null) local.remove(k); else local.set(k, v);
  }
});
