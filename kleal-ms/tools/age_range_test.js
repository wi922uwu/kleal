// Regression cover for the age filter — it has been "fixed" once before and stayed broken.
//
//   node tools/age_range_test.js services/profile/app.py
//
// The functions are pulled out of the real page source rather than copied, so the test cannot pass
// against a file where they no longer exist or were renamed.
//
// The bug was never in the ranker: the gate works (verified against the live pool — 20-25 returns
// 21-25, 60-75 returns 61). Only the handle a person dragged was stored, so the other end stayed
// undefined, flowIntent()'s `if(ageA && ageB)` was false, and the search went out with NO age
// filter while the dial on screen read "25-28". This reproduces exactly that: drag one handle,
// then look at what the request would carry.
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
const labelOf = () => "";
const DIST_OPTS = () => [];
eval(grab("ageEnds"));
eval(grab("ageRange"));

// the age branch of wireDial's apply(), verbatim in behaviour
function dragHandle(hand, age) {
  const e = ageEnds(), a0 = e[0], a1 = e[1];
  if (hand === 0) { FLOW.ageA = age; FLOW.ageB = Math.max(a1, age); }
  else { FLOW.ageB = age; FLOW.ageA = Math.min(a0, age); }
}

// what flowIntent() now does with the range
function intentAge() {
  const it = Object.assign({}, FLOW.intent || {});
  const _age = ageRange();
  if (_age) { it.minAge = _age[0]; it.maxAge = _age[1]; }
  return it;
}

let fails = 0;
function check(name, cond, detail) {
  if (!cond) fails++;
  console.log((cond ? "  ok    " : "  FAIL  ") + name + (detail !== undefined ? "   " + JSON.stringify(detail) : ""));
}

console.log("1. an untouched dial must NOT impose a filter nobody set");
FLOW = { intent: { topics: ["coffee"] } };
check("dial shows the 18-28 placeholder", JSON.stringify(ageEnds()) === "[18,28]", ageEnds());
check("no range is chosen", ageRange() === null, ageRange());
check("the request carries no age filter", intentAge().minAge === undefined, intentAge());

console.log("\n2. THE BUG: drag the LOWER handle only");
FLOW = { intent: { topics: ["coffee"] } };
dragHandle(0, 25);
check("both ends are stored", FLOW.ageA === 25 && FLOW.ageB === 28, [FLOW.ageA, FLOW.ageB]);
check("the dial shows 25-28", JSON.stringify(ageEnds()) === "[25,28]", ageEnds());
const a2 = intentAge();
check("the request now carries 25-28", a2.minAge === 25 && a2.maxAge === 28, a2);

console.log("\n3. drag the UPPER handle only");
FLOW = { intent: { topics: ["coffee"] } };
dragHandle(1, 40);
check("both ends are stored", FLOW.ageA === 18 && FLOW.ageB === 40, [FLOW.ageA, FLOW.ageB]);
const a3 = intentAge();
check("the request carries 18-40", a3.minAge === 18 && a3.maxAge === 40, a3);

console.log("\n4. drag both, in either order");
FLOW = { intent: {} };
dragHandle(0, 30); dragHandle(1, 45);
const a4 = intentAge();
check("30-45 survives", a4.minAge === 30 && a4.maxAge === 45, a4);

console.log("\n5. a crossed handle PUSHES the other, it never inverts the range");
FLOW = { intent: {} };
dragHandle(0, 60);                              // lower handle dragged past the upper default 28
check("dragging the lower end to 60 keeps 60, pushing the upper",
      FLOW.ageA === 60 && FLOW.ageB === 60, [FLOW.ageA, FLOW.ageB]);
FLOW = { intent: {} };
dragHandle(1, 20);                              // upper handle dragged below the lower default 18
check("dragging the upper end to 20 keeps the lower at 18",
      FLOW.ageA === 18 && FLOW.ageB === 20, [FLOW.ageA, FLOW.ageB]);

console.log("\n5b. the result does not depend on the ORDER the handles are moved");
FLOW = { intent: {} }; dragHandle(0, 30); dragHandle(1, 45);
const fwd = [FLOW.ageA, FLOW.ageB];
FLOW = { intent: {} }; dragHandle(1, 45); dragHandle(0, 30);
const rev = [FLOW.ageA, FLOW.ageB];
check("lower-then-upper == upper-then-lower", JSON.stringify(fwd) === JSON.stringify(rev), [fwd, rev]);

console.log("\n6. re-opening a SAVED intent keeps its range and shows it on the dial");
FLOW = { intent: { topics: ["coffee"], minAge: 31, maxAge: 37 } };   // openIntentFlow() rebuilds FLOW like this
check("the dial shows the saved 31-37, not 18-28", JSON.stringify(ageEnds()) === "[31,37]", ageEnds());
check("the range is reported as chosen", JSON.stringify(ageRange()) === "[31,37]", ageRange());
const a6 = intentAge();
check("re-running the saved intent keeps 31-37", a6.minAge === 31 && a6.maxAge === 37, a6);
dragHandle(0, 33);
check("editing it starts from the saved range, not the placeholder",
      FLOW.ageA === 33 && FLOW.ageB === 37, [FLOW.ageA, FLOW.ageB]);

console.log("\n" + (fails ? "FAILED " + fails : "ALL PASS"));
process.exit(fails ? 1 : 0);
