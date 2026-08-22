// Regression cover for the group-size dial — the third screen whose answer never left the screen.
//
//   node tools/gsize_test.js services/profile/app.py
//
// Same shape as the age and sex bugs, and found the same way. scr_gsize() asks «Один на один /
// Малая группа / Компания», stores the answer in FLOW.gsize, and it was read in exactly two places:
// a summary sentence and a review row. flowIntent() — the function that builds the request actually
// sent to matching — never looked at it. Matching routes to §15 group formation on `groupSize`, and
// nothing in the product ever set that field, so choosing «Малая группа» searched for one person,
// byte-identically to choosing 1:1. Groups could not be reached from the app at all.
//
// flowIntent() is pulled out of the real page source, so this cannot pass against a file where the
// mapping was removed or renamed.
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");

function grab(name) {
  const i = src.indexOf("function " + name + "(");
  if (i < 0) throw new Error("not found: " + name);
  let d = 0, started = false;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") { d++; started = true; }
    else if (src[j] === "}") { d--; if (started && d === 0) return src.slice(i, j + 1); }
  }
  throw new Error("unbalanced: " + name);
}

let FLOW = {};
const T = (ru, en) => ru;
const labelOf = () => "Gràcia";
const DIST_OPTS = () => [];
const flowOnline = () => false;
eval(src.slice(src.indexOf("const GSIZE_ALIAS="), src.indexOf("function gsizeOf(")).replace("const ", ""));
eval(grab("gsizeOf"));
eval(src.match(/const GROUP_MIN_TOTAL=\d+;/)[0].replace("const ", ""));
eval(grab("ageRange"));
eval(grab("flowIntent"));

let fails = 0;
function check(name, cond, detail) {
  if (!cond) fails++;
  console.log((cond ? "  ok    " : "  FAIL  ") + name + (detail !== undefined ? "   " + JSON.stringify(detail) : ""));
}

console.log("1. THE BUG: the size question is answered and the request forgets it");
FLOW = { intent: { topics: ["padel"] }, gsize: "group" };
const group = flowIntent();
check("«Группа» reaches the request as a size", group.groupSize >= 3, group.groupSize);
check("and that size is the product's floor of three", group.groupSize === GROUP_MIN_TOTAL, group.groupSize);

console.log("\n1b. the middle bucket is gone — a pair is not a small group");
const opts = src.slice(src.indexOf("const SIZE_OPTS="), src.indexOf("function chRows("));
check("the screen offers exactly two answers", (opts.match(/\['[^']+',/g) || []).length === 2, opts.match(/\['[^']+',/g));
check("«Малая группа» is no longer offered", !/Малая группа/.test(opts));
check("the group option says three or more", /От 3 человек/.test(opts));
FLOW = { intent: {}, gsize: "party" };
check("an old «party» answer still reads as a group", flowIntent().groupSize === GROUP_MIN_TOTAL, flowIntent().groupSize);
FLOW = { intent: {}, gsize: "small" };
check("an old «small» answer is NOT promoted — it may have meant a pair",
      flowIntent().groupSize === undefined, flowIntent().groupSize);

console.log("\n2. 1:1 must NOT become a group");
// groupSize is what routes an intent to §15; sending one for a one-on-one would push a person who
// asked to meet ONE person down the group-formation path.
FLOW = { intent: { topics: ["coffee"] }, gsize: "1:1" };
check("one-on-one carries no groupSize", flowIntent().groupSize === undefined, flowIntent().groupSize);

console.log("\n3. an unanswered question imposes nothing");
FLOW = { intent: { topics: ["coffee"] } };
check("no answer, no groupSize", flowIntent().groupSize === undefined, flowIntent().groupSize);
FLOW = { intent: { topics: ["coffee"] }, gsize: "" };
check("an empty answer, no groupSize", flowIntent().groupSize === undefined, flowIntent().groupSize);

console.log("\n4. the size stays inside the band the engine can serve");
// Floor is spec §1 (three total, the asker included); the ceiling is kleal_groups._MAX_MVP_SIZE = 12
// SEATS, i.e. 13 people. Not to be confused with core_v2.TOP_N = 8, which is how many people a 1:1
// search returns and says nothing about how large a company may be.
FLOW = { intent: {}, gsize: "group" };
const n = flowIntent().groupSize;
check("«Группа» asks for a size the engine can serve (3..13)", n >= 3 && n <= 13, n);

console.log("\n5. the size does not disturb the rest of the intent");
FLOW = { intent: { topics: ["padel"], mode: "offline" }, gsize: "group", ageA: 25, ageB: 35, sex: "female" };
const full = flowIntent();
check("age still carried", full.minAge === 25 && full.maxAge === 35, [full.minAge, full.maxAge]);
check("sex still carried", full.sex === "female", full.sex);
check("topics still carried", JSON.stringify(full.topics) === '["padel"]', full.topics);
check("and the size alongside them", full.groupSize > 1, full.groupSize);

console.log(fails ? "\n" + fails + " FAILED" : "\nALL PASS");
process.exit(fails ? 1 : 0);
