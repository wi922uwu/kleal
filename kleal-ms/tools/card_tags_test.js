// candTags() must lead with what actually matched.
//
//   node tools/card_tags_test.js services/profile/app.py
//
// Reproduces the exact cards from the report: a card reading «общее: football» whose chips were
// birdwatching / шахматы / castellano — the matched interest was not on the card at all, so a
// correct ranking looked random. The function is pulled out of the live page source, so the test
// cannot pass against a file where it was renamed or removed.
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
}
let FLOW = { intent: { topics: ["beer", "football", "playstation"] } };
eval(grab("candTags"));

let fails = 0;
const check = (n, c, d) => { if (!c) fails++; console.log((c ? "  ok    " : "  FAIL  ") + n + (d !== undefined ? "   " + JSON.stringify(d) : "")); };

console.log("the four cards from the report");

// Pablo: summary said «общее: football», chips showed none of it
const pablo = { name: "Pablo Horvat",
  interests: ["birdwatching", "шахматы", "castellano", "football"],
  reasons_ru: ["общее: football", "рядом (0.7 km)"] };
let t = candTags(pablo, 3);
check("Pablo leads with football, not birdwatching", t[0] === "football", t);

// Erik: «общее: football, soccer» — two matched tokens, neither was shown
const erik = { name: "Erik Ferrer",
  interests: ["language cafes", "labubu", "фотография", "football", "soccer"],
  reasons_ru: ["общее: football, soccer", "совпали условия (complementary)"] };
t = candTags(erik, 3);
check("Erik leads with both matched tokens", t[0] === "football" && t[1] === "soccer", t);

// Mia: her own wording was shown, but second
const mia = { name: "Mia Melnyk",
  interests: ["trail running", "крафтовое пиво", "techno", "craftbeer"],
  reasons_ru: ["общее: craftbeer", "открыт(а) к встрече сейчас"] };
t = candTags(mia, 3);
check("Mia leads with the beer, not trail running", /пиво|craftbeer/.test(t[0]), t);

// Guillem: already correct — must not regress
const guillem = { name: "Guillem Moretti",
  interests: ["beer", "longboard", "tapas"],
  reasons_ru: ["общее: beer", "открыт(а) к встрече сейчас"] };
t = candTags(guillem, 3);
check("Guillem still leads with beer", t[0] === "beer", t);

console.log("\nproperties");
check("always returns at most n", candTags(erik, 2).length === 2, candTags(erik, 2));
check("non-matching interests are kept, just after",
      candTags(pablo, 4).length === 4 && candTags(pablo, 4).indexOf("шахматы") > 0, candTags(pablo, 4));

const dup = { interests: ["watercolour", "watercolor", "gym"], reasons_ru: [] };
check("spelling variants do not both eat a slot", candTags(dup, 3).length === 2, candTags(dup, 3));
check("the person's own spelling is the one kept", candTags(dup, 3)[0] === "watercolour", candTags(dup, 3));
// ...but genuinely different short interests must NOT be merged
const near = { interests: ["beer", "bear", "chess", "chest"], reasons_ru: [] };
check("short lookalikes are left alone", candTags(near, 4).length === 4, candTags(near, 4));
const long = { interests: ["bouldering", "boulderin"], reasons_ru: [] };
check("a one-letter difference on a long word IS merged", candTags(long, 2).length === 1, candTags(long, 2));

const noReason = { interests: ["gym", "football", "chess"], reasons_ru: [] };
check("falls back to the requested topics when the card gives no reason",
      candTags(noReason, 3)[0] === "football", candTags(noReason, 3));

const nothing = { interests: ["gym", "chess"], reasons_ru: ["рядом (1 km)"] };
FLOW = { intent: { topics: ["opera"] } };
check("nothing matched -> original order, no crash",
      JSON.stringify(candTags(nothing, 3)) === JSON.stringify(["gym", "chess"]), candTags(nothing, 3));
check("an empty card does not throw", JSON.stringify(candTags({}, 3)) === "[]", candTags({}, 3));

console.log("\n" + (fails ? "FAILED " + fails : "ALL PASS"));
process.exit(fails ? 1 : 0);
