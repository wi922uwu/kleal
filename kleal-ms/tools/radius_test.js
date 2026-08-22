// Regression cover for the distance dial — the fourth screen whose answer never left the screen.
//
//   node tools/radius_test.js services/profile/app.py
//
// Same shape as the age, sex and group-size bugs, and found the same way. OF.09 asks «How far are
// you happy to go?», the slider writes FLOW.dkm, and it was read in exactly four places: three
// labels and a map circle. flowIntent() — the function that builds the request actually sent to
// matching — never looked at it.
//
// This one has teeth, because radiusKm is a HARD gate on the other side:
//
//     if intent.get('mode') == 'offline' and intent.get('radiusKm') and c.get('km') is not None:
//         if float(c['km']) > float(intent['radiusKm']):  return False, 'outside the radius'
//
// and the default is 15. So a person who dragged the slider down to 3 km was still shown people
// fifteen kilometres away, and a person who dragged it up to 40 never saw past fifteen. The dial
// was not merely ignored — it was overruled by a number nobody chose.
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

console.log("1. THE BUG: the distance is chosen and the request forgets it");
FLOW = { intent: { topics: ["coffee"] }, district: "gracia", dkm: 3 };
const near = flowIntent();
check("3 km reaches the request", near.radiusKm === 3, near.radiusKm);
FLOW = { intent: { topics: ["coffee"] }, district: "gracia", dkm: 40 };
check("so does 40 km — the dial is not clamped to the old default", flowIntent().radiusKm === 40);

console.log("\n2. Untouched dial keeps the previous behaviour");
FLOW = { intent: { topics: ["coffee"] }, district: "gracia" };
const untouched = flowIntent();
check("no slider, no radius invented in the request", untouched.radiusKm === undefined, untouched.radiusKm);
FLOW = { intent: { topics: ["coffee"], radiusKm: 12 }, district: "gracia" };
check("a radius already on the intent survives", flowIntent().radiusKm === 12);

console.log("\n3. The expansion ladder still widens what you chose, not what you didn't");
FLOW = { intent: { topics: ["coffee"] }, district: "gracia", dkm: 5, adjust: "radius" };
check("«шире» adds to YOUR 5, not to the 15 default", flowIntent().radiusKm === 10, flowIntent().radiusKm);
FLOW = { intent: { topics: ["coffee"] }, district: "gracia", dkm: 5, adjust: "wide" };
const wide = flowIntent();
check("«намного шире» adds 15 to your 5", wide.radiusKm === 20, wide.radiusKm);
check("and still asks for consent to go broad", wide.broadConsent === true);
FLOW = { intent: { topics: ["coffee"] }, district: "gracia", adjust: "radius" };
check("without a slider the ladder still starts from 15", flowIntent().radiusKm === 20, flowIntent().radiusKm);

console.log("\n4. Online has no radius at all");
FLOW = { intent: { topics: ["coffee"], mode: "online" }, district: "gracia", dkm: 3 };
const online = flowIntent();
check("an online meetup sends no radius", online.radiusKm === undefined, online.radiusKm);
check("and no district", online.place === "Онлайн", online.place);

console.log("\n5. Zero is a real answer, not a missing one");
FLOW = { intent: { topics: ["coffee"] }, district: "gracia", dkm: 0 };
check("0 km survives the null check", flowIntent().radiusKm === 0, flowIntent().radiusKm);

console.log("\n" + (fails ? "FAILED: " + fails : "all radius checks passed"));
process.exit(fails ? 1 : 0);
