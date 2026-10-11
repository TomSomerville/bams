// The test page's entry (index.html): the app's styles, every test file, then run them.
import "../src/styles.css";
import "./nav.test";
import "./hold.test";
import { runAll } from "./harness";

void runAll();
