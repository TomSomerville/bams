// One keydown listener for the whole app (App.tsx). A screen that wants keys before the arrows move the focus
// (the player) installs a handler; it returns true when it used the key.

export type KeyHandler = (e: KeyboardEvent) => boolean;

let handler: KeyHandler | null = null;

export function setKeyHandler(h: KeyHandler | null) {
  handler = h;
}

export const keyHandler = () => handler;
