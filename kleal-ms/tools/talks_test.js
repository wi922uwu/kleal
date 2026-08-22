// Regression cover for «Открыть историю разговоров».
//
//   node tools/talks_test.js services/profile/app.py
//
// The button called flowStart(''), which runs flowInit() and therefore sets FLOW.msgs = []. It did
// not open a history — it DESTROYED the conversation and dropped you into an empty composer. And
// there was nothing to open in the first place: FLOW is not part of the persisted state (saveState
// writes DATA and UI), and buddy only keeps a server-side thread for THIN clients, while the
// profile UI posts the whole thread on each turn and buddy stores none of it.
//
// The functions are pulled out of the real page source, so this cannot pass against a file where
// the persistence was dropped or the button was rewired back to flowStart.
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
function grabConst(prefix) {
  const i = src.indexOf(prefix);
  if (i < 0) throw new Error("not found: " + prefix);
  return src.slice(i, src.indexOf("\n", i));
}

let DATA = {}, FLOW = null, cur = null, saved = 0, toasted = null;
const T = (ru, en) => ru;
const esc = (x) => String(x == null ? "" : x);
const IC = { chat: "", chevR: "" };
const saveState = () => { saved++; };
const render = () => {};
const toast = (m) => { toasted = m; };
const emptyState = (a, b) => "<empty>" + a + "</empty>";

// `const` declared inside a direct eval stays inside it, so the eval'd functions below would not
// see the caps. Dropping the keyword makes them ordinary globals the whole harness shares.
eval(grabConst("const TALK_MAX=").replace("const ", ""));
eval(grab("flowInit"));
eval(grab("talkPrune"));
eval(grab("talkSave"));
eval(grab("flowPush"));
eval(grab("talkOpen"));
eval(grab("talkWhen"));
eval(grab("scr_talks"));

let fails = 0;
function check(name, cond, detail) {
  if (!cond) fails++;
  console.log((cond ? "  ok    " : "  FAIL  ") + name + (detail !== undefined ? "   " + JSON.stringify(detail) : ""));
}

console.log("1. THE BUG: the button must not be wired to flowStart");
const handler = (src.match(/case 'talk-buddy':[^\n]*/) || [""])[0];
check("«talk-buddy» no longer starts a blank flow", !/flowStart/.test(handler), handler.trim());
check("it navigates to the history screen", /talks/.test(handler), handler.trim());
check("a talks screen is registered", /talks:scr_talks/.test(src));
check("it has an app-bar title", /talks:T\('История разговоров'/.test(src));
check("and a back destination", /talks:'agenthome'/.test(src));

console.log("\n2. a conversation is actually kept");
DATA = {}; flowInit("", "buddy");
flowPush({ who: "me", text: "хочу поиграть в падел", t: Date.now() });
flowPush({ who: "ag", text: "Когда удобно?", t: Date.now() });
check("one conversation is stored", (DATA.talks || []).length === 1, (DATA.talks || []).length);
check("both turns are in it", DATA.talks[0].msgs.length === 2, DATA.talks[0].msgs.length);
check("it is titled by what the PERSON said, not the agent",
      DATA.talks[0].title === "хочу поиграть в падел", DATA.talks[0].title);
check("saving the state was requested", saved > 0, saved);

console.log("\n3. more turns extend the SAME conversation, they do not fork it");
flowPush({ who: "me", text: "в субботу", t: Date.now() });
check("still one conversation", DATA.talks.length === 1, DATA.talks.length);
check("now three turns", DATA.talks[0].msgs.length === 3, DATA.talks[0].msgs.length);

console.log("\n4. a NEW conversation is a new entry");
flowInit("", "buddy");
flowPush({ who: "me", text: "что такое облигации", t: Date.now() });
check("two conversations", DATA.talks.length === 2, DATA.talks.map(t => t.title));
check("newest first", DATA.talks[0].title === "что такое облигации", DATA.talks[0].title);

console.log("\n5. reopening restores the transcript and keeps continuing it");
const old = DATA.talks.find(t => t.title === "хочу поиграть в падел");
talkOpen(old.id);
check("the screen is the composer", cur === "reqcomposer", cur);
check("the messages came back", FLOW.msgs.length === 3, FLOW.msgs.length);
check("it continues the same record", FLOW.tid === old.id, [FLOW.tid, old.id]);
flowPush({ who: "ag", text: "ок", t: Date.now() });
check("no fork after reopening", DATA.talks.length === 2, DATA.talks.map(t => t.title));

console.log("\n6. an opener alone must not create an empty entry");
DATA = {}; flowInit("", "intent");
FLOW.msgs = [{ who: "ag", text: "Давай соберём интент.", t: Date.now() }];   // intentStart does exactly this
talkSave();
check("the agent's greeting alone is stored but not titled as a person's",
      (DATA.talks || []).length === 1 && DATA.talks[0].title === "Разговор", DATA.talks && DATA.talks[0]);
DATA = {}; FLOW.msgs = [];
talkSave();
check("nothing at all is stored for an empty conversation", !(DATA.talks || []).length, DATA.talks);

console.log("\n7. bounded — DATA rides into localStorage whole, so this must not grow");
DATA = {};
for (let i = 0; i < TALK_MAX + 12; i++) {
  flowInit("", "buddy");
  flowPush({ who: "me", text: "разговор " + i, t: Date.now() + i });
}
check("kept at the cap", DATA.talks.length === TALK_MAX, DATA.talks.length);
check("the cap drops the OLDEST", DATA.talks.every(t => t.title !== "разговор 0"), DATA.talks.length);
flowInit("", "buddy");
for (let i = 0; i < TALK_MAX_MSGS + 30; i++) flowPush({ who: "me", text: "m" + i, t: Date.now() + i });
check("a long transcript is trimmed", DATA.talks[0].msgs.length === TALK_MAX_MSGS, DATA.talks[0].msgs.length);
check("the trim keeps the LATEST turns",
      DATA.talks[0].msgs[DATA.talks[0].msgs.length - 1].text === "m" + (TALK_MAX_MSGS + 29),
      DATA.talks[0].msgs[DATA.talks[0].msgs.length - 1].text);

console.log("\n8. stale entries expire, and a dead link says so instead of doing nothing");
DATA = { talks: [{ id: "old", t: Date.now() - 40 * 864e5, msgs: [{ who: "me", text: "x" }], title: "x" }] };
check("a 40-day-old conversation is gone", talkPrune().length === 0, talkPrune().length);
toasted = null; talkOpen("nope");
check("opening a missing conversation explains itself", !!toasted, toasted);

console.log("\n9. the empty screen offers a way out");
DATA = {};
const empty = scr_talks();
check("empty state is shown", /<empty>/.test(empty));
check("and a button to start talking", /data-act="talk-new"/.test(empty));

console.log(fails ? "\n" + fails + " FAILED" : "\nALL PASS");
process.exit(fails ? 1 : 0);
