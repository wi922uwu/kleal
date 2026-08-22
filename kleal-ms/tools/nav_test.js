// The floating nav bar: every button in it must actually be pressable.
//
//   node tools/nav_test.js services/profile/app.py
//
// The pill was made to float over the screens — `.bnav{position:absolute;pointer-events:none}` so
// content scrolls underneath it and only the controls take taps. `pointer-events:auto` was then put
// back on `.navpill`… and the centre button is a SIBLING of the pill, not a child of it. So the main
// action of the whole app was visible, raised, and completely dead.
//
// This reads the real stylesheet and the real bnavHTML() out of the page and checks the property for
// every element the bar renders, rather than for the one that was remembered.
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");

let fails = 0;
function check(name, cond, detail) {
  if (!cond) fails++;
  console.log((cond ? "  ok    " : "  FAIL  ") + name + (detail !== undefined ? "   " + JSON.stringify(detail) : ""));
}

// --- the markup the bar actually produces -------------------------------------------------------
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
const T = (ru) => ru;
const IC = new Proxy({}, { get: () => "<svg></svg>" });
let cur = "agenthome";
eval(grab("navFam"));
eval(grab("bnavHTML"));
const html = bnavHTML();

// classes of the bar's own direct children, and which of them are interactive
const children = [...html.matchAll(/<(?:div|span|a)\s+class="([a-z]+)"/g)].map(m => m[1]);
const interactive = [...html.matchAll(/<(?:div|a)\s+class="([a-z]+)"[^>]*data-(?:act|nav)=/g)].map(m => m[1]);

console.log("1. what the bar renders");
check("the bar has children", children.length > 0, children);
check("something in it is interactive", interactive.length > 0, interactive);
check("the centre button is one of them", interactive.includes("fab"), interactive);

// --- the stylesheet ----------------------------------------------------------------------------
console.log("\n2. the bar itself does not swallow taps meant for the screen");
const bnavRule = (src.match(/\n\.bnav\{[^}]*\}/) || [""])[0];
check(".bnav floats over the screens", /position:absolute/.test(bnavRule), bnavRule.slice(0, 70));
check(".bnav passes taps through", /pointer-events:none/.test(bnavRule), bnavRule.slice(0, 70));

console.log("\n3. ...but every control in it is still pressable");
// which selectors re-enable pointer events
const restored = new Set();
for (const m of src.matchAll(/\n([^\n{]*)\{[^}]*pointer-events:auto[^}]*\}/g)) {
  for (const sel of m[1].split(",")) {
    const cls = sel.trim().match(/\.([a-z]+)\s*$/);
    if (cls) restored.add(cls[1]);
  }
}
for (const cls of new Set(interactive)) {
  check("«." + cls + "» takes taps", restored.has(cls),
        "restored on: " + [...restored].join(", "));
}

console.log("\n4. the screens get the height back that the bar no longer occupies");
check("the bar's height is a single variable", /--navh:\s*\d+px/.test(src), (src.match(/--navh:[^;]*/) || [])[0]);
check(".bnav is sized from it", /\.bnav\{[^}]*height:var\(--navh\)/.test(src.replace(/\n/g, "")),
      bnavRule.slice(0, 120));
const bodyRule = (src.match(/\n\.body\{[^}]*\}/) || [""])[0];
check("the main scroll area reserves room for it", /padding[^;]*var\(--navh\)/.test(bodyRule),
      bodyRule.slice(0, 90));

console.log("\n5. anything modal sits ABOVE the floating pill");
// The pill only started covering things when it began to float. A bottom sheet at z-index 40 against
// a pill at 60 had its last control — «Добавить», the save row — hidden underneath it.
const zOf = (sel) => {
  const rule = (src.match(new RegExp("\\n\\" + sel + "\\{[^}]*\\}")) || [""])[0];
  const z = rule.match(/z-index:\s*([^;}]+)/);
  return z ? z[1].trim() : null;
};
const navZ = zOf(".bnav"), scrimZ = zOf(".kscrim");
check("the pill declares its layer", !!navZ, navZ);
check("the modal scrim declares its layer", !!scrimZ, scrimZ);
check("both read from the same named variables, not magic numbers",
      /var\(--z-nav\)/.test(navZ || "") && /var\(--z-modal\)/.test(scrimZ || ""), [navZ, scrimZ]);
const nums = {};
for (const m of src.matchAll(/--z-(nav|modal):\s*(\d+)/g)) nums[m[1]] = +m[2];
check("modal is above nav", nums.modal > nums.nav, nums);

console.log(fails ? "\n" + fails + " FAILED" : "\nALL PASS");
process.exit(fails ? 1 : 0);
