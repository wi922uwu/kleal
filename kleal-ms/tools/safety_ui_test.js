// The two controls on OF.13b that used to lie.
//
//   node tools/safety_ui_test.js services/profile/app.py
//
// «Заблокировать» removed the person from a local array and said «Заблокировано». «Пожаловаться»
// said «Спасибо. Центр безопасности посмотрит.» Neither sent a byte. The next /match rebuilt that
// array from the server with the blocked person back in it, and no report existed anywhere.
//
// A cheerful toast over a failed request is worse here than no button at all: the person believes
// they are protected and they are not. So this checks three things — that the calls exist, that they
// carry a reason, and that the message the user reads depends on whether the call actually worked.
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");

let fails = 0;
function check(name, cond, detail) {
  if (!cond) fails++;
  console.log((cond ? "  ok    " : "  FAIL  ") + name + (detail !== undefined ? "   " + JSON.stringify(detail).slice(0, 160) : ""));
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

console.log("1. The buttons reach the server at all");
const call = grab("safetyCall");
check("safetyCall exists", call.length > 0);
check("it sends who is doing the blocking", /self\s*:\s*me/.test(call), call.slice(0, 200));
check("it is idempotent, so a double tap is one block", /idem\s*:/.test(call));
check("and it reports failure instead of swallowing it", /return\s+false/.test(call));

const act = src.slice(src.indexOf("function doAct("));
const blockCase = act.slice(act.indexOf("case 'cand-block'"), act.indexOf("case 'cand-block'") + 500);
check("block posts to /api/agent/block", /\/api\/agent\/block/.test(blockCase), blockCase.slice(0, 160));
check("block sends on:true, so unblocking is the same route", /on\s*:\s*true/.test(blockCase));

const sendCase = act.slice(act.indexOf("case 'cand-report-send'"), act.indexOf("case 'cand-report-send'") + 500);
check("report posts to /api/agent/report", /\/api\/agent\/report/.test(sendCase), sendCase.slice(0, 160));
check("and carries the chosen reason", /reason\s*:\s*ds\.r/.test(sendCase));

console.log("\n2. The toast tells the truth");
for (const [label, body] of [["block", blockCase], ["report", sendCase]]) {
  check(label + ": the message depends on the result", /ok\s*\?/.test(body), body.slice(0, 200));
  check(label + ": there is a failure message", /(Не удалось|Couldn)/.test(body));
  check(label + ": it only leaves the screen on success", /if\(ok\)\s*flowBack\(\)/.test(body));
}

console.log("\n3. A report has to say what happened");
check("cand-report opens the reason sheet, it does not fire blind",
  /case 'cand-report':\s*SHEET='candreport'/.test(act));
const reasons = src.match(/const REPORT_REASONS=\[[\s\S]*?\];/);
check("the reason list exists", !!reasons);
if (reasons) {
  const keys = [...reasons[0].matchAll(/\['(\w+)',\[/g)].map(m => m[1]);
  check("six reasons, matching the server's list", keys.length === 6, keys);
  for (const k of ["harassment", "fake", "spam", "unsafe", "underage", "other"]) {
    check("  reason present: " + k, keys.includes(k));
  }
  check("every reason is bilingual", (reasons[0].match(/\['[^']*','[^']*'\]/g) || []).length >= 6);
}
const sheet = grab("candReportSheet");
check("the sheet renders one button per reason", /REPORT_REASONS\.map/.test(sheet), sheet.slice(0, 120));
check("each button carries its key", /data-r="\$\{k\}"/.test(sheet));
check("the sheet is registered in render()", /SHEET==='candreport'/.test(src));
check("and it warns that reporting also cuts contact",
  /(больше не сможет|won’t be able to reach)/.test(sheet), sheet.slice(0, 400));

console.log("\n" + (fails ? "FAILED: " + fails : "all safety-UI checks passed"));
process.exit(fails ? 1 : 0);
