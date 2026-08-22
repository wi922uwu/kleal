# -*- coding: utf-8 -*-
"""Страница админки.

ОТДЕЛЬНЫМ ФАЙЛОМ, потому что в app.py она занимала семьдесят процентов объёма: полторы тысячи
строк, из которых девятьсот — разметка со скриптом внутри строкового литерала. Логика тонула.

ЧТО ИЗМЕНИЛОСЬ ПО СУЩЕСТВУ, А НЕ ПО ВИДУ.

1. ПЕРВЫЙ ЭКРАН — «Обзор», и это не украшение. Прежняя панель отвечала только на вопросы про
   подбор и была слепа к тому, на чём система стоит: длина очереди, застрявшие задания, мёртвые
   сообщения, состояние базы. Ровно эти числа молчали, когда обучение таксономии неделями падало
   в несуществующий адрес. Теперь они видны раньше всего остального.

2. ТРЕВОГИ НАВЕРХУ, СПИСКОМ. Не «зелёная точка где-то в углу», а прямая строка: что именно не так.
   Панель, на которой надо ИСКАТЬ проблему, показывает её только тому, кто уже знает, где смотреть.

3. МОСТ ТЕМ ВИДЕН И РЕДАКТИРУЕМ. От него теперь зависит, кого находит поиск, а до сих пор он
   существовал только в файле на боксе.

4. ОДИН ПРИЁМ НА ВСЕ РАЗДЕЛЫ: `api()` + `render()`. Раньше каждая вкладка сама решала, как
   показать ошибку, и половина просто молчала при неудаче — «нажал и ничего», самая дорогая
   разновидность поломки, потому что она неотличима от «всё хорошо».

ЧЕГО ЗДЕСЬ НЕТ НАМЕРЕННО. Разрушительных кнопок. Ни «очистить», ни «пересеять», ни «вычистить
мёртвую очередь»: `/api/admin/clear` и `/api/admin/reseed` однажды уже стёрли живое хранилище без
подтверждения, копии и следа. Единственное действие над очередью — вернуть мёртвое в работу,
и оно ничего не теряет.
"""

PAGE = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Kleal · панель</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f5f6f8; --card:#fff; --line:#e5e7ec; --fg:#161922; --muted:#6b7180;
  --accent:#f5455c; --ok:#12864f; --okbg:#e7f6ee; --warn:#8a5a00; --warnbg:#fdf3e0;
  --bad:#b3261e; --badbg:#fdecea; --code:#f3f4f7;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#12141a; --card:#191c24; --line:#272b36; --fg:#e8eaf0; --muted:#949aa8;
  --okbg:#102a1e; --ok:#4ad08b; --warnbg:#2c2312; --warn:#e0b25c;
  --badbg:#2c1614; --bad:#f08a80; --code:#111319;
}}
body{font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif;
  background:var(--bg);color:var(--fg);-webkit-font-smoothing:antialiased}
.top{background:var(--card);border-bottom:1px solid var(--line);padding:12px 20px;
  display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:10;flex-wrap:wrap}
.logo{font-weight:800;color:var(--accent);font-size:19px;letter-spacing:-.02em}
.pill{font-size:12px;color:var(--muted);background:var(--code);border-radius:20px;padding:3px 10px;
  white-space:nowrap}
.grow{flex:1}
nav{display:flex;gap:4px;padding:0 20px;background:var(--card);border-bottom:1px solid var(--line);
  overflow-x:auto;position:sticky;top:53px;z-index:9}
nav button{background:none;border:0;border-bottom:2px solid transparent;padding:11px 12px;
  font:inherit;color:var(--muted);cursor:pointer;white-space:nowrap}
nav button.on{color:var(--fg);border-bottom-color:var(--accent);font-weight:600}
nav button:hover{color:var(--fg)}
.wrap{max-width:1200px;margin:20px auto;padding:0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;
  margin-bottom:16px}
h2{font-size:15px;margin-bottom:4px}
h2 + .hint{margin-bottom:12px}
.hint{font-size:12.5px;color:var(--muted)}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(210px,1fr))}
.tile{border:1px solid var(--line);border-radius:10px;padding:12px;background:var(--card)}
.tile .k{font-size:12px;color:var(--muted)}
.tile .v{font-size:22px;font-weight:700;letter-spacing:-.02em;margin-top:2px}
.tile .s{font-size:12px;color:var(--muted);margin-top:2px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;vertical-align:1px}
.dot.ok{background:var(--ok)} .dot.bad{background:var(--bad)} .dot.warn{background:var(--warn)}
.alarm{background:var(--badbg);color:var(--bad);border:1px solid transparent;border-radius:10px;
  padding:11px 14px;margin-bottom:12px;font-weight:600}
.alarm ul{margin:6px 0 0 18px;font-weight:400}
.calm{background:var(--okbg);color:var(--ok);border-radius:10px;padding:11px 14px;margin-bottom:12px;
  font-weight:600}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input,select,textarea{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);
  border-radius:9px;padding:8px 10px;min-width:0}
input:focus,textarea:focus,select:focus{outline:2px solid var(--accent);outline-offset:-1px}
button.act{font:inherit;font-weight:600;border:1px solid var(--line);background:var(--card);
  color:var(--fg);border-radius:9px;padding:8px 14px;cursor:pointer}
button.act:hover{border-color:var(--accent)}
button.act.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button.act[disabled]{opacity:.5;cursor:default}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;color:var(--muted);font-weight:600;position:sticky;top:0;background:var(--card)}
tr:hover td{background:var(--code)}
code,pre{font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--code);
  border-radius:7px}
code{padding:1px 5px} pre{padding:12px;overflow:auto;max-height:420px}
.tag{display:inline-block;font-size:12px;background:var(--code);border-radius:6px;padding:2px 7px;
  margin:2px 3px 0 0;color:var(--muted)}
.err{background:var(--badbg);color:var(--bad);border-radius:9px;padding:10px 12px;margin:10px 0}
.ok{color:var(--ok)} .bad{color:var(--bad)} .muted{color:var(--muted)}
.spin{display:inline-block;width:13px;height:13px;border:2px solid var(--line);
  border-top-color:var(--accent);border-radius:50%;animation:sp .8s linear infinite;vertical-align:-2px}
@keyframes sp{to{transform:rotate(360deg)}}
.scroll{overflow:auto;max-height:60vh;border:1px solid var(--line);border-radius:10px}
</style></head><body>

<div class="top">
  <span class="logo">Kleal</span>
  <span class="pill" id="envpill">—</span>
  <span class="grow"></span>
  <input id="tok" type="password" placeholder="Админский токен" style="width:230px">
  <button class="act" onclick="saveTok()">Войти</button>
  <span class="pill" id="clock">—</span>
</div>

<nav id="nav"></nav>
<div class="wrap" id="view"><div class="card"><span class="spin"></span> загружаю…</div></div>

<script>
// ---------------------------------------------------------------- каркас
// Токен в sessionStorage, а не в localStorage: панель управляет живыми людьми, и вкладка,
// закрытая вчера, не должна пускать сегодня без спроса.
let TOK = sessionStorage.getItem('kleal_admin_tok') || '';
let TAB = location.hash.replace('#','') || 'ops';
const S = {};                       // состояние разделов; каждый кладёт своё под своим ключом

const TABS = [
  ['ops',    'Обзор'],
  ['users',  'Люди'],
  ['person', 'Карточка'],
  ['lab',    'Матчинг'],
  ['diag',   'Диагностика'],
  ['bridge', 'Мост тем'],
  ['props',  'Предложения'],
];

function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function num(n){return (n==null||isNaN(n))?'—':new Intl.NumberFormat('ru').format(n)}

/**
 * Один способ ходить на сервер — и один способ показывать неудачу.
 * Раньше каждый раздел решал это сам, и половина при ошибке просто молчала: «нажал и ничего»
 * неотличимо от «всё хорошо», и такие поломки живут до тех пор, пока их не заметит человек.
 */
async function api(path, opts){
  const o = Object.assign({headers:{}}, opts||{});
  o.headers['X-Admin-Token'] = TOK;
  if (o.body && typeof o.body !== 'string'){ o.headers['Content-Type']='application/json'; o.body=JSON.stringify(o.body); o.method=o.method||'POST'; }
  let r;
  try { r = await fetch(path, o); }
  catch(e){ throw new Error('сеть недоступна: ' + e.message); }
  if (r.status === 401) throw new Error('нужен токен — введи его сверху');
  const txt = await r.text();
  let j; try { j = JSON.parse(txt); } catch(e){ throw new Error('сервер ответил не JSON: ' + txt.slice(0,160)); }
  if (!r.ok) throw new Error(j.error || ('код ' + r.status));
  return j;
}

function render(){
  document.getElementById('nav').innerHTML = TABS.map(([k,t]) =>
    `<button class="${TAB===k?'on':''}" onclick="setTab('${k}')">${t}</button>`).join('');
  const v = document.getElementById('view');
  try { v.innerHTML = (VIEWS[TAB] || (()=>'<div class="card">нет такого раздела</div>'))(); }
  catch(e){ v.innerHTML = `<div class="card"><div class="err">не смог отрисовать: ${esc(e.message)}</div></div>`; }
}
function setTab(k){ TAB=k; location.hash=k; render(); (LOADERS[k]||(()=>{}))(); }
function saveTok(){
  TOK = document.getElementById('tok').value.trim();
  sessionStorage.setItem('kleal_admin_tok', TOK);
  (LOADERS[TAB]||(()=>{}))();
}
function busy(key, on){ S[key+'_busy']=on; render(); }
function fail(key, e){ S[key+'_err']=e.message||String(e); S[key+'_busy']=false; render(); }
function errBox(key){ return S[key+'_err'] ? `<div class="err">${esc(S[key+'_err'])}</div>` : ''; }

// ---------------------------------------------------------------- Обзор
const LOADERS = {}, VIEWS = {};

LOADERS.ops = async () => {
  busy('ops', true); S.ops_err='';
  try { S.ops = await api('/api/admin/ops'); S.ops_busy=false; render(); }
  catch(e){ fail('ops', e); }
};

function tile(k, v, s, cls){
  return `<div class="tile"><div class="k">${esc(k)}</div>
    <div class="v ${cls||''}">${v}</div><div class="s">${esc(s||'')}</div></div>`;
}

VIEWS.ops = () => {
  if (S.ops_busy) return `<div class="card"><span class="spin"></span> опрашиваю сервисы…</div>`;
  const d = S.ops; if (!d) return `<div class="card">${errBox('ops')}<button class="act primary" onclick="LOADERS.ops()">Загрузить</button></div>`;
  const al = d.alarms || [];
  const head = al.length
    ? `<div class="alarm">Требует внимания<ul>${al.map(a=>`<li>${esc(a)}</li>`).join('')}</ul></div>`
    : `<div class="calm">Всё отвечает, застрявшего нет</div>`;

  const svc = Object.entries(d.services||{}).map(([n,v]) => {
    const cls = v.ok ? 'ok' : 'bad';
    const note = v.note ? ` <span class="muted">${esc(v.note)}</span>` : (v.error||v.code ? ` <span class="muted">${esc(v.error||v.code)}</span>` : '');
    return `<tr><td><span class="dot ${cls}"></span>${esc(n)}${note}</td>
      <td class="muted">${v.ms==null?'—':v.ms+' мс'}</td>
      <td class="muted">${esc(JSON.stringify(v.info||{}).slice(0,90))}</td></tr>`;
  }).join('');

  const st = d.storage||{}, q = d.queue||{};
  const ob = st.outbox||{};
  const dead = (q.queues||[]).find(x=>x.name==='kleal.dead')||{};
  const work = (q.queues||[]).find(x=>x.name==='teach.phrases')||{};
  const wait = (q.queues||[]).find(x=>x.name==='teach.phrases.wait')||{};

  return `
  ${head}
  <div class="card">
    <h2>Сервисы</h2>
    <div class="hint">404 «нет ручки» и 401 «под паролем» — это отвечает, а не лежит.</div>
    <table><thead><tr><th>сервис</th><th>ответ</th><th>что говорит</th></tr></thead><tbody>${svc}</tbody></table>
    <div class="row" style="margin-top:12px"><button class="act" onclick="LOADERS.ops()">Обновить</button></div>
  </div>

  <div class="card">
    <h2>Хранилище</h2>
    <div class="hint">Режим «mirror» значит: база ведущая, JSON пишется копией — откат ничего не стоит.</div>
    <div class="grid">
      ${tile('режим', esc(st.mode||'—'), st.enabled ? (st.ok?'база отвечает':'база молчит') : 'база не ведущая', st.enabled&&!st.ok?'bad':'')}
      ${tile('размер базы', esc(st.size||'—'), (st.tables||[]).map(t=>t.name+' '+num(t.rows)).join(' · '))}
      ${tile('в outbox ждут', num(ob.pending), 'всего заданий: '+num(ob.total))}
      ${tile('застряли', num(ob.stuck), 'пять попыток и больше', ob.stuck?'bad':'ok')}
    </div>
  </div>

  <div class="card">
    <h2>Очередь</h2>
    <div class="hint">«Ждут повтора» — это НЕ потеря: сообщение вернётся само через 5 с, 30 с, 2 мин и дальше.</div>
    <div class="grid">
      ${tile('режим', esc(q.mode||'—'), q.enabled ? (q.ok?'брокер отвечает':'брокер молчит') : 'очередь выключена', q.enabled&&!q.ok?'bad':'')}
      ${tile('в работе', num(work.messages), 'потребителей: '+num(work.consumers))}
      ${tile('ждут повтора', num(wait.messages), 'вернутся сами', wait.messages?'warn':'')}
      ${tile('мёртвые', num(dead.messages), 'сдались после шести попыток', dead.messages?'bad':'ok')}
    </div>
    <div class="row" style="margin-top:12px">
      <button class="act" onclick="loadDead()">Показать мёртвые</button>
      <button class="act primary" onclick="retryDead()" ${dead.messages?'':'disabled'}>Вернуть в работу</button>
      <span class="hint">Кнопки «очистить» здесь нет намеренно: выбросить работу молча — то, от чего уходили.</span>
    </div>
    ${S.dead ? `<div class="scroll" style="margin-top:12px"><pre>${esc(JSON.stringify(S.dead, null, 2))}</pre></div>` : ''}
  </div>`;
};

async function loadDead(){
  try { const r = await api('/api/admin/dead'); S.dead = r.items||[]; render(); }
  catch(e){ fail('ops', e); }
}
async function retryDead(){
  try { const r = await api('/api/admin/dead/retry', {body:{}}); S.dead=null; await LOADERS.ops();
        alert('вернул в работу: ' + (r.returned||0) + (r.failed?(', не смог: '+r.failed):'')); }
  catch(e){ fail('ops', e); }
}

// ---------------------------------------------------------------- Люди
LOADERS.users = async () => {
  busy('users', true); S.users_err='';
  try { const r = await api('/api/admin/users?limit=200'); S.users = r.users||r.rows||[]; S.users_busy=false; render(); }
  catch(e){ fail('users', e); }
};

VIEWS.users = () => {
  if (S.users_busy) return `<div class="card"><span class="spin"></span> читаю популяцию…</div>`;
  const all = S.users;
  if (!all) return `<div class="card">${errBox('users')}<button class="act primary" onclick="LOADERS.users()">Загрузить</button></div>`;
  const q = (S.uq||'').toLowerCase();
  const rows = all.filter(u => !q || JSON.stringify(u).toLowerCase().includes(q)).slice(0,200);
  return `<div class="card">
    <h2>Люди <span class="pill">${num(all.length)}</span></h2>
    <div class="hint">Поиск идёт по всей строке: имя, город, интересы, источник.</div>
    <div class="row" style="margin:10px 0">
      <input style="flex:1;min-width:220px" placeholder="искать…" value="${esc(S.uq||'')}"
        oninput="S.uq=this.value;render();document.querySelector('.card input').focus()">
      <button class="act" onclick="LOADERS.users()">Обновить</button>
    </div>
    <div class="scroll"><table><thead><tr><th>имя</th><th>возраст</th><th>город</th><th>интересы</th><th>источник</th><th></th></tr></thead><tbody>
    ${rows.map(u=>`<tr>
      <td><b>${esc(u.name)}</b></td><td>${esc(u.age||'')}</td><td>${esc(u.area||u.city||'')}</td>
      <td>${(u.interests||[]).slice(0,5).map(i=>`<span class="tag">${esc(i)}</span>`).join('')}</td>
      <td class="muted">${esc(u.source||'')}</td>
      <td><button class="act" onclick="openPerson('${esc(u.name).replace(/'/g,"\\'")}')">Карточка</button></td>
    </tr>`).join('')}
    </tbody></table></div>
    ${rows.length>=200?'<div class="hint" style="margin-top:8px">Показаны первые 200 — уточни поиск.</div>':''}
  </div>`;
};

function openPerson(n){ S.pname=n; setTab('person'); loadPerson(); }

// ---------------------------------------------------------------- Карточка
LOADERS.person = () => { if (S.pname) loadPerson(); };
async function loadPerson(){
  const n = S.pname || document.getElementById('pn')?.value || '';
  if (!n) return;
  S.pname = n; busy('person', true); S.person_err='';
  try { S.person = await api('/api/admin/person?name=' + encodeURIComponent(n)); S.person_busy=false; render(); }
  catch(e){ fail('person', e); }
}
VIEWS.person = () => {
  const p = S.person;
  const form = `<div class="row" style="margin-bottom:12px">
      <input id="pn" style="flex:1;min-width:220px" placeholder="имя человека" value="${esc(S.pname||'')}">
      <button class="act primary" onclick="S.pname=document.getElementById('pn').value;loadPerson()">Показать</button>
    </div>`;
  if (S.person_busy) return `<div class="card">${form}<span class="spin"></span> считаю видимость…</div>`;
  if (!p) return `<div class="card">${form}${errBox('person')}<div class="hint">Карточка отвечает на два вопроса: почему человека никто не находит и почему он не находит никого.</div></div>`;
  const id = p.identity||{};
  return `<div class="card">${form}${errBox('person')}
    <h2>${esc(p.name||S.pname)} <span class="pill">${esc(p.verdict||'')}</span></h2>
    <div class="grid" style="margin-top:12px">
      ${tile('в пуле', p.inPool?'да':'нет', id.source||'', p.inPool?'ok':'bad')}
      ${tile('возраст', esc(id.age||'—'), id.datingOk?'открыт романтике':'')}
      ${tile('координаты', id.lat?'есть':'нет', id.radiusKm?('радиус '+id.radiusKm+' км'):'', id.lat?'ok':'bad')}
      ${tile('интересов', num((id.interests||[]).length), 'своих затей: '+num(id.ownIntents))}
    </div>
    ${(p.blocks||[]).length?`<div class="card" style="margin-top:12px"><h2 class="bad">Его не находят</h2>
      <ul style="margin-left:18px">${p.blocks.map(b=>`<li>${esc(b.ru||b.key)}</li>`).join('')}</ul></div>`:''}
    ${(p.outbound||[]).length?`<div class="card" style="margin-top:12px"><h2 class="bad">Он не находит</h2>
      <ul style="margin-left:18px">${p.outbound.map(b=>`<li>${esc(b.ru||b.key)}</li>`).join('')}</ul></div>`:''}
    ${(p.warnings||[]).length?`<div class="card" style="margin-top:12px"><h2 class="muted">Предупреждения</h2>
      <ul style="margin-left:18px">${p.warnings.map(b=>`<li>${esc(b.ru||b.key)}</li>`).join('')}</ul></div>`:''}
  </div>`;
};

// ---------------------------------------------------------------- Матчинг
// Список имён для выбора ищущего. Грузится один раз и переиспользуется: без него поле было
// просто строкой, и опечатка в имени молча превращала поиск в «от лица неизвестного Tester» —
// движок отвечал не тем, а выглядело это как поломка подбора.
LOADERS.lab = async () => {
  if (S.names) return;
  try { const r = await api('/api/admin/users?limit=2000'); S.names = (r.users||[]).map(u=>u.name).filter(Boolean); render(); }
  catch(e){ /* без списка поле остаётся обычным вводом — это хуже, но не мешает */ }
};

VIEWS.lab = () => {
  const r = S.lab;
  return `<div class="card">
    <h2>Один поиск, весь разбор</h2>
    <div class="hint">Тот же путь, что у приложения: темы собирает фильтрация, а фраза едет рядом —
      по ней работает мост тем, иначе «опционы» разбираются как «варианты выбора».</div>
    <div class="row" style="margin:10px 0">
      <input id="lq" style="flex:2;min-width:240px" placeholder="что ищем: поговорить про опционы" value="${esc(S.lq||'')}">
      <input id="ls" list="names" style="flex:1;min-width:170px" placeholder="от чьего имени" value="${esc(S.ls||'')}">
      <datalist id="names">${(S.names||[]).slice(0,2000).map(n=>`<option value="${esc(n)}">`).join('')}</datalist>
      <select id="ln" style="min-width:110px">
        ${[8,16,24,32,48].map(n=>`<option value="${n}" ${(S.ln||8)==n?'selected':''}>${n} человек</option>`).join('')}
      </select>
      <button class="act primary" onclick="runLab()" ${S.lab_busy?'disabled':''}>${S.lab_busy?'Ищу…':'Искать'}</button>
    </div>
    <div class="hint">${S.names?('в списке '+num(S.names.length)+' человек — начни печатать имя'):'загружаю имена…'}</div>
    ${errBox('lab')}
    ${r?`
      ${r.searcherKnown===false?`<div class="err">Такого человека в популяции нет — поиск ушёл от лица чужака
        без интересов и координат, и пустой ответ тут ничего не значит. Выбери имя из списка.</div>`:''}
      <div class="hint" style="margin:8px 0">
        ищет: <b>${esc((r.searcher||{}).name||'—')}</b>
        · темы: ${(r.topics||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('') || '<span class="bad">ни одной</span>'}
        · кандидатов: <b>${num((r.candidates||[]).length)}</b>${
          r.hasMore ? ' <span class="tag">есть ещё</span>'
          : ((r.candidates||[]).length < (r.limit||8)
             ? ` <span class="tag">это все, кто подходит</span>` : '')}
        · виды: ${[...new Set((r.candidates||[]).map(c=>c.kind))].map(k=>`<span class="tag">${esc(k)}</span>`).join('')}</div>
      <div class="scroll"><table><thead><tr><th>кто</th><th>ярус</th><th>полоса</th><th>почему</th><th>интересы</th></tr></thead><tbody>
      ${(r.candidates||[]).map(c=>`<tr><td><b>${esc(c.name)}</b></td><td>${esc(c.tier||'')}</td>
        <td>${esc(c.band_ru||c.band||'')}</td>
        <td class="muted">${esc((c.reasons_ru||c.reasons||[]).join('; ')).slice(0,120)}</td>
        <td>${(c.interests||[]).slice(0,4).map(i=>`<span class="tag">${esc(i)}</span>`).join('')}</td></tr>`).join('')}
      </tbody></table></div>
      ${(r.candidates||[]).length < (r.limit||8) && !r.hasMore ? `<div class="hint" style="margin-top:8px">
        Меньше, чем просили, — и это не обрезка: движок отдал всех, у кого нашлось хоть какое-то
        совпадение с темами <b>${(r.topics||[]).map(t=>esc(t)).join(', ')||'—'}</b>. Остальные не показаны
        не потому, что не поместились, а потому что общего с запросом у них нет вовсе.</div>` : ''}`:''}
  </div>`;
};
async function runLab(){
  // ВСЁ ИЗ ПОЛЕЙ ЧИТАЕТСЯ ДО busy(): он зовёт render(), а тот пересобирает разметку заново и
  // возвращает контролам значения из S. Счётчик читался ПОСЛЕ — и выбор человека затирался
  // восьмёркой из состояния ровно в тот момент, когда его собирались отправить.
  S.lq = document.getElementById('lq').value.trim();
  S.ls = document.getElementById('ls').value.trim();
  const _n = document.getElementById('ln'); S.ln = _n ? parseInt(_n.value,10)||8 : 8;
  if (!S.lq){ S.lab_err='нечего искать — напиши фразу'; render(); return; }
  busy('lab', true); S.lab_err='';
  try { S.lab = await api('/api/admin/match-test', {body:{query:S.lq, self:S.ls, limit:S.ln}}); S.lab_busy=false; render(); }
  catch(e){ fail('lab', e); }
}

// ---------------------------------------------------------------- Диагностика
VIEWS.diag = () => `<div class="card">
    <h2>Диагностика</h2>
    <div class="hint">Тяжёлые прогоны: часть из них зовёт модель и занимает минуты. Запускай по одному.</div>
    <div class="row" style="margin:10px 0">
      <button class="act" onclick="diag('funnel')">Воронка</button>
      <button class="act" onclick="diag('diversity')">Разнообразие</button>
      <button class="act" onclick="diag('cohorts')">Когорты</button>
      <button class="act" onclick="diag('stability')">Устойчивость</button>
    </div>
    ${errBox('diag')}
    ${S.diag_busy?'<span class="spin"></span> считаю…':''}
    ${S.diag?`<pre>${esc(JSON.stringify(S.diag,null,2))}</pre>`:''}
  </div>`;
async function diag(kind){
  busy('diag', true); S.diag_err=''; S.diag=null;
  try { S.diag = await api('/api/admin/' + kind); S.diag_busy=false; render(); }
  catch(e){ fail('diag', e); }
}

// ---------------------------------------------------------------- Мост тем
LOADERS.bridge = async () => {
  busy('bridge', true); S.bridge_err='';
  try { S.bridge = await api('/api/admin/bridge?q=' + encodeURIComponent(S.bq||'')); S.bridge_busy=false; render(); }
  catch(e){ fail('bridge', e); }
};
VIEWS.bridge = () => {
  const b = S.bridge;
  return `<div class="card">
    <h2>Мост тем</h2>
    <div class="hint">От него зависит, кого находит поиск: «опционы» встречаются с «finanzas» именно здесь.
      Хранится ФРАЗА и её темы — не слово, иначе «gracia» становится падлом.</div>
    <div class="row" style="margin:10px 0">
      <input style="flex:1;min-width:220px" placeholder="искать фразу или тему" value="${esc(S.bq||'')}"
        onchange="S.bq=this.value;LOADERS.bridge()">
      <button class="act" onclick="LOADERS.bridge()">Найти</button>
    </div>
    <div class="row" style="margin:10px 0">
      <input id="bt" style="flex:1;min-width:220px" placeholder="научить новой фразе: поговорить про опционы">
      <button class="act primary" onclick="teachPhrase()">Научить</button>
      <span class="hint">Уходит в очередь — страница не ждёт модель.</span>
    </div>
    ${errBox('bridge')}
    ${S.bridge_busy?'<span class="spin"></span> читаю мост…':''}
    ${b?`<div class="hint" style="margin:8px 0">всего фраз: <b>${num(b.total)}</b> · подошло: <b>${num(b.matched)}</b></div>
      <div class="scroll"><table><thead><tr><th>фраза</th><th>темы</th></tr></thead><tbody>
      ${(b.items||[]).map(i=>`<tr><td>${esc(i.phrase)}</td>
        <td>${(i.topics||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</td></tr>`).join('')}
      </tbody></table></div>`:''}
  </div>`;
};
async function teachPhrase(){
  const v = document.getElementById('bt').value;
  try { const r = await api('/api/admin/bridge/teach', {body:{phrase:v}});
        alert(r.ok ? ('задание поставлено: ' + r.phrase) : ('не вышло: ' + (r.error||'')));
        document.getElementById('bt').value=''; }
  catch(e){ fail('bridge', e); }
}

// ---------------------------------------------------------------- Предложения
LOADERS.props = async () => {
  busy('props', true); S.props_err='';
  try { S.props = await api('/api/admin/proposals'); S.props_busy=false; render(); }
  catch(e){ fail('props', e); }
};
VIEWS.props = () => {
  if (S.props_busy) return `<div class="card"><span class="spin"></span> читаю журнал…</div>`;
  const p = S.props;
  if (!p) return `<div class="card">${errBox('props')}<button class="act primary" onclick="LOADERS.props()">Загрузить</button></div>`;
  const rows = p.requests || p.items || [];
  return `<div class="card">
    <h2>Предложения <span class="pill">${num(rows.length)}</span></h2>
    <div class="hint">Только чтение: журнал живёт в хранилище матчинга, и панель туда не пишет.</div>
    <div class="scroll" style="margin-top:10px"><table><thead><tr><th>от</th><th>кому</th><th>состояние</th><th>когда</th></tr></thead><tbody>
    ${rows.slice(0,300).map(r=>`<tr><td>${esc(r.from)}</td><td>${esc(r.to)}</td>
      <td>${esc(r.status)}</td><td class="muted">${esc(r.created||r.t||'')}</td></tr>`).join('')}
    </tbody></table></div>
  </div>`;
};

// ---------------------------------------------------------------- запуск
document.getElementById('tok').value = TOK;
setInterval(()=>{ document.getElementById('clock').textContent = new Date().toLocaleTimeString('ru'); }, 1000);
api('/api/admin/ping').then(r=>{
  document.getElementById('envpill').textContent =
    'хранилище: ' + (r.storage||'?') + ' · очередь: ' + (r.queue||'?');
}).catch(()=>{ document.getElementById('envpill').textContent = 'нужен токен'; });
render();
(LOADERS[TAB]||(()=>{}))();
</script></body></html>'''
