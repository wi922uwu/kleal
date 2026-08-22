// «Саммари Kleal» — the two boxes that describe a PERSON and an INTENT in words.
//
//   node tools/summary_test.js services/profile/app.py
//
// Both used to print the machine's own notes. The person box glued the ranker's reason fragments to
// a name — «Adam Weber — другие интересы — более широкий вариант.» — two dashes and no verb. The
// intent box read the request back with the parsed parts comma-spliced on: «Понял так: хочу
// поиграть в падел — вживую, в малой группе. Ищу девушек 25–30.» Both were accurate and neither
// was a sentence anyone would say.
//
// What is asserted here is what can be asserted about prose: it is grounded in the card (no fact
// appears that the data did not carry), it never invents a gender, it degrades honestly when the
// data is thin, and it reads as sentences.
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

let UILANG = "ru", FLOW = null;
const T = (ru, en) => (UILANG === "ru" ? ru : en);
const locTopic = (w) => String(w || "");
const locTopicList = (s) => String(s || "");
const locStr = (s) => String(s || "");
const labelOf = (opts, v, dash) => { const o = (opts || []).find(x => x[0] === v);
  return o ? o[1] : (dash !== undefined ? dash : T("на твоё усмотрение", "flexible")); };
const WHEN_OPTS = () => [["today", T("сегодня", "today")], ["weekend", T("в выходные", "this weekend")]];
const TIME_OPTS = () => [["evening", T("вечером", "in the evening")], ["morning", T("утром", "in the morning")]];
const DIST_OPTS = () => [["gracia", "Gràcia"]];
const dDates = () => [["d0", T("сб, 24 июня", "Sat, 24 June")]];
const intentWhen = () => "";
const flowOnline = () => !!(FLOW && FLOW.intent && FLOW.intent.mode === "online");

const ageRange = () => (FLOW && FLOW.ageA && FLOW.ageB) ? [FLOW.ageA, FLOW.ageB] : null;
// langName + its code table already existed in the page; the summary reuses them rather than
// carrying a second list that could drift.
eval(src.slice(src.indexOf("const _LANG_NAMES="), src.indexOf("function langName(")).replace("const ", ""));
eval(src.slice(src.indexOf("const GSIZE_ALIAS="), src.indexOf("function gsizeOf(")).replace("const ", ""));
eval(grab("gsizeOf"));
eval(grab("langName"));
eval(grab("candShared"));
eval(grab("human"));
eval(grab("candSummaryLine"));
eval(grab("summaryWhen"));
eval(grab("summaryWhere"));
eval(grab("intentUnderstanding"));

let fails = 0;
function check(name, cond, detail) {
  if (!cond) fails++;
  console.log((cond ? "  ok    " : "  FAIL  ") + name + (detail !== undefined ? "   " + JSON.stringify(detail) : ""));
}
const sentences = (s) => String(s).split(/(?<=[.!?])\s+/).filter(Boolean);
// The exact shape the old code produced, and the reason this file exists.
const looksMachine = (s) => /Понял так:/.test(s) ||
  sentences(s).some(x => (x.match(/ — /g) || []).length > 1 || /^[A-ZА-Я][\wА-Яа-яё]* — \S+ — /.test(x));
const GENDERED_RU = /\b(она|он|её|его|ему|ей|любит\s+она)\b/i;
const GENDERED_EN = /\b(she|he|her|his|him)\b/i;

const SARA = { name: "Сара", age: 31, band: "especially_close",
  interests: ["padel", "hiking", "wine"], reasons_ru: ["общее: padel"],
  langs: ["es", "en"], area: "Gràcia" };
const STRANGER = { name: "Адам", age: 40, band: "broader_option",
  interests: ["poker", "geocaching"], reasons_ru: ["другие интересы — более широкий вариант"] };
const BLANK = { name: "Ким", band: "needs_clarification", interests: [] };

console.log("1. a PERSON reads as sentences, not as ranker notes");
FLOW = { intent: { topics: ["padel"] } };
const a = candSummaryLine(SARA);
console.log("     " + a);
check("it is prose, not fragments glued to a name", !looksMachine(a), a);
check("at least two sentences", sentences(a).length >= 2, sentences(a).length);
check("names the shared interest", /padel/i.test(a), a);
  check("languages are named, not ISO codes", !/\bes\b|\ben\b/.test(a) && /испанском/i.test(a), a);
check("and «говорит на» gets the case it governs", !/на испанский|на английский/.test(a), a);
check("names their own interests too", /hiking|wine/i.test(a), a);
check("states the verdict in words, not only as a pill", /ближе всего/i.test(a), a);

console.log("\n2. nothing is invented — no gender the card never carried");
check("no Russian gendered pronoun", !GENDERED_RU.test(a), (a.match(GENDERED_RU) || [])[0]);
UILANG = "en";
const ae = candSummaryLine(SARA);
console.log("     " + ae);
check("no English gendered pronoun", !GENDERED_EN.test(ae), (ae.match(GENDERED_EN) || [])[0]);
check("English is prose too", !looksMachine(ae) && sentences(ae).length >= 2, ae);
UILANG = "ru";

console.log("\n3. a weak match SAYS it is weak instead of dressing up");
const b = candSummaryLine(STRANGER);
console.log("     " + b);
check("admits there is no direct overlap", /нет|шире/i.test(b), b);
check("still says what they ARE into", /poker|geocaching/i.test(b), b);
check("does not claim a shared interest", !/разделяет твой интерес/.test(b), b);

console.log("\n4. an empty profile degrades honestly");
const c = candSummaryLine(BLANK);
console.log("     " + c);
check("says the profile is thin", /пуст/i.test(c), c);
check("never renders 'undefined' or a dangling clause", !/undefined|null|—\s*$|:\s*$/.test(c), c);

console.log("\n5. a backend-written summary still wins");
check("klealSummary takes precedence",
      candSummaryLine(Object.assign({}, SARA, { klealSummary: "Написано моделью." })) === "Написано моделью.");

console.log("\n6. the INTENT box describes the plan, not the parse");
FLOW = { intent: { topics: ["padel"], mode: "offline" }, request: "хочу поиграть в падел",
         fmt: "offline", gsize: "group", date: "d0", time: "evening", district: "gracia",
         sex: "female", ageA: 25, ageB: 30, summary: {} };
const i1 = intentUnderstanding();
console.log("     " + i1);
check("the read-back preamble is gone", !/Понял так:/.test(i1), i1);
check("it says how it happens and at what size", /Вживую, компанией/.test(i1), i1);
check("it says when", /24 июня|вечером/.test(i1), i1);
check("it says where", /Gràcia/.test(i1), i1);
check("it says who it is open to", /Открыто для/.test(i1) && /25–30/.test(i1), i1);
check("three sentences", sentences(i1).length >= 3, sentences(i1).length);

console.log("\n7. an online plan has no district, and does not pretend to");
FLOW = { intent: { topics: ["dota"], mode: "online" }, request: "поиграть в доту",
         fmt: "online", gsize: "group", sex: "any", summary: {} };
const i2 = intentUnderstanding();
console.log("     " + i2);
check("says online", /Онлайн/i.test(i2), i2);
check("no place clause", !/Место|Gràcia/.test(i2), i2);
check("open to everyone when nobody was excluded", /кому это близко/.test(i2), i2);

console.log("\n8. a bare intent still produces a whole sentence");
FLOW = { intent: { topics: ["coffee"] }, request: "выпить кофе", summary: {} };
const i3 = intentUnderstanding();
console.log("     " + i3);
check("no empty clauses", !/undefined|null|:\s*\.|—\s*\./.test(i3), i3);
check("starts with a capital", /^[А-ЯA-Z]/.test(i3), i3);
check("a backend summary still wins", (FLOW.summary = { summary: "Из модели." },
      intentUnderstanding() === "Из модели."));

console.log(fails ? "\n" + fails + " FAILED" : "\nALL PASS");
process.exit(fails ? 1 : 0);
