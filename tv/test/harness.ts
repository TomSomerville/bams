// A small test runner for the page scripts/test.mjs builds (run.ts): each test gets an empty #root laid out with the
// app's own styles at 1920x1080; the results go into <pre id="results"> for the script to read.

type Test = { name: string; fn: () => void | Promise<void> };
const tests: Test[] = [];

export function test(name: string, fn: () => void | Promise<void>) {
  tests.push({ name, fn });
}

export function eq<T>(got: T, want: T, what = "value") {
  if (got !== want) throw new Error(`${what}: expected ${JSON.stringify(want)}, got ${JSON.stringify(got)}`);
}

export function ok(cond: unknown, what: string) {
  if (!cond) throw new Error(what);
}

export const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Put `html` in #root (fresh for each test). */
export function mount(html: string): HTMLElement {
  const root = document.getElementById("root")!;
  root.innerHTML = html;
  return root;
}

/** The [data-fid] of the focused element ("body" when nothing has the focus). */
export function focused(): string {
  const a = document.activeElement as HTMLElement | null;
  if (!a || a === document.body) return "body";
  return a.dataset.fid ?? (a.id || a.tagName);
}

export async function runAll() {
  const results: { name: string; ok: boolean; error?: string }[] = [];
  for (const t of tests) {
    (document.activeElement as HTMLElement | null)?.blur?.();
    document.getElementById("root")!.innerHTML = "";
    try {
      await t.fn();
      results.push({ name: t.name, ok: true });
    } catch (e) {
      results.push({ name: t.name, ok: false, error: (e as Error).message });
    }
  }
  document.getElementById("results")!.textContent = JSON.stringify(results);
}
