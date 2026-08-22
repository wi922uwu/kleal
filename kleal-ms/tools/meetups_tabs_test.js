// My Active Meetups — the four tabs, tested without a browser.
//
//   node tools/meetups_tabs_test.js services/profile/app.py
//
// scr_intents() returns an HTML string, so the whole screen is testable as a pure function once the
// handful of helpers it calls are stubbed. The point of these assertions is that every badge is
// DERIVED from server state: `launched`, `candidates`, the request status machine and `expires_at`.
// A card must never claim more than those four facts support — "Confirmed" on a plan with no place,
// or "3 options" on a search that has not run, is the class of lie this file exists to catch.
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

// --- the environment the screen expects -------------------------------------------------------
let UILANG = "ru";
let MTAB = "intents", ARCHTAB = "all";
let REQS = [], DATA = { name: "Me", intents: [] };
let _intT = 1, _reqT = 1;                       // loaders already ran; do not let them wipe fixtures
const NOT_ACCEPTED = ["declined", "expired", "withdrawn", "policy_revoked"];
const T = (ru, en) => (UILANG === "ru" ? ru : en);
const esc = x => String(x == null ? "" : x);
const locStr = x => String(x || "");
const locTopic = x => x;
const IC = { calen: "<svg/>", pin: "<svg/>", clock: "<svg/>", check: "<svg/>", spark: "<svg/>",
             edit: "<svg/>", chat: "<svg/>", photo: "<svg/>" };
const intentTile = () => '<div class="itile"></div>';
const loadIntents = () => {}, loadRequests = () => {};
const reqStatusLabel = st => ({ accepted: "подтверждена", declined: "не принято", expired: "истекло",
                                withdrawn: "отозвано", policy_revoked: "отменено настройками" }[st] || "в архиве");

eval(grab("plural"));
eval(grab("mtabCounts"));
eval(grab("replyBy"));
eval(grab("mAvatars"));
eval(grab("mWhen"));
eval(grab("mWhere"));
eval(grab("mCard"));
eval(grab("scr_intents"));

let fails = 0;
const check = (n, c, d) => { if (!c) fails++; console.log((c ? "  ok    " : "  FAIL  ") + n + (d !== undefined ? "   " + JSON.stringify(d) : "")); };
const html = () => scr_intents();
const titles = h => (h.match(/<div class="tl">([^<]*)<\/div>/g) || []).map(x => x.replace(/<[^>]*>/g, ""));
const badges = h => { const out = [], re = /<span class="bdg [^"]*">(?:<svg\/>)?([^<]*)</g;
                      let m; while ((m = re.exec(h))) out.push(m[1].trim()); return out; };

const ME = "Me";
DATA = { name: ME, intents: [
  { id: "i1", title: "Rooftop party", launched: true, candidates: [], intent: { time: "Sat 9 PM", place: "Gràcia" } },
  { id: "i2", title: "BBQ", launched: true, candidates: [{ name: "Ann" }, { name: "Bo" }, { name: "Cy" }], intent: {} },
  { id: "i3", title: "Chess", launched: false, candidates: [], intent: {} },
  { id: "i4", title: "Dali show", launched: true, candidates: [], intent: {} }
] };
REQS = [
  { id: "w1", from: ME, to: "Sal", status: "pending", intent: { title: "Dali show" } },
  { id: "w2", from: ME, to: "Pau", status: "pending", intent: { title: "Dali show" } },
  { id: "p1", from: "Ann", to: ME, status: "accepted", intent: { title: "Coffee with Ann", time: "Flexible", place: "" } },
  { id: "p2", from: "Mia", to: ME, status: "accepted", intent: { title: "Sunset walk", time: "Sat 9 PM", place: "Mallorca 401" } },
  { id: "v1", from: "Jane", to: ME, status: "pending", expires_at: 1785200000, intent: { title: "Champagne" } },
  { id: "a1", from: "Saly", to: ME, status: "archived", intent: { title: "Coffee with Saly" } },
  { id: "a2", from: ME, to: "Pep", status: "expired", intent: { title: "Practice Spanish" } },
  { id: "a3", from: ME, to: "Leo", status: "declined", intent: { title: "Chess in the park" } }
];

console.log("1. MY INTENTS — the badge is derived, never decorative");
MTAB = "intents";
let h = html(), b = badges(h);
check("a launched search with nobody yet reads as Searching", b[0] === "Ищу", b);
check("candidates are counted, and counted in Russian", b[1] === "3 варианта", b);
check("a search that never ran does NOT claim to be searching", b[2] === "Поиск не начат", b);
check("pending proposals of MINE become «waiting for N replies»", b[3] === "Жду 2 ответа", b);
check("all four intents are shown", titles(h).length === 4, titles(h));
check("the composer is always reachable from this tab", /data-act="createintent"/.test(h));

console.log("\n2. PLANS — Confirmed only when the when AND the where are settled");
MTAB = "plans"; h = html(); b = badges(h);
check("a plan with no place is still forming", b[0] === "План собирается", b);
check("a plan with both is confirmed", b[1] === "Подтверждено", b);
check("the other person is named, not me",
      /Coffee with Ann/.test(h) && titles(h).indexOf("Me") < 0, titles(h));

console.log("\n3. INVITES — only what is waiting on ME, with a real deadline");
MTAB = "invites"; h = html();
check("my own outgoing proposals are NOT invites", !/Dali show/.test(h), titles(h));
check("only the inbox request is shown", titles(h).length === 1 && /Champagne/.test(h), titles(h));
check("the deadline comes from expires_at", /Ответить до \d\d:\d\d/.test(h), badges(h));
const noTtl = REQS.filter(r => r.id !== "v1").concat([{ id: "v2", from: "Zoe", to: ME, status: "pending", intent: { title: "Walk" } }]);
const keep = REQS; REQS = noTtl; h = html();
check("no expiry means no invented deadline", !/Ответить до/.test(h) && /Ждёт ответа/.test(h), badges(h));
REQS = keep;

console.log("\n4. ARCHIVE — filtered by HOW it ended");
MTAB = "archive";
ARCHTAB = "all"; h = html();
check("All shows every terminal state", titles(h).length === 3, titles(h));
ARCHTAB = "completed"; h = html();
check("Completed = the ones archived by hand", titles(h).join() === "Coffee with Saly", titles(h));
check("a finished meetup offers the conversation, not a dead feedback button",
      /Написать/.test(h) && !/Leave Feedback|Оставить отзыв/.test(h));
ARCHTAB = "expired"; h = html();
check("Expired is its own filter", titles(h).join() === "Practice Spanish", titles(h));
check("a lapsed request offers to try again", /Создать похожий/.test(h));
ARCHTAB = "declined"; h = html();
check("Declined groups declined/withdrawn/revoked", titles(h).join() === "Chess in the park", titles(h));
ARCHTAB = "all";

console.log("\n5. EMPTY STATES say what to do next, and never pretend");
DATA.intents = []; MTAB = "intents"; h = html();
check("no intents -> the Figma empty state", /No active Intents yet|Активных интентов пока нет/.test(h));
check("and the way out of it", /data-act="createintent"/.test(h));
REQS = []; MTAB = "plans"; h = html();
check("no plans -> honest empty", /Планов пока нет/.test(h) && !/mcard/.test(h));
MTAB = "invites"; h = html();
check("no invites -> honest empty", /Приглашений нет/.test(h));
MTAB = "archive"; h = html();
check("empty archive -> honest empty", /Здесь пусто/.test(h));

console.log("\n6. TAB BAR");
DATA.intents = [{ id: "x", title: "t", intent: {} }];
REQS = [{ id: "v", from: "Jane", to: ME, status: "pending", intent: {} },
        { id: "v2", from: "Bob", to: ME, status: "pending", intent: {} }];
MTAB = "intents"; h = html();
check("only Invites carries a count, and it is the inbox size", (h.match(/<span class="n">2<\/span>/g) || []).length === 1, h.match(/class="n">\d+/g));
check("every tab is reachable", (h.match(/data-act="mtab"/g) || []).length === 4);

console.log("\n" + (fails ? "FAILED " + fails : "ALL PASS"));
process.exit(fails ? 1 : 0);
