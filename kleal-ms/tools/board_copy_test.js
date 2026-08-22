// The agent's questions in the create wizard, held to the board's exact wording.
//
//   node tools/board_copy_test.js services/profile/app.py
//
// Figma «1:1 Offline», OF.04–OF.12 and OF.16. These strings are the whole voice of the product — the
// agent asking one short question at a time — and they drift silently: a synonym reads fine in
// isolation, so nobody notices the screen no longer says what the design says.
//
// Three had drifted when this was written: OF.05 asked «What format do you prefer?» instead of «How
// do you want to meet?», OF.10 used a typewriter apostrophe, and OF.07–09 had grown two different
// wordings for the one prompt the board shares across all three steps.
//
// Every English string below was read out of the Figma text layers, character for character.
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");

let fails = 0;
function check(name, cond, detail) {
  if (!cond) fails++;
  console.log((cond ? "  ok    " : "  FAIL  ") + name + (detail !== undefined ? "   " + JSON.stringify(detail).slice(0, 150) : ""));
}

// Every kprompt(...) in the file, with its Russian and English halves.
const prompts = [...src.matchAll(/kprompt\(T\('((?:[^'\\]|\\.)*)','((?:[^'\\]|\\.)*)'\)\)/g)]
  .map((m) => ({ ru: m[1], en: m[2] }));
const en = prompts.map((p) => p.en);

console.log("1. The agent asks the board's questions, word for word");
const BOARD = [
  ["OF.04", "What do you want to do?"],
  ["OF.05", "How do you want to meet?"],
  ["OF.06", "How many people will there be?"],
  ["OF.07/08/09", "To match you better, one thing"],
  ["OF.10", "Here’s what I got"],
  ["OF.12/15/17", "Best fit for your request"],
];
for (const [frame, want] of BOARD) {
  const found = src.includes("'" + want + "'");
  check(frame + "  «" + want + "»", found, found ? undefined : en);
}

// Only STRING LITERALS count. A comment naming the old Figma frame is documentation, not copy — the
// first version of this test failed on its own comments, and a test that can only be kept green by
// deleting an accurate comment is measuring the wrong thing.
const code = src.split("\n").filter((l) => !/^\s*\/\//.test(l)).join("\n");

console.log("\n2. The drifts that actually happened");
check("OF.05 no longer asks about a «format»", !/'What format do you prefer/.test(code));
check("OF.10 uses the typographic apostrophe, not the typewriter one",
  code.includes("Here’s what I got") && !code.includes("'Here's what I got'"));
check("OF.07–09 share ONE prompt, as on the board",
  en.filter((x) => x === "To match you better, one thing").length >= 2 &&
  !/To match you better, one thing:/.test(src));

console.log("\n3. Every prompt is bilingual and neither half is empty");
for (const p of prompts) {
  check("«" + p.en.slice(0, 42) + "»", p.ru.length > 0 && p.en.length > 0, p);
}

console.log("\n4. Russian is written, not transliterated");
for (const p of prompts) {
  check("ru for «" + p.en.slice(0, 34) + "»", /[а-яё]/i.test(p.ru), p.ru);
}

console.log("\n5. OF.16 — a decline is reported as the person's, not as a failure");
// «Marta can’t this time» is the board's sentence. It matters that it is not «Request declined»:
// one is a person who is busy, the other reads as a verdict on the user.
check("the declined line exists",
  /can’t this time/.test(code) && /не сможет в этот раз/.test(code),
  (code.match(/.{0,50}can’t this time.{0,20}/) || [])[0]);
check("the sender is not shown a bare «Отказ:»", !code.includes("'Отказ: '"));
check("and the follow-up points somewhere instead of at a dead end",
  /It happens\. Below is who else fits\./.test(code));

console.log("\n" + (fails ? "FAILED: " + fails : "all board-copy checks passed"));
process.exit(fails ? 1 : 0);
