// One section, one editor.
//
//   node tools/profile_rows_test.js services/profile/app.py
//
// Each hub card on the profile carries two tap targets: the card itself (data-nav) and an «Изменить»
// button beside it (data-act="editrow"). They led to two DIFFERENT editors — the card opened the full
// section screen (per-interest toggles, Kleal's summary, «Добавить интересы»), the button opened a
// stripped-down bottom sheet. Same row, same intent, two interfaces. «Личность» had already been
// special-cased to fix exactly this; the rule simply was not general.
//
// Summary rows (Basics / Location / Languages) legitimately keep the sheet: there is no screen behind
// those, so the sheet IS the editor rather than a second one.
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");

let fails = 0;
function check(name, cond, detail) {
  if (!cond) fails++;
  console.log((cond ? "  ok    " : "  FAIL  ") + name + (detail !== undefined ? "   " + JSON.stringify(detail) : ""));
}

// the hub sections, straight from the tab table
const tabs = [...src.matchAll(/\['([a-z]+)','[^']*','[^']*'\]/g)].map(m => m[1]).filter(x => x !== "overview");
check("the hub has sections", tabs.length > 0, tabs);

// the row markup: does one row really carry both affordances?
const rowFn = src.slice(src.indexOf("function navRows()"), src.indexOf("function cbadge("));
check("the card opens the section", /data-nav="\$\{t\[0\]\}"/.test(rowFn));
check("and the row also has an «Изменить» button", /data-act="editrow"/.test(rowFn), true);

// the handler: what each one does
const handler = src.slice(src.indexOf("case 'editrow':"), src.indexOf("case 'edit-int':"));
check("«Изменить» routes hub sections to the SCREEN, like the card does",
      /TABS\.some\(t=>t\[0\]===ds\.row\)/.test(handler) && /setTab\(ds\.row\)/.test(handler),
      handler.slice(0, 120));
check("no hub section is left pointing at a sheet",
      !tabs.some(t => new RegExp("\\b" + t + ":\\s*'" + t + "'").test(handler)), tabs);

// the rows that legitimately keep a sheet still do
check("Basics / Location / Languages keep their sheet",
      /'Basics':'basics'/.test(handler) && /'Location':'location'/.test(handler)
      && /'Languages':'languages'/.test(handler), handler.slice(-160));

// and the sheet is still reachable where it belongs — from inside the section screen
check("the interests screen still offers «Добавить интересы» via the sheet",
      /data-act="add-interests"/.test(src) && /case 'add-interests': openSheet\('interests'\)/.test(src));

console.log(fails ? "\n" + fails + " FAILED" : "\nALL PASS");
process.exit(fails ? 1 : 0);
