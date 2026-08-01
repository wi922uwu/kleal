// The 1:1 meeting strip — Figma «1:1 Offline», OF.20–OF.25 and OF.C3–OF.C5.
//
//   node tools/mplan_ui_test.js services/profile/app.py
//
// Fourteen frames, one screen: the same Plan Card, the same two participant rows and the same
// two-button stack, with the copy swapped by state. So the thing worth testing is the SWITCH — that
// each server state lands on the frame the board drew for it, and that the sentence on it is the
// board's sentence and not an approximation of it.
//
// The English strings below are copied out of Figma character for character. If someone rewrites one
// in the app, this fails — which is the point: these particular sentences are the product's promise
// («nothing is cancelled», «that works both ways»), and a paraphrase quietly weakens them.
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");

let fails = 0;
function check(name, cond, detail) {
  if (!cond) fails++;
  console.log((cond ? "  ok    " : "  FAIL  ") + name + (detail !== undefined ? "   " + JSON.stringify(detail).slice(0, 170) : ""));
}
function grab(name) {
  const i = src.indexOf("function " + name + "(");
  if (i < 0) return "";
  let d = 0, started = false;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") { d++; started = true; }
    else if (src[j] === "}") { d--; if (started && d === 0) return src.slice(i, j + 1); }
  }
  return "";
}

// --- the real functions, pulled from the page source -------------------------------------------
let UILANG = "en", DATA = { name: "Dmitry" }, MPLAN = null;
const T = (ru, en) => (UILANG === "ru" ? ru : en);
const esc = (s) => String(s == null ? "" : s);
const IC = new Proxy({}, { get: () => "<svg></svg>" });
eval(grab("mpWhen"));
eval(grab("mpTime"));
eval(grab("mpMins"));
eval(grab("mpPhase"));
eval(grab("mpHead"));
eval(grab("mpWhereText"));
eval(grab("mpStatusLine"));
eval(grab("mpCTAs"));

const HOUR = 3600, NOW = () => Date.now() / 1000;
function plan(o) {
  return Object.assign({
    id: "mp_1", version: 1, state: "confirmed", title: "Coffee & AI talk", mode: "offline",
    starts_at: NOW() + 48 * HOUR, district: "Gràcia", venue: "Nømad", address: "Carrer de Verdi 12",
    address_set: true, address_visible_to_me: true, host: "Dmitry", guest: "Marta", other: "Marta",
    my_response: "confirmed", both_confirmed: true, pending: null, my_live: null, their_live: null,
    participants: [], waiting_on: [],
  }, o);
}

console.log("1. Every server state lands on the frame the board drew for it");
const cases = [
  ["OF.C3  to_confirm", plan({ state: "proposed", my_response: null }), "to_confirm"],
  ["OF.20  waiting", plan({ state: "proposed" }), "waiting"],
  ["OF.20a no_address", plan({ address_set: false, address: "", host: "Dmitry" }), "no_address"],
  ["OF.21  confirmed", plan({}), "confirmed"],
  ["OF.21b change_out", plan({ pending: { by: "Dmitry", mine: true, starts_at: NOW() + 72 * HOUR } }), "change_out"],
  ["OF.C5  change_in", plan({ pending: { by: "Marta", mine: false, starts_at: NOW() + 72 * HOUR } }), "change_in"],
  ["OF.22  soon", plan({ starts_at: NOW() + 30 * 60 }), "soon"],
  ["OF.22a my_late", plan({ starts_at: NOW() + 20 * 60, my_live: { status: "late", eta_min: 15 } }), "my_late"],
  ["OF.C4  their_late", plan({ starts_at: NOW() + 20 * 60, their_live: { status: "late", eta_min: 10 } }), "their_late"],
  ["OF.23  now", plan({ starts_at: NOW() - 60 }), "now"],
  ["OF.24  over", plan({ starts_at: NOW() - 40 * 60 }), "over"],
  ["       cancelled", plan({ state: "cancelled" }), "cancelled"],
  ["       done", plan({ state: "done" }), "done"],
];
for (const [label, p, want] of cases) check(label, mpPhase(p) === want, mpPhase(p));

console.log("\n2. A suggested time and a late arrival outrank a quiet «confirmed»");
check("a pending change wins over the countdown",
  mpPhase(plan({ starts_at: NOW() + 20 * 60, pending: { by: "Marta", mine: false, starts_at: NOW() + HOUR } })) === "change_in");
check("their delay wins over «starts soon»",
  mpPhase(plan({ starts_at: NOW() + 20 * 60, their_live: { status: "late" } })) === "their_late");
check("but a plan nobody confirmed is never «running late»",
  mpPhase(plan({ state: "proposed", my_response: null, their_live: { status: "late" } })) === "to_confirm");

console.log("\n3. The sentences are the board's, word for word");
UILANG = "en";
const BOARD = [
  ["to_confirm", plan({ state: "proposed", my_response: null }),
    "Marta sent a plan",
    "Confirm and the exact address opens for you. Until then you only see the district — that works both ways."],
  ["waiting", plan({ state: "proposed" }),
    "Sent to Marta",
    "Marta sees the district and the time. The exact address opens for them only when they confirm."],
  ["change_out", plan({ pending: { by: "Dmitry", mine: true, starts_at: NOW() + 72 * HOUR } }),
    "New time sent to Marta",
    "Marta sees the new time and confirms again. Until then the old time still stands — nothing is cancelled and nobody has to do anything."],
  ["confirmed", plan({}), "Confirmed", null],
  ["now", plan({ starts_at: NOW() - 60 }), "Your meetup is now", null],
];
for (const [label, p, title, body] of BOARD) {
  MPLAN = p;
  const [h, ex] = mpHead(p);
  check(label + " · title", h === title, h);
  if (body) check(label + " · body", ex === body, ex);
}
MPLAN = plan({ pending: { by: "Marta", mine: false, starts_at: NOW() + 72 * HOUR } });
const [ch, cex] = mpHead(MPLAN);
check("change_in · title names the suggested hour", /^Marta suggests \d\d:\d\d$/.test(ch), ch);
check("change_in · body",
  cex === "Marta wants to move it. The old time holds until you answer, so there is no rush and nothing is lost if you say no.", cex);

console.log("\n4. Nobody is given a gender the board never stated");
UILANG = "en";
for (const [, p] of cases) {
  MPLAN = p;
  const txt = mpHead(p).join(" ");
  check("no «her/his/she/he» in: " + (txt.slice(0, 34) || "(empty)"),
    !/\b(her|his|she|he|him)\b/i.test(txt), txt.slice(0, 120));
}

console.log("\n5. «Confirm and the exact address opens» is enforced, not just written");
check("no address before you confirm",
  mpWhereText(plan({ address_visible_to_me: false })) === "Gràcia · address opens when you confirm",
  mpWhereText(plan({ address_visible_to_me: false })));
check("the address appears once you have",
  mpWhereText(plan({})) === "Nømad · Carrer de Verdi 12", mpWhereText(plan({})));
check("a plan with no address yet says so, not «opens when you confirm»",
  mpWhereText(plan({ address_set: false, address: "", address_visible_to_me: false })) === "Gràcia",
  mpWhereText(plan({ address_set: false, address: "", address_visible_to_me: false })));
check("online never shows a district", mpWhereText(plan({ mode: "online" })) === "Online");

console.log("\n6. The buttons match the state");
const wantBtn = {
  to_confirm: ["mp-confirm", "mp-reschedule"],
  waiting: ["mp-chat", "mp-reschedule"],
  no_address: ["mp-address", "mp-chat"],
  confirmed: ["mp-chat", "mp-reschedule"],
  change_in: ["mp-accept-change", "mp-reject-change"],
  change_out: ["mp-chat", "mp-reject-change"],
  soon: ["mp-otw", "mp-late"],
  my_late: ["mp-here", "mp-chat"],
  their_late: ["mp-here", "mp-chat"],
  now: ["mp-here", "mp-chat"],
  over: ["mp-happened", "mp-nothappened"],
};
for (const [label, p, ph] of cases) {
  if (!wantBtn[ph]) continue;
  const acts = [...mpCTAs(p).matchAll(/data-act="([\w-]+)"/g)].map((m) => m[1]);
  check(ph + " -> " + wantBtn[ph].join(" + "), JSON.stringify(acts) === JSON.stringify(wantBtn[ph]), acts);
}
check("a cancelled plan offers only the chat",
  [...mpCTAs(plan({ state: "cancelled" })).matchAll(/data-act="([\w-]+)"/g)].map((m) => m[1]).join() === "mp-chat");

console.log("\n7. Participant status: colour carries meaning");
check("confirmed is green", mpStatusLine({ confirmed: true }, plan({}))[1] === "ok");
check("your turn is neutral", mpStatusLine({ is_me: true, confirmed: false }, plan({}))[1] === "");
check("late is a warning", mpStatusLine({ live: { status: "late", eta_min: 15 } }, plan({}))[1] === "late");
check("and says how late", mpStatusLine({ live: { status: "late", eta_min: 15 } }, plan({}))[0] === "Running late by 15 min");
check("here is green", mpStatusLine({ live: { status: "here" } }, plan({}))[1] === "ok");

console.log("\n8. Russian is written, not machine-translated from the English");
UILANG = "ru";
for (const [label, p] of cases) {
  MPLAN = p;
  const txt = mpHead(p).join(" ").trim();
  if (!txt) continue;
  check("ru copy exists for " + mpPhase(p), /[а-яё]/i.test(txt), txt.slice(0, 90));
}
MPLAN = plan({ state: "proposed", my_response: null });
check("«прислал» avoided — Russian past tense would guess a gender",
  !/прислал|отправил|сказал|подтвердил\b/.test(mpHead(MPLAN).join(" ")), mpHead(MPLAN)[0]);

console.log("\n9. Russian never puts a Latin name in an oblique case");
// The server hands over a name it cannot decline, so «Отправлено Marta» (wants the dative «Марте») and
// «У Marta есть адрес» (wants the genitive «У Марты») are both broken Russian. Every RU string has to
// keep the name nominative — as a label after a colon, or as the subject. These four slipped through
// a green test suite once already; they are only visible by reading the sentence.
UILANG = "ru";
const OBLIQUE = [
  [/(^|[^:])\bОтправлено\s+\{?o/, "«Отправлено <имя>» — нужен дательный"],
  [/\bУ\s*'\s*\+\s*o/, "«У <имя>» — нужен родительный"],
  [/скажи\s*'\s*\+\s*o/, "«скажи <имя>» — нужен дательный"],
  [/отправлено\s*'\s*\+\s*o/, "«отправлено <имя>» — нужен дательный"],
];
const headSrc = grab("mpHead");
for (const [re, why] of OBLIQUE) check("не осталось: " + why, !re.test(headSrc));
check("«виден», а не «видим»", !/Ответ видим/.test(src), "Ответ видим");
for (const [, p] of cases) {
  MPLAN = p;
  const txt = mpHead(p).join(" ");
  check("нет падежной ошибки в: " + (txt.slice(0, 30) || "(пусто)"),
    !/(^|\s)(У|скажи|Отправлено|отправлено)\s+[A-Z][a-z]+/.test(txt), txt.slice(0, 110));
}
// The board says THEY wait at the same place. An earlier Russian pass told the user to wait instead —
// a green test and the opposite instruction.
MPLAN = plan({ starts_at: NOW() + 30 * 60 });
check("«опаздываешь» не превращается в «подожди сам»",
  !/подожди на том же месте/.test(mpHead(MPLAN)[1]), mpHead(MPLAN)[1]);
check("и говорит, что ждать будут тебя", /подождёт/.test(mpHead(MPLAN)[1]), mpHead(MPLAN)[1]);
UILANG = "en";

console.log("\n10. Both hours must be on screen at once");
// The heading names the suggested hour and the card kept the agreed one. If the card does not also
// carry the suggestion, the two never appear together — and «the old time holds until you answer»
// asks the person to compare something they cannot see side by side.
eval(grab("mpCard"));
UILANG = "en";
const pend = plan({ pending: { by: "Marta", mine: false, starts_at: NOW() + 72 * HOUR } });
const cardHtml = mpCard(pend);
check("the agreed time is still on the card", cardHtml.includes(mpWhen(pend.starts_at)));
check("and the suggested one is too", cardHtml.includes("Suggested: " + mpWhen(pend.pending.starts_at)),
  cardHtml.slice(cardHtml.indexOf("Suggested"), cardHtml.indexOf("Suggested") + 60));
check("a plan with no suggestion has no extra row", !mpCard(plan({})).includes("Suggested:"));

console.log("\n11. Wiring");
check("the screen is registered", /mplan:scr_mplan/.test(src));
check("plans are polled, so the other side's move arrives", /loadMplans\(\)/.test(src));
check("actions send the version, so a stale screen cannot overwrite", /version:MPLAN\.version/.test(src));
check("every action repaints from the server's answer, not a guess",
  /if\(r&&r\.ok&&r\.plan\)\{ MPLAN=r\.plan/.test(src));
check("refusals are named for the user", /VERSION_CONFLICT:/.test(src) && /NOT_CONFIRMED:/.test(src));

console.log("\n" + (fails ? "FAILED: " + fails : "all meeting-strip checks passed"));
process.exit(fails ? 1 : 0);
