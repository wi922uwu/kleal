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
/* ТЕРМИНАЛЬНЫЙ ВИД БАТАРЕИ — по рабочему терминалу владельца (папка TRADE).
   Оттуда взяты и приёмы, и меры: чёрный фон, плитка с шапкой «⣿ ИМЯ», тонкая ВНУТРЕННЯЯ рамка
   вместо тени, шапка 10.5px капсом с разрядкой, моноширинный шрифт с табличными цифрами.
   Плотность там — главное: ничего не «дышит», всё видно на одном экране. Всё заперто в `.терм`,
   чтобы соседние вкладки жили по своим правилам. */
/* ВО ВСЮ ШИРИНУ. Общая обёртка держит 1200px и поля по 20px — разумно для таблиц и карточек,
   но терминалу они мешают: плитки жмутся, а справа висит пустота. Выходим за обёртку теми же
   числами, какими она задана (см. .wrap выше): поля гасим, ширину берём всю. */
.терм{margin:-20px calc(50% - 50vw) 0;width:100vw;max-width:100vw;padding:8px 10px;border-radius:0;
  --фон:#000;--карта:#050506;--текст:#ececee;--текст2:#a6a6ab;--текст3:#6f6f76;
  --вверх:#3ecf8e;--вниз:#ff6b5e;--охра:#d9a83a;--синь:#6ea0ff;--линия:rgba(255,255,255,.07);
  background:var(--фон);color:var(--текст);
  font:11.5px/1.45 "JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  font-feature-settings:"tnum" 1}
.т-сетка{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:8px}
.терм .пан{position:relative;display:flex;flex-direction:column;min-width:0;overflow:hidden;
  border-radius:8px;background:var(--карта);box-shadow:inset 0 0 0 1px var(--линия)}
.терм .пан-шапка{display:flex;align-items:center;gap:8px;flex:none;padding:5px 8px 4px 9px;
  font:600 10.5px "JetBrains Mono",ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;
  color:rgba(236,236,238,.72);background:rgba(255,255,255,.03);border-bottom:1px solid rgba(255,255,255,.05)}
.терм .пан-ручка{font-style:normal;font-size:10px;color:rgba(236,236,238,.3)}
.терм .пан-имя{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.терм .пан-хвост{margin-left:auto;color:var(--текст3);font-weight:400;letter-spacing:.04em}
.терм .пан-тело{padding:6px 9px 8px;min-height:0;overflow:auto}
.кв-сетка{display:grid;grid-template-columns:1fr 1fr;gap:2px 10px}
.кв-стр{display:flex;align-items:baseline;justify-content:space-between;gap:8px;
  border-bottom:1px solid rgba(255,255,255,.04);padding:2px 0}
.кв-стр i{font-style:normal;font-size:9.5px;letter-spacing:.08em;color:var(--текст3)}
.кв-стр b{font-weight:600;color:#fff;white-space:nowrap}
.т-искра{color:var(--вверх);letter-spacing:.5px}
.т-тихо{color:var(--текст3)}
.т-подпись{margin:6px 0 2px;font-size:9.5px;letter-spacing:.08em}
.т-вверх{color:var(--вверх)} .т-вниз{color:var(--вниз)}
.т-бар{white-space:pre;line-height:1.4}
.т-барв{color:var(--вверх)}
.т-полоса{display:flex;flex-wrap:wrap;gap:5px;align-items:center;margin-bottom:8px}
.т-кн{appearance:none;border:0;cursor:pointer;padding:4px 9px;border-radius:6px;
  font:600 10.5px "JetBrains Mono",ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;
  color:var(--текст2);background:var(--карта);box-shadow:inset 0 0 0 1px var(--линия)}
.т-кн.вкл{color:#000;background:var(--вверх);box-shadow:none}
.т-поле{flex:1 1 220px;background:var(--карта);color:var(--текст);border:0;padding:4px 9px;border-radius:6px;
  box-shadow:inset 0 0 0 1px var(--линия);font:11.5px "JetBrains Mono",ui-monospace,monospace}
.т-лента{height:46vh;overflow:auto;padding-right:2px}
.t-row{padding:1px 0;border-bottom:1px solid rgba(255,255,255,.04);white-space:pre-wrap;word-break:break-word}
/* КТО ГОВОРИТ — СЛОВОМ. Значки «▸» и «◂» различались только направлением, и в плотной ленте на
   трёх языках понять, где человек, а где Kleal, было нельзя. Подпись словом плюс своя полоса
   слева: человек синей, Kleal зелёной. */
.реч{padding-left:6px;border-left:2px solid transparent}
.реч.чел{border-left-color:var(--синь)}
.реч.бот{border-left-color:rgba(62,207,142,.5)}
.кто{display:inline-block;min-width:58px;font-size:9px;letter-spacing:.09em;padding:0 4px;
  border-radius:3px;margin-right:4px;text-align:center;vertical-align:1px}
.кто-чел{color:#001018;background:var(--синь)}
.кто-бот{color:#00180d;background:var(--вверх)}
.t-row.t-k,.t-row .t-dim{color:var(--текст3)}
.t-dim{color:var(--текст3)} .t-scen{color:var(--синь);opacity:.8}
.t-you{color:var(--синь)} .t-ai{color:var(--текст)}
.t-ok .t-okm,.t-okm{color:var(--вверх)}
.t-bad{background:rgba(255,107,94,.07)} .t-badm{color:var(--вниз)}
.t-tag{color:var(--вниз);box-shadow:inset 0 0 0 1px rgba(255,107,94,.35);padding:0 4px;margin-right:4px;border-radius:3px}
.t-sub{color:var(--текст3);padding-left:2ch}
.t-sep{color:var(--охра);text-align:center;padding:4px 0}
.т-строка{white-space:pre;border-bottom:1px solid rgba(255,255,255,.04);padding:1px 0}
/* Подпись поля в плитке разбора: узкая колонка слева, чтобы значения выстроились в столбик. */
.т-имя{display:inline-block;min-width:96px;color:var(--muted);text-transform:uppercase;font-size:9.5px;letter-spacing:.06em}
/* Ряд с колонками в плитке ответов модели: строка длинная, колонки должны держать ширину. */
.т-ряд{display:flex;gap:8px;align-items:baseline;white-space:nowrap;border-bottom:1px solid rgba(255,255,255,.04);padding:1px 0}
/* Круг квадратами: один квадрат — один сценарий, цвет — исход. */
.кв-поле{display:flex;flex-wrap:wrap;gap:2px;align-content:flex-start}
.кв-клетка{width:11px;height:11px;border-radius:2px;cursor:pointer;display:block;
  box-shadow:inset 0 0 0 1px rgba(0,0,0,.5)}
.кв-клетка.чисто{background:var(--вверх);opacity:.7}
.кв-клетка.беда{background:var(--вниз);opacity:.85}
.кв-клетка.идёт{background:var(--охра);animation:д-пульс 1.1s ease-in-out infinite}
.кв-клетка.выбран{outline:1px solid #fff;outline-offset:1px;opacity:1}
.кв-клетка:hover{opacity:1;transform:scale(1.25)}
.кв-низ{margin-top:6px}
@keyframes д-пульс{0%,100%{opacity:.45}50%{opacity:.95}}
/* ДЕРЕВО БАТАРЕИ — три цвета, как на референсах: белый (чисто), красный (беда), серые нити.
   Всё в единицах viewBox, поэтому толщины тонкие: картинка 1000 единиц ужимается в ~700px. */
.т-охра{color:var(--охра)}
.т-ссылка{cursor:pointer;color:var(--текст2);text-decoration:underline dotted}
.т-лента-низ{height:26vh}
/* РОСТ ЗАДАЁТ ВЫСОТА, А НЕ ШИРИНА. При `width:100%` + `max-height` картинка получалась выше
   плитки и уезжала под нижний край: тело плитки прокручиваемое, и круг обрезался. */
.кольца{display:block;width:auto;height:min(74vh,880px);max-width:100%;aspect-ratio:1/1;margin:0 auto;
  background:radial-gradient(circle at 50% 50%,#08080a 0,#000 70%);border-radius:8px;cursor:grab;touch-action:none}
.кольца:active{cursor:grabbing}
/* ОДНА ДУГА — ОДИН ПРОГОН. Дуга видима, но не спорит со штрихами разговоров под ней. */
.кольца .дуга{fill:none;stroke:rgba(255,255,255,.17);stroke-width:.8}
.кольца .дуга.тек{stroke:rgba(255,255,255,.3);stroke-width:1.1}
.кольца .дуга.край{stroke:rgba(255,255,255,.12);stroke-width:.7}
.кольца .ш{cursor:pointer}
.кольца .ш:hover .п-штрих{opacity:1;stroke-width:1.8}
.кольца .п-попап{fill:rgba(255,255,255,.75)}
/* Чистое прошлое приглушено, беда — нет: внутренние кольца это ИСТОРИЯ, и глаз должен читать в
   ней не «сколько всего было», а «где болело». Иначе зелень чистых кругов забивает всю картину. */
.кольца .п-штрих{stroke-width:1.1;stroke-linecap:round;opacity:.3}
.кольца .п-штрих.беда{opacity:.85;stroke-width:.95}
.кольца .круг{transition:opacity .6s ease}
.кольца .сектор-имя{fill:rgba(236,236,238,.45);font:600 9px "JetBrains Mono",ui-monospace,monospace;letter-spacing:.18em;text-anchor:middle}
/* Цвет ствола приходит атрибутом `stroke` из раскладки (вид беды / чисто / идёт), поэтому здесь
   только толщина, прозрачность и ПЕРЕХОД: когда сценарий кончается, ветка плавно перекрашивается
   из «идёт» в цвет исхода — это и есть видимый признак, что данные живые. */
.кольца .в .ствол{stroke-width:.75;opacity:.62;transition:stroke .45s ease,opacity .45s ease,stroke-width .2s}
.кольца .в.беда .ствол{opacity:.8}
.кольца .в.идёт .ствол{stroke-dasharray:2 2;animation:д-пульс 1.2s ease-in-out infinite}
.кольца .узел-чел{fill:#000;stroke:rgba(236,236,238,.85);stroke-width:.7}
.кольца .узел-бот{fill:rgba(236,236,238,.8)}
/* Отбор по виду беды: чужие ветки не прячем, а гасим — исчезнувшая ветка врала бы о плотности. */
.кольца .в.тускло{opacity:.09}
.кольца .в{transition:opacity .3s ease}
/* Новая ветка ПРОРАСТАЕТ, а не возникает: 40 единиц с запасом длиннее любого ствола. */
.кольца .в.рост .ствол{stroke-dasharray:140;stroke-dashoffset:140;animation:рост-линия .75s ease-out forwards}
.кольца .в.рост circle{animation:узел-всплыл .5s ease-out backwards}
.кольца .в.дрогнула circle{animation:узел-всплыл .45s ease-out backwards}
.кольца .в.гаснет{opacity:0;transition:opacity .45s ease}
@keyframes рост-линия{to{stroke-dashoffset:0}}
@keyframes узел-всплыл{from{opacity:0;transform:scale(.2)}to{opacity:1;transform:none}}
.кольца .сияние{fill:rgba(255,255,255,.14)}
.кольца .узел-готово{fill:#fff}
.кольца .отросток{fill:none;stroke:rgba(236,236,238,.5);stroke-width:.6}
.кольца .узел-затея{fill:#000;stroke:#fff;stroke-width:.9}
.кольца .лист-нить{stroke:rgba(236,236,238,.32);stroke-width:.55}
.кольца .лист-мастер{fill:rgba(236,236,238,.9)}
.кольца .лист-попап{fill:#000;stroke:rgba(236,236,238,.9);stroke-width:.7}
.кольца .обрыв{stroke:rgba(245,69,92,.9);stroke-width:.9;stroke-dasharray:1.2 1.2}
.кольца .разошлись{stroke:rgba(245,69,92,.95);stroke-width:.8}
.кольца .в{cursor:pointer}
.кольца .в:hover .ствол,.кольца .в.выбр .ствол{stroke-width:1.6;opacity:1}
.кольца .в.выбр .узел-бот,.кольца .в:hover .узел-бот{fill:#fff}
.кольца .в.иск .ствол{stroke-width:1.4;opacity:1}
.кольца .в.иск .узел-бот{fill:var(--охра)}
/* СЕРДЦЕ КРУГА. Всё моноширинным и с табличными цифрами: числа меняются каждые две с половиной
   секунды, и прыгающая ширина знака дёргала бы весь блок. */
.кольца .с-подпись{fill:rgba(236,236,238,.45);font:600 8.5px "JetBrains Mono",ui-monospace,monospace;letter-spacing:.16em}
.кольца .с-число{fill:#fff;font:700 34px "JetBrains Mono",ui-monospace,monospace;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.кольца .с-важно{fill:#fff;font:600 12.5px "JetBrains Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
.кольца .с-мелкое{fill:rgba(236,236,238,.85);font:11.5px "JetBrains Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums}
.кольца .с-мелкое.плохо{fill:#ff4d6d}
.кольца .с-черта{stroke:rgba(255,255,255,.08);stroke-width:.7}
.кольца .с-полоса{stroke:rgba(255,255,255,.1);stroke-width:2.4;stroke-linecap:round}
.кольца .с-полоса.есть{stroke:#3ecf8e}
.кольца .искра{fill:none;stroke-width:1.1;stroke-linejoin:round;stroke-linecap:round;opacity:.9}
/* Легенда — она же отбор: цвет тут значит ровно то же, что в кольцах и в «Видах бед». */
.д-легенда{display:flex;flex-wrap:wrap;gap:3px 6px;align-items:center;margin-top:7px;font-size:10px}
.л-вид{display:inline-flex;align-items:center;gap:4px;padding:2px 7px;border-radius:20px;cursor:pointer;
  color:var(--текст2);box-shadow:inset 0 0 0 1px var(--линия);white-space:nowrap}
.л-вид i{width:7px;height:7px;border-radius:50%;display:inline-block}
.л-вид:hover{color:var(--текст);box-shadow:inset 0 0 0 1px rgba(255,255,255,.2)}
.л-вид.вкл{color:#000;background:var(--текст);font-weight:600}
.л-сброс{cursor:pointer;color:var(--охра);padding:2px 6px}
.л-помощь{margin-left:auto;font-size:9.5px}
/* Строка вида беды в плитке — та же краска, то же нажатие. */
.вид-стр{cursor:pointer;display:flex;align-items:center;gap:5px;border-radius:4px;padding:0 3px;margin:0 -3px}
.вид-стр:hover{background:rgba(255,255,255,.05)}
.вид-стр.вкл{background:rgba(255,255,255,.09);color:#fff}
.вид-точка{width:7px;height:7px;border-radius:50%;flex:none}
/* Веер диалога */
.веер{display:block;width:100%;height:auto;max-height:230px;margin:2px 0 6px;background:#040405;border-radius:6px;
  box-shadow:inset 0 0 0 1px var(--линия)}
.веер .в-ось{stroke:rgba(255,255,255,.12);stroke-width:1}
.веер .в-нить{fill:none;stroke:rgba(236,236,238,.16);stroke-width:.8}
.веер .узел-чел{fill:#000;stroke:#ececee;stroke-width:1.2}
.веер .узел-бот{fill:#ececee}
.веер .сияние{fill:rgba(255,255,255,.14)}
.веер .узел-готово{fill:#fff}
.веер .отросток{fill:none;stroke:rgba(236,236,238,.55);stroke-width:.9}
.веер .узел-затея{fill:#000;stroke:#fff;stroke-width:1.3}
.веер .лист-нить{fill:none;stroke:rgba(236,236,238,.4);stroke-width:.9}
.веер .лист-мастер{fill:#ececee}
.веер .лист-попап{fill:#000;stroke:#ececee;stroke-width:1.2}
.веер .обрыв{stroke:#f5455c;stroke-width:1.4;stroke-dasharray:2 2}
.веер .разошлись{stroke:#f5455c;stroke-width:1.2}
.веер .беда-нить{stroke:rgba(245,69,92,.5);stroke-width:.8;stroke-dasharray:1.5 1.5}
.веер .узел-беда{fill:#f5455c}
.веер .в-подпись{fill:rgba(236,236,238,.62);font:9.5px "JetBrains Mono",ui-monospace,monospace}
.веер .в-подпись.чел{fill:var(--синь)}
.веер .в-подпись.яркая{fill:#fff;font-weight:600}
.веер .в-подпись.плохо{fill:#f5455c}
.д-загол{color:#fff;margin-bottom:4px}
.д-диалог{max-height:44vh;overflow:auto}
.и-итог{margin-top:8px;padding:7px 8px;background:rgba(255,255,255,.03);box-shadow:inset 0 0 0 1px var(--линия);border-radius:6px}
.и-загол{color:var(--охра);letter-spacing:.1em;margin-bottom:4px}
.и-стр{display:grid;grid-template-columns:150px 1fr;gap:8px;padding:1px 0;border-bottom:1px solid rgba(255,255,255,.04)}
.и-стр i{font-style:normal;font-size:9.5px;letter-spacing:.07em;color:var(--текст3)}
.и-стр b{font-weight:500;color:var(--текст);word-break:break-word}
.и-ворч{margin-top:5px}
@media (max-width:1100px){.т-сетка{grid-template-columns:repeat(6,minmax(0,1fr))}
  .терм .пан{grid-column:span 6 !important}}
.blive{max-height:60vh;overflow:auto;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
.brow{padding:2px 6px;border-bottom:1px solid var(--line)}
.brow .bt{color:var(--muted);opacity:.7}
.brow .bs{color:var(--muted)}
.brow .bh{color:var(--accent)}
.brow.bk{opacity:.85}
.brow.bok{background:rgba(40,160,90,.07)}
.brow.bbad{background:rgba(220,60,60,.09)}
.brow.bsep{text-align:center;color:var(--muted);padding:6px 0;background:transparent}
nav{display:flex;gap:4px;padding:0 20px;background:var(--card);border-bottom:1px solid var(--line);
  overflow-x:auto;position:sticky;top:53px;z-index:9}
nav button{background:none;border:0;border-bottom:2px solid transparent;padding:11px 12px;
  font:inherit;color:var(--muted);cursor:pointer;white-space:nowrap}
nav button.on{color:var(--fg);border-bottom-color:var(--accent);font-weight:600}
nav button:hover{color:var(--fg)}
.wrap{max-width:1200px;margin:20px auto;padding:0 20px}
/* ЧЁРНАЯ ПАНЕЛЬ ВСЕГДА, А НЕ ПО НАСТРОЙКЕ СИСТЕМЫ.
   Тёмные цвета были спрятаны в `@media (prefers-color-scheme: dark)`, и у человека со светлой
   системой шапка оставалась белой рядом с чёрным терминалом батареи — панель выглядела склеенной
   из двух разных. Ставим ту же палитру, что в терминале (папка TRADE), и ставим безусловно. */
:root{--bg:#000;--card:#050506;--line:rgba(255,255,255,.07);--fg:#ececee;--muted:#8a8a91;
  --code:#0b0b0c;--okbg:rgba(62,207,142,.12);--ok:#3ecf8e;--warnbg:rgba(217,168,58,.12);--warn:#d9a83a;
  --badbg:rgba(255,107,94,.12);--bad:#ff6b5e}
body{background:#000;color:var(--fg)}
.top{background:#000;border-bottom:1px solid var(--line)}
nav{background:#050506;border-bottom:1px solid var(--line)}
nav button.on{border-bottom-color:var(--ok);color:#fff}
.card{background:var(--card);border:1px solid var(--line)}
input,select,textarea{background:#0b0b0c;color:var(--fg);border:1px solid var(--line)}
.prow{display:flex;justify-content:space-between;gap:8px;padding:6px 8px;border-radius:8px;
  cursor:pointer;font-size:13px}
.prow:hover{background:var(--code)}
.prow.on{background:var(--code);font-weight:600}
.toast{position:fixed;right:18px;bottom:18px;z-index:50;background:var(--fg);color:var(--card);
  padding:10px 14px;border-radius:10px;font-size:13px;max-width:420px;opacity:0;
  transition:opacity .2s;box-shadow:0 10px 30px rgba(0,0,0,.22)}
.toast.bad{background:var(--bad);color:#fff}
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
  <input id="tok" type="password" placeholder="Пароль" style="width:230px">
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

// Порядок — по частоте, с которой сюда заходят, а не по истории появления разделов.
// «Карточка» из списка ушла: она открывается нажатием на человека и больше не требует
// перепечатывать имя в отдельной вкладке. «Диагностика» переехала внутрь «Матчинга»: это
// прогоны того же поиска, и держать их врозь значило звать их по очереди из двух мест.
const TABS = [
  ['ops',     'Сводка'],
  ['battery', 'Батарея'],
  ['users',   'Люди'],
  ['reports', 'Жалобы'],
  ['model',   'Модель'],
  ['prompts', 'Промпты'],
  ['lab',     'Матчинг'],
  ['bridge',  'Мост тем'],
  ['props',   'Предложения'],
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
  if (r.status === 401) throw new Error('нужен пароль — введи его сверху');
  const txt = await r.text();
  let j; try { j = JSON.parse(txt); } catch(e){ throw new Error('сервер ответил не JSON: ' + txt.slice(0,160)); }
  if (!r.ok) throw new Error(j.error || ('код ' + r.status));
  return j;
}

function render(){
  /*
   * ПРОКРУТКА ЛЕНТ ПЕРЕЖИВАЕТ ПЕРЕРИСОВКУ.
   *
   * Вид собирается заново целиком каждые две с половиной секунды, и вместе с разметкой пропадала
   * прокрутка: человек отлистывал ленту вниз почитать, приходило новое сообщение — и его бросало
   * наверх. Читать в такой ленте нельзя вовсе.
   *
   * Просто вернуть прежний `scrollTop` мало: новое приходит СВЕРХУ, и содержимое под ним съезжает
   * вниз ровно на высоту добавленного. Поэтому запоминаем и высоту тоже, а после перерисовки
   * сдвигаем на прирост — тогда строка, на которую человек смотрел, остаётся на месте.
   *
   * Тот, кто стоит у самого верха, остаётся у верха: он следит за новым, и держать его на месте
   * значило бы уводить ленту из-под него.
   */
  const было = {};
  document.querySelectorAll('[data-лента]').forEach(el => {
    было[el.getAttribute('data-лента')] = { верх: el.scrollTop, высота: el.scrollHeight };
  });
  document.getElementById('nav').innerHTML = TABS.map(([k,t]) =>
    `<button class="${TAB===k?'on':''}" onclick="setTab('${k}')">${t}</button>`).join('');
  const v = document.getElementById('view');
  try { v.innerHTML = (VIEWS[TAB] || (()=>'<div class="card">нет такого раздела</div>'))(); }
  catch(e){ v.innerHTML = `<div class="card"><div class="err">не смог отрисовать: ${esc(e.message)}</div></div>`; }
  document.querySelectorAll('[data-лента]').forEach(el => {
    const b = было[el.getAttribute('data-лента')];
    if (!b) return;
    if (b.верх <= 2) { el.scrollTop = 0; return; }
    el.scrollTop = b.верх + (el.scrollHeight - b.высота);
  });
}
function setTab(k){ TAB=k; location.hash=k; render(); (LOADERS[k]||(()=>{}))(); }
function saveTok(){
  TOK = document.getElementById('tok').value.trim();
  sessionStorage.setItem('kleal_admin_tok', TOK);
  // Шапка проверяется заново: раньше она спрашивала сервер ОДИН раз при загрузке, и после
  // верного токена так и продолжала висеть «нужен токен» — панель работала, а выглядела мёртвой.
  envPill();
  (LOADERS[TAB]||(()=>{}))();
}

function envPill(){
  api('/api/admin/ping').then(r=>{
    document.getElementById('envpill').textContent =
      'хранилище: ' + (r.storage||'?') + ' · очередь: ' + (r.queue||'?');
  }).catch(()=>{ document.getElementById('envpill').textContent = 'нужен пароль'; });
}
/**
 * Ответ на действие. Раньше это был alert(): он останавливает страницу, выглядит как ошибка
 * браузера и не показывает, ЧТО именно получилось. Здесь — короткая плашка в углу, которая
 * гаснет сама, и у неё два цвета: сделано и не вышло.
 */
function toast(msg, bad){
  let b = document.getElementById('toast');
  if (!b){ b = document.createElement('div'); b.id='toast'; document.body.appendChild(b); }
  b.className = bad ? 'toast bad' : 'toast';
  b.textContent = msg;
  b.style.opacity = '1';
  clearTimeout(b._t); b._t = setTimeout(()=>{ b.style.opacity='0'; }, 3200);
}

function busy(key, on){ S[key+'_busy']=on; render(); }
function fail(key, e){ S[key+'_err']=e.message||String(e); S[key+'_busy']=false; render(); }
function errBox(key){ return S[key+'_err'] ? `<div class="err">${esc(S[key+'_err'])}</div>` : ''; }

// ---------------------------------------------------------------- Обзор
const LOADERS = {}, VIEWS = {};

/* ------------------------------------------------------------------ Батарея
 *
 * ДЕРЕВО ВМЕСТО ЛЕНТ. Прежний вид был терминалом: четыре текстовые ленты по языкам, квадратики
 * и текст диалога. Он показывал поток и прятал форму — где разговор раздваивается и как это
 * меняется круг за кругом. Теперь центр экрана — кольца (см. блок «ДЕРЕВО БАТАРЕИ» ниже): прошлые
 * круги пылью, текущий — ветками с развилками; справа веер выбранного диалога.
 *
 * ДАННЫЕ КОПЯТСЯ. Кольцо событий батарея подрезает сама, поэтому прошлые круги панель берёт из
 * склада `/api/admin/battery/tree`, который админка дописывает и не режет; живой круг — из кольца.
 *
 * И МЕНЯЮТСЯ ВЖИВУЮ. Раздел больше не пересобирается целиком на каждый ответ сервера: плитки
 * обновляются по своим местам (`батЖиво`), а рисунок правится по веткам (`деревоПатч`). Полная
 * перерисовка осталась только там, где её и ждут: переключение вкладки и нажатия человека.
 */
LOADERS.battery = async () => {
  // ОДИН ЗАПРОС ЗА РАЗ. Таймер тикает независимо от сети, и при медленном ответе запросы копились
  // друг на друга: панель съела лимит частоты в nginx и положила саму себя — 503 на /admin. Пока
  // прошлый не вернулся, новый не уходит.
  if (S.bat_busy) return;
  S.bat_busy = true;
  try {
    const r = await api('/api/admin/battery?since=' + (S.bat_since || 0));
    S.bat = r;
    S.bat_since = r.now;
    // Копим поток у себя: сервер отдаёт только новое, а глазам нужна история прокрутки.
    if (!S.bat_hold) S.bat_ev = (r.events || []).concat(S.bat_ev || []).slice(0, 3000);
    S.bat_err = '';
    // Склад ветвей — реже: он меняется раз в несколько секунд, а не каждую реплику.
    const now = Date.now();
    if (!S.tree_at || now - S.tree_at > 9000){
      S.tree_at = now;
      // ХОЛОДНЫЙ СТАРТ ПРОСИТ ПРОГОНАМИ, а не строками: прогон бывает и в 60 сценариев, и в 480,
      // и по числу строк часть дуг не приезжала — после обновления страницы картинка выглядела
      // сброшенной. Дальше идём по `since`: сервер отдаёт только новое.
      const t = await api(S.tree_since
        ? '/api/admin/battery/tree?since=' + S.tree_since + '&limit=2000'
        : '/api/admin/battery/tree?rounds=' + ДЕРЕВО.КРУГОВ);
      const m = S.tree_map || {};
      (t.branches || []).forEach(b => { m[b.scen + '@' + Math.round(b.t0)] = b; S.tree_since = Math.max(S.tree_since || 0, b.t1 || 0); });
      S.tree_map = m;
      деревоПодрезать();
    }
    // Вторая модель — реже дерева: её сводка меняется медленно, а журнал ответов дописывается
    // по одной строке. Пятнадцати секунд достаточно, чтобы не плодить запросов.
    if (!S.card_at || now - S.card_at > 15000){
      S.card_at = now;
      try { S.card = await api('/api/admin/card'); } catch(e){}
    }
  } catch (e) { S.bat_err = e.message || String(e); }
  finally { S.bat_busy = false; }
  // Вживую, а не перерисовкой: `батЖиво` возвращает false, если раздела на экране ещё нет.
  if (TAB === 'battery' && !батЖиво()) render();
};
// Свёрнутая вкладка браузера ничего не показывает — и спрашивать ей незачем: это чистый расход
// лимита. Две с половиной секунды вместо полутора: на глаз разницы нет, а запас появляется.
setInterval(() => {
  if (TAB === 'battery' && !document.hidden && !S.bat_hold) LOADERS.battery();
}, 2500);

/* В памяти панели держим столько кругов, сколько рисуем, плюс один: склад на диске полный, а
   вкладка не должна расти без конца. */
function деревоПодрезать(){
  const m = S.tree_map || {};
  const rs = {};
  Object.values(m).forEach(b => { rs[b.r || 0] = 1; });
  const keys = Object.keys(rs).map(Number).sort((a, b) => a - b);
  if (keys.length <= ДЕРЕВО.КРУГОВ + 1) return;
  const cut = keys[keys.length - ДЕРЕВО.КРУГОВ - 1];
  Object.keys(m).forEach(k => { if ((m[k].r || 0) < cut) delete m[k]; });
}

/* ГДЕ ТЫ БЫЛ — ПЕРЕЖИВАЕТ ОБНОВЛЕНИЕ СТРАНИЦЫ.
 *
 * Сами дуги возвращает склад, а вот масштаб, выбранный разговор, отбор по виду беды и строку
 * поиска держала только память вкладки: F5 — и человек оказывался «нигде», с полным кругом вместо
 * места, куда он приблизился (сообщено владельцем 17.09.2026). Кладём это в sessionStorage: он
 * живёт до закрытия вкладки, как и токен панели, и не тащит вчерашнее состояние в новый день. */
const БАТ_ПАМЯТЬ = ['tree_vb', 'bat_pick', 'bat_kind', 'bat_q', 'bat_flow'];
function батЗапомнить(){
  try { sessionStorage.setItem('kleal_bat', JSON.stringify(
    БАТ_ПАМЯТЬ.reduce((o, k) => (S[k] === undefined || S[k] === '' ? o : (o[k] = S[k], o)), {}))); }
  catch (e) { /* приватный режим — переживём без памяти */ }
}
/* Вспоминаем ЛЕНИВО, перед первой сборкой вида, а не по порядку скриптов: вызов на месте
   объявления отрабатывал раньше, чем надо, и первая картинка успевала нарисоваться с полным
   кругом — масштаб «возвращался» только со второй перерисовки. */
function батВспомнить(){
  if (S._вспомнил) return;
  S._вспомнил = 1;
  try { Object.assign(S, JSON.parse(sessionStorage.getItem('kleal_bat') || '{}')); } catch (e) {}
  if (S.bat_pick) деревоРечь(S.bat_pick);
}

function batHold(){ S.bat_hold = !S.bat_hold; render(); }
// Поиск и выбор вида беды НЕ перерисовывают раздел: иначе поле теряет курсор на каждой букве.
function batSearch(el){ S.bat_q = el.value; clearTimeout(window._bq); window._bq = setTimeout(() => { батЗапомнить(); батЖиво(); }, 200); }
function batВид(k){ S.bat_kind = (S.bat_kind === k ? '' : k); батЗапомнить(); батЖиво(); }
/* `ключ` — это «сценарий@время», а не метка сценария: пул переиспользуется, и одна метка лежит в
   складе столько раз, сколько прогонов её гоняли. По метке из новой дуги открывалась копия из
   старой, где реплик ещё не писали (со снимка владельца 17.09.2026). */
function batPick(ключ){
  S.bat_pick = (S.bat_pick === ключ ? '' : ключ);
  батЗапомнить();
  батЖиво();
  if (S.bat_pick) деревоРечь(S.bat_pick);
}
function ключМетка(k){ return String(k || '').split('@')[0]; }
function ключВремя(k){ const t = String(k || '').split('@')[1]; return t ? +t : null; }

/* РЕПЛИКИ ВЫБРАННОЙ ВЕТКИ. Кольцо событий у панели короткое: для ветки из прошлого круга в нём
   остаётся одна-две строки, и разговор выглядел «из одного слова» (снято владельцем 17.09.2026).
   Слова лежат в складе; просим их РОВНО для той ветки, по которой щёлкнули, и запоминаем. */
async function деревоРечь(ключ){
  S.talk = S.talk || {};
  if (S.talk[ключ] || S.talk['@' + ключ]) return;
  S.talk['@' + ключ] = 1;                       // отметка «уже спросили», чтобы не долбить сервер
  try {
    const t0 = ключВремя(ключ);
    const r = await api('/api/admin/battery/tree?scen=' + encodeURIComponent(ключМетка(ключ)) +
                        (t0 ? '&t0=' + t0 : ''));
    if (r && r.branch) S.talk[ключ] = r.branch;
  } catch (e) { /* не вышло — покажем то, что есть в кольце */ }
  батЖиво();
}
function batПоток(){ S.bat_flow = !S.bat_flow; батЗапомнить(); render(); }

/* Все ветви, что есть у панели: склад плюс живые. */
function деревоВетви(){
  return слитьВетви(Object.values(S.tree_map || {}), ветвиИзКольца(S.bat_ev || []));
}

/* Плитка. Разметка повторяет приём из рабочего терминала владельца (папка TRADE): ручка ⣿,
   имя капсом, хвост справа, тонкая внутренняя рамка вместо тени. Плотность там главное: шапка
   в 10.5px, тело без лишних отступов. `id` нужен живому обновлению: по нему находят тело. */
function батПлитка(name, tail, body, span, tall, id){
  /* ИМЯ НЕ `tile`. В панели уже есть своя `tile(k, v, s, cls)` — она ЭКРАНИРУЕТ содержимое, а в
     JavaScript объявленная позже функция побеждает объявленную раньше. Мои вызовы молча уходили
     в чужую, и тело плитки приезжало на экран текстом: «<div class="кв-сетка">…». Снято со
     скриншота владельца. Общее имя в общем файле — это не стиль, это столкновение. */
  return '<section class="пан" style="grid-column:span ' + (span || 4) + (tall ? ';grid-row:span ' + tall : '') + '">' +
    '<header class="пан-шапка"><i class="пан-ручка">⣿</i><span class="пан-имя">' + name + '</span>' +
    '<span class="пан-хвост"' + (id ? ' id="' + id + '-хвост"' : '') + '>' + (tail || '') + '</span></header>' +
    '<div class="пан-тело"' + (id ? ' id="' + id + '"' : '') + '>' + body + '</div></section>';
}

/* Ломаная знаками: восемь уровней, один знак — один круг. */
function sparkText(vals, n){
  const B = '▁▂▃▄▅▆▇█';
  const v = (vals || []).filter(x => typeof x === 'number' && isFinite(x)).slice(-(n || 40));
  if (!v.length) return '—';
  const max = Math.max.apply(null, v), min = Math.min.apply(null, v);
  const span = (max - min) || 1;
  return v.map(x => B[Math.min(7, Math.floor((x - min) / span * 7.999))]).join('');
}

/* Столбик знаками: доля от максимума. */
function barText(val, max, width){
  const w = width || 14;
  const n = max > 0 ? Math.round(val / max * w) : 0;
  return '█'.repeat(n) + '░'.repeat(Math.max(0, w - n));
}

function padEnd(s, n){ s = String(s); return s.length >= n ? s.slice(0, n) : s + ' '.repeat(n - s.length); }
function padStart(s, n){ s = String(s); return s.length >= n ? s : ' '.repeat(n - s.length) + s; }

function sumKinds(rounds, n){
  const acc = {};
  (rounds || []).slice(-n).forEach(r => Object.entries(r.kinds || {}).forEach(([k, v]) => { acc[k] = (acc[k] || 0) + v; }));
  return Object.entries(acc).sort((a, b) => b[1] - a[1]);
}
function sumPairs(rounds, field, n){
  const acc = {};
  (rounds || []).slice(-n).forEach(r => Object.entries(r[field] || {}).forEach(([k, v]) => {
    acc[k] = acc[k] || {bad: 0, all: 0};
    acc[k].bad += (v['бед'] || 0); acc[k].all += (v['всего'] || 0);
  }));
  return Object.entries(acc).sort((a, b) => b[1].bad - a[1].bad);
}

/* Одна строка потока. Колонки фиксированы: время · сценарий · знак · текст. */
function termLine(e){
  const t = new Date((e.t || 0) * 1000).toLocaleTimeString('ru');
  const sc = padEnd(e.scen || '', 18);
  const head = '<span class="t-dim">' + t + '</span> <span class="t-scen">' + esc(sc) + '</span> ';
  if (e.kind === 'human')
    return '<div class="t-row"><span class="t-you">▸</span> ' + head + '<span class="t-you">' + esc(e.text) + '</span></div>';
  if (e.kind === 'kleal')
    return '<div class="t-row t-k"><span class="t-dim">◂</span> ' + head + '<span class="t-ai">' + esc(e.text) + '</span></div>';
  if (e.kind === 'intent')
    return '<div class="t-row t-ok"><span class="t-okm">✔</span> ' + head + '<b>' + esc(e.text) + '</b>' +
      '<div class="t-sub">' + esc((e.topics || []).join(' · ')) + ' │ ход ' + e.turns + ' │ вопросов ' + e.questions +
      (e.hard ? ' │ сложность ' + e.hard : '') + (e.src === 'gen' ? ' │ нейронка' : ' │ своё') + '</div></div>';
  if (e.kind === 'problem'){
    const m = String(e.text || '').match(/^([А-ЯЁ ]+):\s*(.*)$/);
    const kind = m ? m[1] : 'БЕДА', rest = m ? m[2] : e.text;
    return '<div class="t-row t-bad"><span class="t-badm" style="color:' + краскаБеды(kind) + '">✖</span> ' + head +
      '<span class="t-tag" style="color:' + краскаБеды(kind) + ';box-shadow:inset 0 0 0 1px ' + краскаБеды(kind) + '66">' +
      esc(kind) + '</span> ' + esc(rest) + '</div>';
  }
  if (e.kind === 'result' || e.kind === 'scen_start' || e.kind === 'scen_done') return '';
  if (e.kind === 'run_start')
    return '<div class="t-sep">── круг: ' + e.scen + ' сценариев · ' + e.workers + ' потоков · пул ' + e.pool + ' ──</div>';
  if (e.kind === 'run_done')
    return '<div class="t-sep">── круг окончен: бед ' + e.bad + ' · вызовов ' + e.calls + ' · ' + e.min + ' мин ──</div>';
  return '';
}

/* ── ТЕЛА ПЛИТОК ОТДЕЛЬНЫМИ ФУНКЦИЯМИ ─────────────────────────────────────────────────────────
 * Каждая строит СВОЁ тело и ничего не знает про остальные. Так одна и та же разметка годится и
 * первой отрисовке (`VIEWS.battery`), и живому обновлению (`батЖиво`), и они не могут разойтись. */
function батПрогон(b, R, last, avg){
  const kv = (k, v) => '<div class="кв-стр"><i>' + k + '</i><b>' + v + '</b></div>';
  return '<div class="кв-сетка">' +
    kv('БЕД В КРУГЕ', (last ? last.bad : '—') + ' <span class="т-искра">' + sparkText(R.map(r => r.bad), 24) + '</span>') +
    kv('СРЕДНЕЕ ЗА 10', avg) +
    kv('СОБРАНО', last ? last.built + ' / ' + last.scen : '—') +
    kv('ПОТОКОВ', last ? last.workers : '—') +
    kv('P50 · P95', last ? last.median + 'с · ' + last.p95 + 'с' : '—') +
    kv('ЗАДЕРЖКА', '<span class="т-искра">' + sparkText(R.map(r => r.p95), 24) + '</span>') +
    kv('СБОЕВ', last ? last.errors : '—') +
    kv('ПУЛ', (b.pool || 0) + ' сц.') +
    kv('КРУГОВ', R.length) +
    kv('ДЛИТ. КРУГА', last ? last.min + ' мин' : '—') +
    '</div>' + (S.bat_err ? '<div class="т-вниз">' + esc(S.bat_err) + '</div>' : '');
}

/* ВИДЫ БЕД — В СВОИХ КРАСКАХ, И ЭТО ЖЕ ВЫБОР. Столбик красится тем цветом, каким этот вид
   нарисован в кольцах; нажатие оставляет в кольцах только его — остальные гаснут. */
function батВиды(R){
  const kinds = sumKinds(R, 10), kmax = kinds.length ? kinds[0][1] : 1;
  if (!kinds.length) return '<div class="т-тихо">— чисто —</div>';
  return kinds.map(([k, v]) => {
    const c = краскаБеды(k), on = S.bat_kind === k;
    return '<div class="т-бар вид-стр' + (on ? ' вкл' : '') + '" onclick="batВид(&#39;' + k.replace(/'/g, '') + '&#39;)">' +
      '<i class="вид-точка" style="background:' + c + '"></i>' + padEnd(k, 19) +
      ' <span class="т-барв" style="color:' + c + '">' + barText(v, kmax, 10) + '</span> ' + padStart(v, 4) + '</div>';
  }).join('');
}

function батБолит(R){
  const cut = rows => rows.map(([k, v]) =>
    '<div class="т-бар">' + padEnd(k, 9) + ' <span class="т-барв">' + barText(v.bad, Math.max(1, v.all), 8) +
    '</span> ' + padStart(v.bad + '/' + v.all, 7) + ' <span class="т-тихо">' +
    (v.all ? padStart(Math.round(v.bad / v.all * 100) + '%', 4) : '') + '</span></div>').join('') ||
    '<div class="т-тихо">— нет данных —</div>';
  return '<div class="т-тихо т-подпись">ЯЗЫК</div>' + cut(sumPairs(R, 'langs', 10)) +
    '<div class="т-тихо т-подпись">СЛОЖНОСТЬ</div>' + cut(sumPairs(R, 'hards', 10)) +
    '<div class="т-тихо т-подпись">СВОИ / НЕЙРОНКА</div>' + cut(sumPairs(R, 'src', 10));
}

function батКруги(b){
  const hist = (b.history || []).slice().reverse().slice(0, 9).map(r =>
    '<div class="т-строка">' + padEnd(String(r[0]).slice(-5), 6) + padStart(r[2], 5) +
    ' <span class="' + ((+r[3]) > 0 ? 'т-вниз' : 'т-вверх') + '">' + padStart(r[3], 5) + '</span>' +
    padStart(r[7] + 'с', 7) + padStart(r[8], 4) + '</div>').join('');
  return '<div class="т-строка т-тихо">' + padEnd('ВРЕМЯ', 6) + padStart('СОБР', 5) + padStart('БЕД', 6) +
    padStart('P95', 7) + padStart('СБОЙ', 4) + '</div>' +
    (hist || '<div class="т-тихо">— кругов ещё не было —</div>');
}

/* Что означает цвет — прямо под рисунком, с числами ЭТОГО круга. */
function батЛегенда(L){
  const счёт = {};
  L.cur.branches.forEach(b => b.kinds.forEach(k => { счёт[k] = (счёт[k] || 0) + 1; }));
  const виды = Object.entries(счёт).sort((a, b) => b[1] - a[1]).map(([k, v]) =>
    '<span class="л-вид' + (S.bat_kind === k ? ' вкл' : '') + '" onclick="batВид(&#39;' + k.replace(/'/g, '') + '&#39;)">' +
    '<i style="background:' + краскаБеды(k) + '"></i>' + esc(k.toLowerCase()) + ' ' + v + '</span>').join('');
  return '<div class="д-легенда">' +
    '<span class="л-вид"><i style="background:' + ЦВЕТ_ЧИСТО + '"></i>чисто ' + (L.cur.done - L.cur.bad) + '</span>' +
    '<span class="л-вид"><i style="background:' + ЦВЕТ_ИДЁТ + '"></i>идёт ' + (L.cur.n - L.cur.done) + '</span>' +
    виды + (S.bat_kind ? '<span class="л-сброс" onclick="batВид(&#39;&#39;)">× снять отбор</span>' : '') +
    '<span class="т-тихо л-помощь">⌘/Ctrl+колесо или кнопки — масштаб · тянуть — сдвиг · щелчок по ветке — диалог</span></div>';
}

/* ДИАЛОГ: веер сверху, реплики и итог под ним. Для ветви из склада, чьи реплики уже вышли из
   кольца, — только форма и заголовки, и об этом сказано словами. */
function батДиалог(branches){
  const pick = S.bat_pick;
  if (!pick) return '<div class="т-тихо">— щёлкни ветку в кольцах —</div>';
  let b = branches.find(x => (x.scen + '@' + Math.round(x.t0)) === pick) || branches.find(x => x.scen === pick);
  if (!b) return '<div class="т-тихо">— ветка ' + esc(ключМетка(pick)) + ' уже вышла из памяти панели —</div>';
  // Ветка из колец идёт без слов; если склад их прислал — берём оттуда.
  // Из колец ветвь приходит сухой (там нужна только форма); со склада — целиком, с репликами,
  // темами, предметом и текстами бед. Целая побеждает.
  const речь = (S.talk || {})[pick];
  if (речь && речь.turns) b = Object.assign({}, b, речь);
  const head = '<div class="д-загол">' + esc(b.scen) + ' <span class="т-тихо">· ' + (b.lang || '') +
    (b.hard ? ' · сложность ' + b.hard : '') + (b.src === 'gen' ? ' · нейронка' : ' · своё') + '</span>' +
    (b.done ? ' <span style="color:' + краскаВетви(b) + '">· ' + (b.bad ? esc((b.problems[0] || {}).kind || 'с бедой').toLowerCase() : 'чисто') +
      (b.t1 && b.t0 ? ' · ' + (b.t1 - b.t0).toFixed(1) + 'с' : '') + '</span>' : ' <span class="т-охра">· идёт</span>') +
    '</div>';
  const fan = svgВеер(b);

  /* РАЗГОВОР СТРОИТСЯ ИЗ САМОЙ ВЕТКИ, А НЕ ИЗ КОЛЬЦА СОБЫТИЙ. Раньше строки брались из живого
     кольца — и у старой ветки их там уже не было. Теперь ходы, беды и затея приходят одним и тем
     же путём для любой ветки: свежей, старой, складской. */
  let ход = 0;
  const строки = (b.turns || []).map(t => {
    if (t.k === 'h'){ ход++;
      return '<div class="t-row реч чел"><span class="кто кто-чел">ЧЕЛОВЕК</span>' +
        '<span class="t-dim">ход ' + ход + '</span> <span class="t-you">' + esc(t.txt || '—') + '</span></div>'; }
    return '<div class="t-row t-k реч бот"><span class="кто кто-бот">KLEAL</span>' +
      (t.ready ? '<span class="т-вверх">попап ✔</span> ' : '') + '<span class="t-ai">' + esc(t.txt || '—') + '</span></div>';
  }).join('');
  const беды = (b.problems || []).map(p =>
    '<div class="t-row t-bad"><span class="t-badm" style="color:' + краскаБеды(p.kind) + '">✖</span> ' +
    '<span class="t-tag" style="color:' + краскаБеды(p.kind) + ';box-shadow:inset 0 0 0 1px ' + краскаБеды(p.kind) + '66">' +
    esc(p.kind) + '</span> ' + esc(p.text) + '</div>').join('');
  /* РЯД ПРОЧЕРКОВ — ХУЖЕ ЧЕСТНОГО «НЕ СОХРАНИЛОСЬ». Склад начал писать реплики 17.09.2026 в 16:36;
     у прогонов старше их нет НИГДЕ: кольцо событий давно прокрутилось, а журналы батареи пишут 64
     потока разом и по метке разговор из них не достать. Форму разговора, беды и итог показываем —
     они в складе есть, — а про слова говорим прямо. */
  const немо = !(b.turns || []).some(t => t.txt);
  const body = немо
    ? '<div class="т-тихо">' + (речь === undefined ? '— спрашиваю реплики у склада… —'
        : '— реплики этого этапа не сохранились: склад начал их писать позже. Форма разговора, ' +
          'беды и итог ниже — они на месте. —') + '</div>' + беды
    : строки + беды;

  /* ИТОГ РАЗГОВОРА — КАК ЗАТЕЮ НАЗОВУТ В КАЖДОМ ОКНЕ. Одна затея показывается человеку в разных
     местах, и каждое берёт имя своим путём: мастер — из ответа сборщика, попап «С чего начнём?» —
     из ответа разговорной ручки. Здесь они стоят рядом, потому что расхождение между ними и есть
     беда, которую иначе не увидеть. */
  let itog = '';
  if (b.master || b.done){
    const m = b.master || {}, p = b.popup;
    const стр = (k, v, cls) => '<div class="и-стр"><i>' + k + '</i><b class="' + (cls || '') + '">' + v + '</b></div>';
    const разошлись = !!(p && p.title && m.title && p.title.trim().toLowerCase() !== m.title.trim().toLowerCase());
    itog = '<div class="и-итог"><div class="и-загол">ИТОГ</div>' +
      стр('МАСТЕР ЗАТЕИ', esc(m.title || '—'), разошлись ? 'т-вниз' : 'т-вверх') +
      стр('ПРЕДМЕТ · ГЛАГОЛ', esc((m.subject || '—') + ' · ' + (m.role || '—'))) +
      (b.intent ? стр('ТЕМЫ', esc((b.intent.topics || []).join(', ') || '—')) : '') +
      (p ? стр('ПОПАП У БАДДИ', esc(p.title), разошлись ? 'т-вниз' : 'т-вверх') +
           стр('СРАБОТАЛ', 'на ходу ' + b.fired + ' из ' + b.turns_said)
         : стр('ПОПАП У БАДДИ', 'НЕ СРАБОТАЛ — в разговоре затея не распозналась', 'т-вниз')) +
      (разошлись ? '<div class="т-вниз и-ворч">имена расходятся: человек увидит одну затею под двумя названиями</div>' : '') +
      '</div>';
  }
  return head + fan + '<div class="д-диалог">' + body + itog + '</div>';
}

/* Числа сердца. Берём их из истории прогонов, а «этапов пройдено» и «разговоров в складе» —
   с сервера: дуг на экране шестнадцать, а прогонов за сутки бывает две сотни. */
function батЦентр(L, last){
  const b = S.bat || {}, R = b.rounds || [];
  return svgСердце({
    этапов: b.rounds_total || R.length || 0,
    бед: last ? last.bad : (L.cur.bad || 0),
    беды: R.map(r => r.bad),
    p95: last ? last.p95 : '—',
    p95р: R.map(r => r.p95),
    p50: last ? last.median : '—',
    вызовов: last ? num(last.calls) : '—',
    сбоев: last ? last.errors : 0,
    потоков: last ? last.workers : '—',
    мин: last ? last.min : '—',
    собрано: last ? last.built : L.cur.done,
    сцен: last ? last.scen : L.cur.n,
    разговоров: num(b.talks || 0),
    пул: num(b.pool || 0),
  });
}

function батПоле(){
  батВспомнить();
  const b = S.bat || {}, R = b.rounds || [];
  const last = R.length ? R[R.length - 1] : null;
  const ten = R.slice(-10);
  const avg = ten.length ? (ten.reduce((s, r) => s + (r.bad || 0), 0) / ten.length).toFixed(1) : '—';
  const branches = деревоВетви();
  const L = раскладкаКолец(кругиИзВетвей(branches));
  return {b, R, last, avg, branches, L};
}

/* ЖИВОЕ ОБНОВЛЕНИЕ. Возвращает false, если раздела на экране нет — тогда зовущий делает render(). */
function батЖиво(){
  const кольца = document.getElementById('бат-кольца');
  if (!кольца || TAB !== 'battery') return false;
  const {b, R, last, avg, branches, L} = батПоле();
  const пиши = (id, html) => { const el = document.getElementById(id); if (el && el.innerHTML !== html) el.innerHTML = html; };
  пиши('бат-прогон', батПрогон(b, R, last, avg));
  пиши('бат-виды', батВиды(R));
  пиши('бат-болит', батБолит(R));
  пиши('бат-круги', батКруги(b));
  пиши('бат-легенда', батЛегенда(L));
  пиши('бат-диалог', батДиалог(branches));
  пиши('бат-диалог-хвост', S.bat_pick ? esc(ключМетка(S.bat_pick)) : 'ничего не выбрано');
  пиши('бат-кольца-тело-хвост', L.cur.n + ' веток в круге · ' + L.прошлые.length + ' прогонов дугами');
  пиши('бат-прогон-хвост', b.alive ? '<span class="т-вверх">● ИДЁТ</span>' : '<span class="т-вниз">● МОЛЧИТ</span>');
  if (S.bat_flow) пиши('бат-поток', батПотокТело());
  return деревоПатч(L, батЦентр(L, last), S.bat_pick, S.bat_q, S.bat_kind);
}

function батПотокТело(){
  const q = String(S.bat_q || '').toLowerCase();
  let ev = (S.bat_ev || []);
  if (q) ev = ev.filter(e => ((e.text || '') + ' ' + (e.scen || '')).toLowerCase().includes(q));
  if (!S.bat_flow) return '<div class="т-тихо">' + ev.length + ' событий в памяти</div>';
  return '<div class="т-лента т-лента-низ" data-лента="все">' +
    (ev.slice(0, 200).map(termLine).join('') || '<div class="т-тихо">— тихо —</div>') + '</div>';
}

VIEWS.battery = () => {
  const {b, R, last, avg, branches, L} = батПоле();
  const st = b.alive ? '<span class="т-вверх">● ИДЁТ</span>' : '<span class="т-вниз">● МОЛЧИТ</span>';

  const bar = '<div class="т-полоса">' +
    '<input class="т-поле" placeholder="искать ветку: сценарий, затея, слова…" value="' + esc(S.bat_q || '') + '" oninput="batSearch(this)">' +
    '<button class="т-кн" onclick="деревоМасштаб(1/1.35)">＋ БЛИЖЕ</button>' +
    '<button class="т-кн" onclick="деревоМасштаб(1.35)">－ ДАЛЬШЕ</button>' +
    '<button class="т-кн" onclick="деревоСброс()">⟲ ВЕСЬ КРУГ</button>' +
    '<button class="т-кн' + (S.bat_hold ? ' вкл' : '') + '" onclick="batHold()">' +
      (S.bat_hold ? '▶ ПРОДОЛЖИТЬ' : '⏸ ОСТАНОВИТЬ') + '</button></div>';

  // Пыль кэшируется по составу кругов: перерисовывать её каждый тик незачем.
  const key = L.прошлые.map(d => d.r + ':' + d.n).join('|');
  if (S.tree_hist_key !== key){ S.tree_hist_key = key; S.tree_hist_svg = svgПрошлые(L.прошлые, L.sectors, L.cx, L.cy); }

  return '<div class="терм">' + bar + '<div class="т-сетка">' +
    батПлитка('ПРОГОН', st, батПрогон(b, R, last, avg), 3, 0, 'бат-прогон') +
    батПлитка('ВИДЫ БЕД', '10 кругов · нажми', батВиды(R), 3, 0, 'бат-виды') +
    батПлитка('ГДЕ БОЛИТ', '10 кругов', батБолит(R), 3, 0, 'бат-болит') +
    батПлитка('КРУГИ', 'последние 9', батКруги(b), 3, 0, 'бат-круги') +
    батПлитка('КОЛЬЦА', L.cur.n + ' веток в круге · ' + L.прошлые.length + ' прогонов дугами',
      '<div id="бат-кольца">' + svgКольца(L, батЦентр(L, last), S.bat_pick, S.bat_q, S.tree_hist_svg, S.bat_kind) + '</div>' +
      '<div id="бат-легенда">' + батЛегенда(L) + '</div>', 8, 2, 'бат-кольца-тело') +
    батПлитка('ДИАЛОГ', S.bat_pick ? esc(ключМетка(S.bat_pick)) : 'ничего не выбрано', батДиалог(branches), 4, 2, 'бат-диалог') +
    батПлитка('ПОТОК', '<a class="т-ссылка" onclick="batПоток()">' + (S.bat_flow ? 'свернуть' : 'развернуть') + '</a>',
      батПотокТело(), 12, 0, 'бат-поток') +
    разборПлитки() +
    '</div></div>';
};

/*@дерево-начало*/
/* ── ДЕРЕВО БАТАРЕИ: ГОДОВЫЕ КОЛЬЦА И ВЕЕР ДИАЛОГА ────────────────────────────────────────────
 *
 * ЗАЧЕМ ДЕРЕВО, А НЕ ЛЕНТЫ. Ленты показывали ПОТОК и прятали ФОРМУ: где разговор раздваивается —
 * сработал попап или промолчал, собралась затея или нет, назвали ли мастер и попап одно и то же.
 * По просьбе владельца (17.09.2026, с тремя референсами): каждый диалог — своя ветка/точка, каждое
 * расхождение потока — развилка, и данные КОПЯТСЯ, а не перезаписываются.
 *
 * ОДНА ДУГА — ОДИН ПРОГОН (владелец, 17.09.2026). Дуги идут от середины наружу, старший прогон
 * внутри; между двумя соседними дугами лежат ВСЕ РАЗГОВОРЫ этого прогона — каждый своим штрихом,
 * который можно открыть и почитать. Середина остаётся ПУСТОЙ: там только счёт текущего прогона.
 * Кончился прогон — снаружи появляется новая дуга, и разговоры копятся в её полосе; нарисованное
 * не стирается и не сдвигается. Прошлые дуги приходят из склада `/api/admin/battery/tree` (его
 * дописывает админка и никогда не режет), текущая полоса — из живого кольца событий.
 *
 * ТЕКУЩАЯ ПОЛОСА ШИРЕ прошлых: за ней и смотрят, и только в ней есть место показать ход за ходом,
 * развилку попапа и два листа. У прошлых остаются ствол (длина — сколько ходов прожил разговор),
 * точка попапа и цвет исхода; всё остальное читается, когда разговор откроют.
 *
 * РАЗВИЛКИ ТОЛЬКО ИЗ ДАННЫХ, ничего придуманного:
 *   ready  — ход, на котором сервер распознал затею (попап у Бадди): яркий узел, от него отросток
 *            к узлу затеи;
 *   result — в конце два листа, мастер и попап: два чтения одного разговора. Разошлись именами —
 *            красная перемычка; попап молчал — второго листа нет, обрыв видно.
 * Беды — красные узлы у листа; если в тексте есть «на ходу N», узел встаёт на этот ход.
 *
 * INLINE-SVG БЕЗ БИБЛИОТЕК: панель открывают с бокса, где сети наружу может не быть (правило файла).
 * Раскладка — чистые функции «события → ветви → координаты», их гоняет тест в node на фикстуре.
 * Кольца пыли рисуются один раз и кэшируются строкой: 11 тысяч точек перерисовывать каждые две с
 * половиной секунды незачем; живое кольцо перерисовывается каждый тик.
 */
const ДЕРЕВО = {
  КРУГОВ: 16,          // сколько прогонов держать дугами на экране (склад держит всё)
  ВЬЮ: 1000,           // сторона viewBox
  R0: 160,             // где начинается первая дуга: СЕРЕДИНА ОСТАЁТСЯ ПУСТОЙ
  ПОЛОСА: 17,          // ширина полосы одного прошлого прогона
  ТЕК_ПОЛОСА: 30,      // текущий прогон шире: за ним и смотрят
  ХОДОВ_МАКС: 8,       // больше ходов на длину ствола не влияют
  ЗАЗОР: 3 * Math.PI / 180,   // зазор между секторами языков
  РАЗРЫВ_КРУГА: 120,   // с: ветви без отметки прогона группируем по разрыву во времени
};
const ДЕРЕВО_СЕКТОРА = [['ru', 'RU'], ['en', 'EN'], ['es', 'ES']];
const ДЕРЕВО_НА_ХОДУ = /на ходу (\d+)/;

/* ЦВЕТ — ЭТО ВИД БЕДЫ, А НЕ УКРАШЕНИЕ.
 *
 * Пока беда была одного красного цвета, кольцо отвечало только на вопрос «сколько», а главный
 * вопрос круга — «чего именно». Теперь у каждого вида своя краска, и она одна и та же ВЕЗДЕ:
 * столбик в «Видах бед», узел на ветке, точка в кольце прошлого круга, подпись в диалоге. Кольцо
 * читается с одного взгляда: фиолетовое — молчит попап, малиновое — затея не про то.
 *
 * Краски разведены по тону, а не по яркости: рядом стоят сотни точек в две-три единицы, и разница
 * в светлоте на чёрном не видна. Виды, которых в списке нет, получают серый — это честнее, чем
 * молча покрасить их в чужой цвет. */
const КРАСКИ = {
  'ЗАТЕЯ НЕ ПРО ТО':    '#ff4d6d',
  'ВЗЯЛ ОТВЕРГНУТОЕ':   '#ff9f43',
  'ПОПАП НЕ СРАБОТАЛ':  '#a879ff',
  'БЕЗ ПРЕДМЕТА':       '#ffd93d',
  'ПРЕДМЕТ НИОТКУДА':   '#ff6fb5',
  'ИМЕНА РАСХОДЯТСЯ':   '#4dc9ff',
  'ЛИШНИЕ ВОПРОСЫ':     '#5ee7c4',
  'НЕ СОБРАЛАСЬ':       '#8e9bb3',
  'ПОВТОР ВОПРОСА':     '#c9a227',
  'ПРЕДМЕТ ИЗ ОТКАЗА':  '#e8563f',
  'ПРЕДМЕТ-МУСОР':      '#e879a6',
  'МУСОР В ТЕМАХ':      '#b5a06b',
  'МУСОР В ЧИПАХ':      '#d4a05f',
  'РАСПИСКА НЕ ПРО ТО': '#f0a5ff',
  'ЧУЖОЙ ЯЗЫК':         '#7dd3fc',
  'АНГЛ В РУССКОМ':     '#60a5fa',
  'СЕТЬ':               '#6b7280',
};
const ЦВЕТ_ЧИСТО = '#3ecf8e', ЦВЕТ_ИДЁТ = '#d9a83a', ЦВЕТ_ПРОЧЕЕ = '#9aa0b5';
function краскаБеды(kind){ return КРАСКИ[String(kind || '').trim()] || ЦВЕТ_ПРОЧЕЕ; }
/* Цвет ветки — по ПЕРВОЙ беде: она и есть та, из-за которой разговор пошёл не туда. */
function краскаВетви(b){
  if (!b.done) return ЦВЕТ_ИДЁТ;
  return b.problems && b.problems.length ? краскаБеды(b.problems[0].kind) : ЦВЕТ_ЧИСТО;
}

/* События одного сценария → ветвь. ТА ЖЕ форма, что у `branch_from_events` в battery_tree.py,
   плюс `txt` у ходов — для живого кольца тексты ещё есть. Порядок событий в кольце не всегда
   хронологический по смыслу: `intent` и `problem` бывают ПОСЛЕ `scen_done`, поэтому складываем по
   видам, а не по позиции. */
function ветвьИзСобытий(events, roundT){
  const ev = (events || []).slice().sort((a, b) => (a.t || 0) - (b.t || 0));
  const start = ev.find(e => e.kind === 'scen_start');
  const dones = ev.filter(e => e.kind === 'scen_done');
  const done = dones.length ? dones[dones.length - 1] : null;
  const turns = [];
  let readyAt = 0, humans = 0;
  for (const e of ev){
    if (e.kind === 'human'){ humans++; turns.push({k: 'h', ready: 0, txt: String(e.text || '')}); }
    else if (e.kind === 'kleal'){
      const r = e.ready ? 1 : 0;
      turns.push({k: 'k', ready: r, txt: String(e.text || '')});
      if (r && !readyAt) readyAt = humans;
    }
  }
  const its = ev.filter(e => e.kind === 'intent');
  let intent = null;
  if (its.length){
    const i = its[its.length - 1];
    intent = {title: String(i.text || '').slice(0, 80), subject: String(i.subject || '').slice(0, 40),
              topics: (i.topics || []).slice(0, 6).map(x => String(x).slice(0, 24)),
              at: +(i.turns || readyAt || 0)};
  }
  const rs = ev.filter(e => e.kind === 'result');
  const res = rs.length ? rs[rs.length - 1] : null;
  let master = null, popup = null, fired = 0, turnsSaid = 0;
  if (res){
    const m = res.master || {};
    master = m.title ? {title: String(m.title).slice(0, 80), subject: String(m.subject || '').slice(0, 40),
                        role: String(m.role || '').slice(0, 20)} : null;
    popup = res.popup ? {title: String(res.popup.title || '').slice(0, 80)} : null;
    fired = +(res.fired || 0); turnsSaid = +(res.turns_said || 0);
  }
  const problems = [];
  for (const e of ev){
    if (e.kind !== 'problem') continue;
    const txt = String(e.text || '');
    const m = txt.match(/^([А-ЯЁ\- ]+):\s*(.*)$/);
    const kind = m ? m[1].trim() : 'БЕДА', rest = m ? m[2] : txt;
    const at = rest.match(ДЕРЕВО_НА_ХОДУ);
    problems.push({kind: kind.slice(0, 32), at: at ? +at[1] : null, text: rest.slice(0, 120)});
  }
  const src = start || done || ev[0] || {};
  const t0 = +((done && done.t0) || (start && start.t) || (ev[0] && ev[0].t) || 0);
  const t1 = ev.length ? +(ev[ev.length - 1].t || 0) : 0;
  return {scen: String(src.scen || ''), lang: String(src.lang || ''), hard: +(src.hard || 0),
          src: String(src.src || ''), r: +(roundT || 0), t0, t1, turns, intent, fired,
          turns_said: turnsSaid, master, popup, problems,
          // `bad` в scen_done пишется ДО проверки попапа: там 0 при живой беде.
          bad: Math.max(+((done && done.bad) || 0), problems.length), done: !!done};
}

/* Живое кольцо событий → ветви, включая НЕЗАКОНЧЕННЫЕ: они и есть рост дерева. Круг ветви — тот,
   в котором она началась. */
function ветвиИзКольца(events){
  const by = {}, roundOf = {};
  let roundT = 0;
  for (const e of (events || []).slice().sort((a, b) => (a.t || 0) - (b.t || 0))){
    if (e.kind === 'run_start'){ roundT = +(e.t || 0); continue; }
    if (!e.scen) continue;
    (by[e.scen] = by[e.scen] || []).push(e);
    if (!(e.scen in roundOf)) roundOf[e.scen] = roundT;
  }
  return Object.keys(by).map(s => ветвьИзСобытий(by[s], roundOf[s]));
}

/* Склад + живое: живая ветвь того же сценария побеждает складскую — у неё есть тексты и она может
   быть свежее; складская побеждает, когда живой уже нет (реплики вышли из кольца). */
function слитьВетви(store, live){
  const m = {};
  (store || []).forEach(b => { m[b.scen + '@' + Math.round(b.t0)] = b; });
  (live || []).forEach(b => {
    // Живая ветвь без scen_start и без ходов — обрывок хвоста кольца; складская полнее.
    const k = b.scen + '@' + Math.round(b.t0);
    if (m[k] && !b.turns.length) return;
    m[k] = b;
  });
  return Object.values(m);
}

/* Ветви → круги, от старшего к младшему. Отметка круга `r` — время run_start; ветви с r=0 (до
   первой отметки в хвосте) режутся по разрыву во времени между стартами. */
function кругиИзВетвей(branches){
  const rounds = {};
  const orphans = [];
  for (const b of branches){ if (b.r) (rounds[b.r] = rounds[b.r] || []).push(b); else orphans.push(b); }
  const out = Object.keys(rounds).map(r => ({r: +r, branches: rounds[r]}));
  orphans.sort((a, b) => a.t0 - b.t0);
  let cur = null;
  for (const b of orphans){
    if (!cur || b.t0 - cur.last > ДЕРЕВО.РАЗРЫВ_КРУГА){ cur = {r: -b.t0, branches: [], last: b.t0}; out.push(cur); }
    cur.branches.push(b); cur.last = b.t0;
  }
  out.forEach(c => { delete c.last; c.t = Math.min.apply(null, c.branches.map(b => b.t0));
                     c.branches.sort((a, b) => a.t0 - b.t0); });
  return out.sort((a, b) => a.t - b.t);
}

function полюс(cx, cy, r, a){ return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; }

/* Угол каждой ветви в кольце: сектор по языку (RU сверху-справа, дальше по часовой), внутри
   сектора — по порядку старта. Возвращает и шаг между соседями: от него зависят отростки, чтобы
   развилка одной ветки не залезала на соседнюю. */
function углыВетвей(branches){
  const span = (2 * Math.PI) / ДЕРЕВО_СЕКТОРА.length;
  const res = {}, sectors = [];
  ДЕРЕВО_СЕКТОРА.forEach(([lang, label], i) => {
    const a0 = -Math.PI / 2 + span * i + ДЕРЕВО.ЗАЗОР, a1 = -Math.PI / 2 + span * (i + 1) - ДЕРЕВО.ЗАЗОР;
    const mine = branches.filter(b => (b.lang || 'ru') === lang);
    const n = Math.max(mine.length, 1), pitch = (a1 - a0) / n;
    mine.forEach((b, j) => { res[b.scen + '@' + Math.round(b.t0)] = {a: a0 + pitch * (j + 0.5), pitch}; });
    sectors.push({lang, label, a0, a1, n: mine.length});
  });
  // Язык вне трёх известных — в конец сектора RU: такого не бывает, но молча терять ветку нельзя.
  branches.forEach(b => { const k = b.scen + '@' + Math.round(b.t0); if (!res[k]) res[k] = {a: -Math.PI / 2, pitch: 0.01}; });
  return {angles: res, sectors};
}

/* Геометрия одной ветки внутри её полосы. Общая для прошлых прогонов и текущего: разница только
   в ширине полосы и в том, сколько подробностей рисуется. */
function ветвьВПолосе(b, a, Ri, ширина, cx, cy, pitch){
  const ходов = Math.min((b.turns || []).length, ДЕРЕВО.ХОДОВ_МАКС);
  // Воздух до следующей дуги обязателен: без него штрихи смыкаются с ней, полосы сливаются в
  // сплошной диск и «одна дуга — один прогон» перестаёт читаться.
  const тело = ширина * 0.62;
  const len = Math.max(тело * 0.28, тело * (ходов || 1) / ДЕРЕВО.ХОДОВ_МАКС);
  const r0 = Ri + 1.4, r1 = r0 + len;
  const [x0, y0] = полюс(cx, cy, r0, a), [x1, y1] = полюс(cx, cy, r1, a);
  // Узел попапа — на своей доле ствола: видно, рано его подняли или к самому концу.
  let ready = null;
  const i = (b.turns || []).findIndex(t => t.ready);
  if (i >= 0){
    const rr = r0 + len * ((i + 1) / Math.max(ходов, 1));
    const [rx, ry] = полюс(cx, cy, Math.min(rr, r1), a);
    ready = {x: rx, y: ry};
  }
  return {a, r0, r1, len, trunk: [x0, y0, x1, y1], ready, ходов};
}

/* Раскладка: прогоны → координаты. Чистая функция, ничего не рисует. */
function раскладкаКолец(rings){
  const V = ДЕРЕВО.ВЬЮ, cx = V / 2, cy = V / 2;
  const shown = rings.slice(-ДЕРЕВО.КРУГОВ);
  const cur = shown.length ? shown[shown.length - 1] : {r: 0, branches: []};
  const hist = shown.slice(0, -1);
  const дуга = k => ДЕРЕВО.R0 + ДЕРЕВО.ПОЛОСА * k;

  const прошлые = hist.map((ring, k) => {
    const Ri = дуга(k);
    const {angles} = углыВетвей(ring.branches);
    return {r: ring.r, radius: Ri, n: ring.branches.length, bad: ring.branches.filter(x => x.bad).length,
            t: Math.min.apply(null, ring.branches.map(x => x.t0 || 0).concat([Infinity])),
            dots: ring.branches.map(x => {
              const g = ветвьВПолосе(x, angles[x.scen + '@' + Math.round(x.t0)].a, Ri, ДЕРЕВО.ПОЛОСА, cx, cy);
              const kind = x.problems && x.problems.length ? x.problems[0].kind : '';
              return {x: g.trunk[0], y: g.trunk[1], x2: g.trunk[2], y2: g.trunk[3], ready: g.ready,
                      bad: x.bad, kind, цвет: краскаВетви(x), scen: x.scen, key: x.scen + '@' + Math.round(x.t0),
                      title: (x.master && x.master.title) || (x.intent && x.intent.title) || ''};
            })};
  });

  const R0 = дуга(hist.length);                     // дуга текущего прогона
  const Rout = R0 + ДЕРЕВО.ТЕК_ПОЛОСА;              // и внешняя граница его полосы
  const {angles, sectors} = углыВетвей(cur.branches);
  const branches = cur.branches.map(b => {
    const {a, pitch} = angles[b.scen + '@' + Math.round(b.t0)];
    const g = ветвьВПолосе(b, a, R0, ДЕРЕВО.ТЕК_ПОЛОСА, cx, cy, pitch);
    const δ = Math.min(pitch * 0.40, 0.018);        // развилка не должна лезть к соседу
    // Ходы — точками вдоль ствола; в полосе тесно, поэтому они мелкие и читаются при увеличении.
    const n = g.ходов;
    const nodes = (b.turns || []).slice(0, n).map((t, i) => {
      const r = g.r0 + g.len * ((i + 1) / Math.max(n, 1));
      const [x, y] = полюс(cx, cy, r, a);
      return {x, y, r, k: t.k, ready: !!t.ready, i};
    });
    // Затея — коротким отростком от узла попапа (или от конца ствола).
    let intent = null;
    if (b.intent){
      const base = g.ready ? nodes.find(nd => nd.ready) : null;
      const rr = (base ? base.r : g.r1) + 3.5;
      const [ix, iy] = полюс(cx, cy, Math.min(rr, Rout - 2), a + δ);
      intent = {x: ix, y: iy, from: base ? [base.x, base.y] : [g.trunk[2], g.trunk[3]], title: b.intent.title};
    }
    // Два листа: мастер и попап. Попап молчал — обрыв.
    const leafR = Math.min(g.r1 + 4.5, Rout - 1);
    const [mx, my] = полюс(cx, cy, leafR, a - δ), [px, py] = полюс(cx, cy, leafR, a + δ);
    const diverged = !!(b.master && b.popup && b.master.title && b.popup.title &&
                        b.master.title.trim().toLowerCase() !== b.popup.title.trim().toLowerCase());
    const leaves = (b.done || b.master) ? {master: b.master ? {x: mx, y: my, title: b.master.title} : null,
                                           popup: b.popup ? {x: px, y: py, title: b.popup.title} : null,
                                           silent: !!(b.master && !b.popup), diverged} : null;
    // Беды: на своём ходу, если он назван, иначе у конца ствола.
    let tail = 0;
    const problems = (b.problems || []).map(p => {
      const nd = p.at ? nodes.find(x => x.k === 'h' && nodes.filter(y => y.k === 'h' && y.i <= x.i).length === p.at) : null;
      const rr = nd ? nd.r : Math.min(g.r1 + 1.5 + 2.6 * tail++, Rout - 1);
      const [x, y] = полюс(cx, cy, rr, a - δ * 1.7);
      return {x, y, kind: p.kind, text: p.text};
    });
    return {scen: b.scen, key: b.scen + '@' + Math.round(b.t0), lang: b.lang, a, bad: b.bad, done: b.done,
            цвет: краскаВетви(b), kinds: (b.problems || []).map(p => p.kind),
            trunk: g.trunk, nodes, intent, leaves, problems,
            title: (b.master && b.master.title) || (b.intent && b.intent.title) || '',
            hint: b.scen + (b.lang ? ' · ' + b.lang : '') + (b.hard ? ' · сложность ' + b.hard : '') +
                  ' · ходов ' + (b.turns || []).length + (b.fired ? ' · попап на ходу ' + b.fired : (b.done ? ' · попап молчал' : ' · идёт')) +
                  ((b.problems || []).length ? ' · ' + b.problems.map(p => p.kind).join(', ') : ''),
            text: (b.turns || []).map(t => t.txt || '').join(' ')};
  });
  const labels = sectors.map(s => {
    const [x, y] = полюс(cx, cy, Rout + 13, (s.a0 + s.a1) / 2);
    return {x, y, label: s.label, n: s.n, a: (s.a0 + s.a1) / 2};
  });
  return {V, cx, cy, R0, Rout, прошлые, dust: прошлые,
          cur: {r: cur.r, branches, n: cur.branches.length,
                done: cur.branches.filter(b => b.done).length, bad: cur.branches.filter(b => b.bad).length},
          labels, sectors};
}

function ф(n){ return Math.round(n * 10) / 10; }

/* Дуга по сектору: именно она и делит прогоны. */
function svgДуга(cx, cy, r, a0, a1, cls){
  const [x0, y0] = полюс(cx, cy, r, a0), [x1, y1] = полюс(cx, cy, r, a1);
  const big = (a1 - a0) > Math.PI ? 1 : 0;
  return '<path d="M' + ф(x0) + ' ' + ф(y0) + ' A' + ф(r) + ' ' + ф(r) + ' 0 ' + big + ' 1 ' +
         ф(x1) + ' ' + ф(y1) + '" class="' + cls + '"/>';
}

/* Прошлые прогоны — строкой, чтобы кэшировать: тысячи штрихов перерисовывать каждый тик незачем.
   Одна дуга — один прогон, под ней его разговоры. Цвет штриха — вид беды, длина — сколько ходов
   прожил разговор, точка на штрихе — где сработал попап. По штриху щёлкают: `data-s`. */
function svgПрошлые(rings, sectors, cx, cy){
  return rings.map(ring => '<g class="круг" data-r="' + ring.r + '">' +
    (sectors || []).map(s => svgДуга(cx || 500, cy || 500, ring.radius, s.a0, s.a1, 'дуга')).join('') +
    ring.dots.map(d => '<g class="ш" data-s="' + esc(d.scen) + '" data-k="' + esc(d.key) + '"><title>' +
      esc(d.scen + (d.title ? ' · ' + d.title : '') + (d.kind ? ' · ' + d.kind : '')) + '</title>' +
      '<line x1="' + ф(d.x) + '" y1="' + ф(d.y) + '" x2="' + ф(d.x2) + '" y2="' + ф(d.y2) +
      '" class="п-штрих' + (d.bad ? ' беда' : '') + '" stroke="' + d.цвет + '"/>' +
      (d.ready ? '<circle cx="' + ф(d.ready.x) + '" cy="' + ф(d.ready.y) + '" r=".9" class="п-попап"/>' : '') +
      '</g>').join('') +
    '</g>').join('');
}
const svgПыль = svgПрошлые;      // прежнее имя: им зовут из вида и из проверки

/* Подпись ветки: по ней патч решает, надо ли перерисовывать её нутро. Всё, что видно глазом. */
function подписьВетви(b, pick, hit, kind){
  return [b.turns_len, b.nodes.length, b.bad, b.done ? 1 : 0, b.цвет, b.problems.length,
          b.intent ? 1 : 0, b.leaves ? ((b.leaves.master ? 'м' : '') + (b.leaves.popup ? 'п' : '') +
          (b.leaves.silent ? 'т' : '') + (b.leaves.diverged ? 'р' : '')) : '',
          pick ? 1 : 0, hit ? 1 : 0, kind ? 1 : 0].join('|');
}

/* Классы ветки — отдельно от нутра: их патч меняет, не трогая разметку. */
function классыВетви(b, pick, hit, тускло){
  return 'в' + (b.bad ? ' беда' : '') + (b.done ? '' : ' идёт') + (pick ? ' выбр' : '') +
         (hit ? ' иск' : '') + (тускло ? ' тускло' : '');
}

/* Нутро одной ветки — без обёртки <g>: этой же строкой патч обновляет уже стоящую в DOM ветку. */
function svgВетвьВнутри(b){
  let s = '<title>' + esc(b.hint) + (b.title ? '\n' + b.title : '') + '</title>';
  s += '<line x1="' + ф(b.trunk[0]) + '" y1="' + ф(b.trunk[1]) + '" x2="' + ф(b.trunk[2]) + '" y2="' +
       ф(b.trunk[3]) + '" class="ствол" stroke="' + b.цвет + '"/>';
  b.nodes.forEach(nd => {
      if (nd.ready) s += '<circle cx="' + ф(nd.x) + '" cy="' + ф(nd.y) + '" r="4.2" class="сияние"/>';
      s += '<circle cx="' + ф(nd.x) + '" cy="' + ф(nd.y) + '" r="' + (nd.ready ? 2.4 : (nd.k === 'h' ? 1.5 : 1.2)) +
           '" class="' + (nd.ready ? 'узел-готово' : (nd.k === 'h' ? 'узел-чел' : 'узел-бот')) + '"/>';
  });
  if (b.intent){
      s += '<path d="M' + ф(b.intent.from[0]) + ' ' + ф(b.intent.from[1]) + ' Q' + ф((b.intent.from[0] + b.intent.x) / 2) + ' ' +
           ф((b.intent.from[1] + b.intent.y) / 2) + ' ' + ф(b.intent.x) + ' ' + ф(b.intent.y) + '" class="отросток"/>' +
           '<circle cx="' + ф(b.intent.x) + '" cy="' + ф(b.intent.y) + '" r="2" class="узел-затея"/>';
  }
  if (b.leaves){
      const e = [b.trunk[2], b.trunk[3]];
      if (b.leaves.master) s += '<line x1="' + ф(e[0]) + '" y1="' + ф(e[1]) + '" x2="' + ф(b.leaves.master.x) + '" y2="' + ф(b.leaves.master.y) + '" class="лист-нить"/>' +
        '<circle cx="' + ф(b.leaves.master.x) + '" cy="' + ф(b.leaves.master.y) + '" r="1.9" class="лист-мастер"/>';
      if (b.leaves.popup) s += '<line x1="' + ф(e[0]) + '" y1="' + ф(e[1]) + '" x2="' + ф(b.leaves.popup.x) + '" y2="' + ф(b.leaves.popup.y) + '" class="лист-нить"/>' +
        '<circle cx="' + ф(b.leaves.popup.x) + '" cy="' + ф(b.leaves.popup.y) + '" r="1.9" class="лист-попап"/>';
      else if (b.leaves.silent) s += '<line x1="' + ф(e[0]) + '" y1="' + ф(e[1]) + '" x2="' + ф((e[0] + b.leaves.master.x) / 2 + (b.leaves.master.x - e[0]) * 0) +
        '" y2="' + ф((e[1] + b.leaves.master.y) / 2) + '" class="обрыв"/>';
      if (b.leaves.diverged && b.leaves.master && b.leaves.popup)
        s += '<line x1="' + ф(b.leaves.master.x) + '" y1="' + ф(b.leaves.master.y) + '" x2="' + ф(b.leaves.popup.x) + '" y2="' + ф(b.leaves.popup.y) + '" class="разошлись"/>';
  }
  b.problems.forEach(p => { s += '<circle cx="' + ф(p.x) + '" cy="' + ф(p.y) + '" r="2.4" class="узел-беда" fill="' +
  краскаБеды(p.kind) + '"><title>' + esc(p.kind + ': ' + p.text) + '</title></circle>'; });
  return s;
}

/* Попала ли ветка под поиск и под выбранный вид беды. */
function ветвьИщется(b, qq){ return !!qq && (b.scen + ' ' + b.title + ' ' + b.text).toLowerCase().includes(qq); }
function ветвьТускла(b, kind){ return !!kind && b.kinds.indexOf(kind) < 0; }

/* Живое кольцо строкой — первая отрисовка. Дальше ветки обновляет `деревоПатч` по месту. */
function svgВетви(L, pick, q, kind){
  const qq = String(q || '').toLowerCase();
  return L.cur.branches.map(b => {
    const hit = ветвьИщется(b, qq), тускло = ветвьТускла(b, kind), сам = pick === b.key;
    return '<g class="' + классыВетви(b, сам, hit, тускло) + '" data-s="' + esc(b.scen) +
      '" data-k="' + esc(b.key) + '" data-п="' + esc(подписьВетви(b, сам, hit, тускло)) + '">' +
      svgВетвьВнутри(b) + '</g>';
  }).join('');
}

function svgСектора(L){
  const дуги = L.sectors.map(s =>
    svgДуга(L.cx, L.cy, L.R0, s.a0, s.a1, 'дуга тек') +        // дуга текущего прогона
    svgДуга(L.cx, L.cy, L.Rout, s.a0, s.a1, 'дуга край')       // и внешняя граница его полосы
  ).join('');
  return дуги + L.labels.map(l => '<text x="' + ф(l.x) + '" y="' + ф(l.y) + '" class="сектор-имя" transform="rotate(' +
    ф(l.a * 180 / Math.PI + 90) + ' ' + ф(l.x) + ' ' + ф(l.y) + ')">' + l.label + ' · ' + l.n + '</text>').join('');
}

function svgКольца(L, центр, pick, q, histSvg, kind){
  return '<svg class="кольца" viewBox="' + (S.tree_vb || '0 0 1000 1000') + '" preserveAspectRatio="xMidYMid meet" ' +
    'onwheel="деревоКолесо(event)" onpointerdown="деревоТянуть(event)" onclick="деревоКлик(event)">' +
    '<g class="прошлые-все">' + histSvg + '</g><g class="сектора">' + svgСектора(L) + '</g>' +
    '<g class="живое">' + svgВетви(L, pick, q, kind) + '</g>' +
    '<g class="центр">' + центр + '</g></svg>';
}

/* ── СЕРДЦЕ КРУГА: ПРИБОРЫ ────────────────────────────────────────────────────────────────────
 *
 * ЗАЧЕМ. Середина нарочно пустая — кольца туда не растут. Но пустота в середине рисунка, за
 * которым следят часами, это потерянное место: именно там взгляд и отдыхает. Владелец
 * (17.09.2026): «в центре круга сделай сколько этапов прошло, нагрузку на модель и подобное,
 * влезь в тот же размер сердца круга, диаграммами мелкими».
 *
 * ЧТО ТУТ ЕСТЬ И ПОЧЕМУ ИМЕННО ЭТО. Сколько прогонов прошло ВСЕГО (а не сколько нарисовано дугами:
 * дуг шестнадцать, прогонов может быть тысяча) · беды по прогонам ломаной · нагрузка на модель:
 * p50/p95 ломаной и числом, вызовов и сбоев за прогон, потоков · сколько собралось из скольких ·
 * сколько разговоров лежит в складе и сколько сценариев в пуле.
 *
 * ВСЁ ВЛЕЗАЕТ В КРУГ РАДИУСА R0. Содержимое держим в столбце шириной 210 единиц и высотой 210:
 * на отступе 105 от середины полуширина круга — 120 при R0=160, то есть запас есть даже по углам.
 */
function искраSVG(vals, x, y, w, h, цвет, cls){
  const v = (vals || []).filter(n => typeof n === 'number' && isFinite(n)).slice(-40);
  if (v.length < 2) return '';
  const max = Math.max.apply(null, v), min = Math.min.apply(null, v), span = (max - min) || 1;
  const px = i => x + w * i / (v.length - 1);
  const py = n => y + h - h * (n - min) / span;
  const pts = v.map((n, i) => ф(px(i)) + ' ' + ф(py(n))).join(' ');
  return '<polyline points="' + pts + '" class="искра ' + (cls || '') + '" stroke="' + цвет + '"/>' +
         '<circle cx="' + ф(px(v.length - 1)) + '" cy="' + ф(py(v[v.length - 1])) + '" r="1.6" fill="' + цвет + '"/>';
}

function svgСердце(s){
  const X = 500, L = 396, R = 604, W = R - L;     // столбец приборов внутри пустой середины
  const под = (x, y, t, a) => '<text x="' + ф(x) + '" y="' + ф(y) + '" class="с-подпись"' +
    (a ? ' text-anchor="' + a + '"' : '') + '>' + t + '</text>';
  const чис = (x, y, t, cls, a) => '<text x="' + ф(x) + '" y="' + ф(y) + '" class="' + cls + '"' +
    (a ? ' text-anchor="' + a + '"' : '') + '>' + t + '</text>';
  let o = '';
  // 1. Сколько этапов прошло — главное число сердца.
  o += под(X, 400, 'ЭТАПОВ ПРОЙДЕНО', 'middle');
  o += чис(X, 432, s.этапов, 'с-число', 'middle');
  // 2. Беды по прогонам — ломаной, и последнее значение числом.
  o += под(L, 452, 'БЕД В ЭТАПЕ');
  o += чис(R, 452, s.бед, 'с-важно', 'end');
  o += искраSVG(s.беды, L, 456, W, 20, s.бед ? '#ff4d6d' : ЦВЕТ_ЧИСТО);
  // 3. Нагрузка на модель.
  o += '<line x1="' + L + '" y1="482" x2="' + R + '" y2="482" class="с-черта"/>';
  o += под(L, 496, 'НАГРУЗКА НА МОДЕЛЬ');
  o += чис(R, 496, 'p95 ' + s.p95 + 'с', 'с-важно', 'end');
  o += искраSVG(s.p95р, L, 500, W, 18, '#4dc9ff');
  o += под(L, 534, 'ВЫЗОВОВ');      o += чис(L, 548, s.вызовов, 'с-мелкое');
  o += под(X, 534, 'СБОЕВ', 'middle'); o += чис(X, 548, s.сбоев, s.сбоев ? 'с-мелкое плохо' : 'с-мелкое', 'middle');
  o += под(R, 534, 'ПОТОКОВ', 'end'); o += чис(R, 548, s.потоков, 'с-мелкое', 'end');
  o += под(L, 568, 'МЕДИАНА');      o += чис(L, 581, s.p50 + 'с', 'с-мелкое');
  o += под(R, 568, 'ДЛИТ. ЭТАПА', 'end'); o += чис(R, 581, s.мин + ' мин', 'с-мелкое', 'end');
  // 4. Сколько собралось — полоской.
  const доля = s.сцен ? Math.max(0, Math.min(1, s.собрано / s.сцен)) : 0;
  o += под(L, 598, 'СОБРАЛОСЬ');
  o += чис(R, 598, s.собрано + ' / ' + s.сцен, 'с-мелкое', 'end');
  o += '<line x1="' + L + '" y1="604" x2="' + R + '" y2="604" class="с-полоса"/>' +
       '<line x1="' + L + '" y1="604" x2="' + ф(L + W * доля) + '" y2="604" class="с-полоса есть"/>';
  // 5. Что накоплено.
  o += под(X, 624, 'РАЗГОВОРОВ В СКЛАДЕ ' + s.разговоров + ' · ПУЛ ' + s.пул, 'middle');
  return o;
}

/* ── ЖИВОЕ ОБНОВЛЕНИЕ, А НЕ ПЕРЕРИСОВКА ───────────────────────────────────────────────────────
 *
 * ЗАЧЕМ. Панель собирала ВЕСЬ раздел заново каждые две с половиной секунды: `render()` подменял
 * innerHTML целиком, и вместе с разметкой пропадал и возникал заново весь рисунок. Выглядело это
 * ровно как перезагрузка страницы — моргание, сброшенные подсказки, и никакого ощущения, что
 * батарея идёт прямо сейчас. Владелец (17.09.2026): «они должны меняться в реальном времени, а не
 * при перезагрузке страницы».
 *
 * КАК. Рисунок строится строкой ОДИН раз, а дальше правится по месту: ветка сопоставляется по
 * ключу `сценарий@время`, и её нутро переписывается только если изменилась подпись — число ходов,
 * исход, цвет, листья. Тогда узлы, которые не менялись, остаются теми же элементами, и браузеру
 * есть что анимировать: новая ветка прорастает (`.рост`), выросший ход вспыхивает (`.дрогнула`),
 * законченная плавно перекрашивается из «идёт» в цвет исхода — переход стоит на `stroke` в стилях.
 *
 * Ушедшие ветки (начался новый круг) не исчезают рывком: им ставится `.гаснет`, и они снимаются
 * через полсекунды — к этому времени они уже нарисованы пылью во внутреннем кольце.
 */
function деревоПатч(L, центр, pick, q, kind){
  const svg = document.querySelector('svg.кольца');
  if (!svg) return false;
  const qq = String(q || '').toLowerCase();
  // Пыль и сектора меняются только со сменой круга — по ключу состава.
  const kdust = L.прошлые.map(d => d.r + ':' + d.n).join('|');
  if (svg.dataset.пыль !== kdust){ svg.dataset.пыль = kdust; svg.querySelector('.прошлые-все').innerHTML = svgПрошлые(L.прошлые, L.sectors, L.cx, L.cy); }
  const ksec = L.sectors.map(s => s.label + s.n).join('|') + '@' + ф(L.R0) + '/' + ф(L.Rout);
  if (svg.dataset.сект !== ksec){ svg.dataset.сект = ksec; svg.querySelector('.сектора').innerHTML = svgСектора(L); }
  svg.querySelector('.центр').innerHTML = центр;

  const gwrap = svg.querySelector('.живое');
  const было = new Map();
  Array.prototype.forEach.call(gwrap.children, g => { if (!g.classList.contains('гаснет')) было.set(g.dataset.k, g); });
  L.cur.branches.forEach(b => {
    const hit = ветвьИщется(b, qq), тускло = ветвьТускла(b, kind), сам = pick === b.key;
    const подпись = подписьВетви(b, сам, hit, тускло);
    let g = было.get(b.key);
    if (!g){
      g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.dataset.s = b.scen; g.dataset.k = b.key;
      g.setAttribute('class', классыВетви(b, сам, hit, тускло) + ' рост');
      g.innerHTML = svgВетвьВнутри(b);
      g.dataset.п = подпись;
      gwrap.appendChild(g);
      // Класс снимаем, иначе при следующей перерисовке страницы анимация проигралась бы снова.
      setTimeout(() => g.classList.remove('рост'), 900);
      return;
    }
    было.delete(b.key);
    if (g.dataset.п !== подпись){
      const вырос = +(g.dataset.ходов || 0) < b.nodes.length;
      g.innerHTML = svgВетвьВнутри(b);
      g.dataset.п = подпись;
      if (вырос){ g.classList.add('дрогнула'); setTimeout(() => g.classList.remove('дрогнула'), 600); }
    }
    g.dataset.ходов = b.nodes.length;
    // Классы состояния переписываем ВСЕГДА, но не сбивая идущую анимацию: пока ветка росла, отбор
    // по виду беды до неё не доходил — свежие ветки оставались яркими, и отбор выглядел сломанным.
    const анимация = (g.classList.contains('рост') ? ' рост' : '') + (g.classList.contains('дрогнула') ? ' дрогнула' : '');
    const cls = классыВетви(b, сам, hit, тускло) + анимация;
    if (g.getAttribute('class') !== cls) g.setAttribute('class', cls);
  });
  было.forEach(g => { g.classList.add('гаснет'); setTimeout(() => g.remove(), 500); });
  return true;
}

/* Веер диалога: ходы слева направо, от первой реплики к каждой следующей тонкие нити, ready —
   яркий узел с отростком к затее, справа два листа, беды красным под своими ходами. */
function svgВеер(b){
  if (!b) return '';
  // Ширина viewBox под узкую плитку: при 640 подписи ужимались до нечитаемых 5px.
  const W = 500, H = 210, x0 = 30, x1 = 400, y = 104;
  const n = b.turns.length;
  const xs = b.turns.map((t, i) => n > 1 ? x0 + (x1 - x0) * i / (n - 1) : (x0 + x1) / 2);
  let s = '<svg class="веер" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMidYMid meet">';
  s += '<line x1="' + x0 + '" y1="' + y + '" x2="' + (x1 + 30) + '" y2="' + y + '" class="в-ось"/>';
  // веер нитей от первой реплики
  for (let i = 1; i < n; i++){
    const cx1 = xs[0] + (xs[i] - xs[0]) * 0.35, cx2 = xs[0] + (xs[i] - xs[0]) * 0.65;
    const lift = 22 + 9 * i;
    s += '<path d="M' + ф(xs[0]) + ' ' + y + ' C' + ф(cx1) + ' ' + (y - lift) + ' ' + ф(cx2) + ' ' + (y - lift) + ' ' + ф(xs[i]) + ' ' + y + '" class="в-нить"/>';
  }
  let readyX = null, humans = 0;
  b.turns.forEach((t, i) => {
    const x = xs[i];
    if (t.k === 'h') humans++;
    if (t.ready && readyX === null){
      readyX = x;
      s += '<circle cx="' + ф(x) + '" cy="' + y + '" r="9" class="сияние"/>';
      s += '<circle cx="' + ф(x) + '" cy="' + y + '" r="5" class="узел-готово"/>';
      s += '<text x="' + ф(x) + '" y="' + (y + 24) + '" class="в-подпись яркая" text-anchor="middle">попап · ход ' + humans + '</text>';
    } else {
      s += '<circle cx="' + ф(x) + '" cy="' + y + '" r="' + (t.k === 'h' ? 4 : 3) + '" class="' + (t.k === 'h' ? 'узел-чел' : 'узел-бот') + '"/>';
    }
    // Подписываем только реплики человека: ответы Kleal длинные, и в узкой плитке они наползали
    // друг на друга; их читают ниже, в тексте диалога.
    const txt = t.k === 'h' ? String(t.txt || '').replace(/\s+/g, ' ').trim() : '';
    if (txt) s += '<text x="' + ф(x) + '" y="' + (y - 12) + '" class="в-подпись чел" text-anchor="middle">' +
      esc(txt.length > 18 ? txt.slice(0, 17) + '…' : txt) + '</text>';
  });
  if (b.intent){
    const fx = readyX == null ? xs[n - 1] || x1 : readyX, ix = fx + 46, iy = 40;
    s += '<path d="M' + ф(fx) + ' ' + y + ' Q' + ф(fx + 10) + ' ' + iy + ' ' + ф(ix) + ' ' + iy + '" class="отросток"/>' +
         '<circle cx="' + ф(ix) + '" cy="' + iy + '" r="3.5" class="узел-затея"/>' +
         '<text x="' + ф(ix + 8) + '" y="' + (iy + 3) + '" class="в-подпись яркая">затея · ' + esc(b.intent.title.slice(0, 26)) + '</text>';
  }
  const lx = x1 + 58, кор = t => esc(String(t || '').length > 22 ? String(t).slice(0, 21) + '…' : t);
  if (b.master){
    s += '<path d="M' + (x1 + 30) + ' ' + y + ' Q' + (x1 + 44) + ' ' + y + ' ' + lx + ' ' + (y - 18) + '" class="лист-нить"/>' +
         '<circle cx="' + lx + '" cy="' + (y - 18) + '" r="3" class="лист-мастер"/>' +
         '<text x="' + (lx + 7) + '" y="' + (y - 15) + '" class="в-подпись">мастер · ' + кор(b.master.title) + '</text>';
  }
  if (b.popup){
    const div = b.master && b.master.title.trim().toLowerCase() !== b.popup.title.trim().toLowerCase();
    s += '<path d="M' + (x1 + 30) + ' ' + y + ' Q' + (x1 + 44) + ' ' + y + ' ' + lx + ' ' + (y + 18) + '" class="лист-нить"/>' +
         '<circle cx="' + lx + '" cy="' + (y + 18) + '" r="3" class="лист-попап"/>' +
         '<text x="' + (lx + 7) + '" y="' + (y + 21) + '" class="в-подпись' + (div ? ' плохо' : '') + '">попап · ' + кор(b.popup.title) + '</text>' +
         (div ? '<line x1="' + lx + '" y1="' + (y - 15) + '" x2="' + lx + '" y2="' + (y + 15) + '" class="разошлись"/>' : '');
  } else if (b.master){
    s += '<line x1="' + (x1 + 30) + '" y1="' + y + '" x2="' + (x1 + 44) + '" y2="' + (y + 10) + '" class="обрыв"/>' +
         '<text x="' + (lx + 7) + '" y="' + (y + 21) + '" class="в-подпись плохо">попап молчал</text>';
  }
  let tail = 0;
  b.problems.forEach(p => {
    let x;
    if (p.at){ let h = 0, idx = -1; b.turns.forEach((t, i) => { if (t.k === 'h'){ h++; if (h === p.at && idx < 0) idx = i; } }); x = idx >= 0 ? xs[idx] : null; }
    if (x == null) x = x1 + 30 - 18 * tail++;
    const c = краскаБеды(p.kind);
    s += '<line x1="' + ф(x) + '" y1="' + y + '" x2="' + ф(x) + '" y2="' + (y + 52) + '" class="беда-нить" stroke="' + c + '"/>' +
         '<circle cx="' + ф(x) + '" cy="' + (y + 52) + '" r="3.2" class="узел-беда" fill="' + c + '"><title>' + esc(p.kind + ': ' + p.text) + '</title></circle>' +
         '<text x="' + ф(x) + '" y="' + (y + 66) + '" class="в-подпись" fill="' + c + '" text-anchor="middle">' + esc(p.kind.toLowerCase()) + '</text>';
  });
  return s + '</svg>';
}

/* ── управление картинкой: масштаб Ctrl/⌘+колесо и кнопками, сдвиг перетаскиванием, выбор щелчком ──
   Голое колесо НЕ перехватываем: кольца занимают полэкрана, и обычная прокрутка страницы, проходя
   над ними, превращалась в масштаб — картинка уезжала сама по себе (снято на стенде 17.09.2026). */
function деревоМасштаб(k, cx, cy){
  const vb = (S.tree_vb || '0 0 1000 1000').split(' ').map(Number);
  const px = cx == null ? vb[0] + vb[2] / 2 : cx, py = cy == null ? vb[1] + vb[3] / 2 : cy;
  const w = Math.min(4000, Math.max(120, vb[2] * k)), h = w;
  S.tree_vb = [px - (px - vb[0]) * (w / vb[2]), py - (py - vb[1]) * (h / vb[3]), w, h].map(v => Math.round(v * 10) / 10).join(' ');
  const svg = document.querySelector('svg.кольца');
  if (svg) svg.setAttribute('viewBox', S.tree_vb);
  if (typeof батЗапомнить === 'function') батЗапомнить();
}
function деревоКолесо(ev){
  if (!(ev.ctrlKey || ev.metaKey)) return;
  ev.preventDefault();
  const svg = ev.currentTarget, vb = (S.tree_vb || '0 0 1000 1000').split(' ').map(Number);
  const rect = svg.getBoundingClientRect();
  деревоМасштаб(ev.deltaY > 0 ? 1.12 : 1 / 1.12,
                vb[0] + (ev.clientX - rect.left) / rect.width * vb[2], vb[1] + (ev.clientY - rect.top) / rect.height * vb[3]);
}
function деревоТянуть(ev){
  const svg = ev.currentTarget, rect = svg.getBoundingClientRect();
  const vb0 = (S.tree_vb || '0 0 1000 1000').split(' ').map(Number), sx = ev.clientX, sy = ev.clientY;
  let moved = false;
  const move = e => {
    const dx = (e.clientX - sx) / rect.width * vb0[2], dy = (e.clientY - sy) / rect.height * vb0[3];
    if (Math.abs(e.clientX - sx) + Math.abs(e.clientY - sy) > 3) moved = true;
    S.tree_vb = [vb0[0] - dx, vb0[1] - dy, vb0[2], vb0[3]].map(v => Math.round(v * 10) / 10).join(' ');
    svg.setAttribute('viewBox', S.tree_vb);
  };
  const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
    S.tree_drag = moved; if (typeof батЗапомнить === 'function') батЗапомнить(); };
  window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
}
function деревоКлик(ev){
  if (S.tree_drag){ S.tree_drag = false; return; }
  // Щёлкают и по живой ветке, и по штриху прошлого прогона — разговор открывается одинаково.
  // ВЫБИРАЕМ ПО КЛЮЧУ «сценарий@время», а не по метке: пул сценариев переиспользуется, и одна
  // метка лежит в складе столько раз, сколько прогонов её гоняли. По метке из новой дуги
  // открывалась копия из старой — со снимка владельца 17.09.2026.
  const g = ev.target.closest ? ev.target.closest('g.в, g.ш') : null;
  if (g) batPick(g.getAttribute('data-k') || g.getAttribute('data-s'));
}
function деревоСброс(){ S.tree_vb = '0 0 1000 1000'; if (typeof батЗапомнить === 'function') батЗапомнить(); render(); }
/*@дерево-конец*/

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
    <div class="scroll"><table><thead><tr><th>имя</th><th>возраст</th><th>город</th><th>интересы</th><th>источник</th><th>состояние</th><th></th></tr></thead><tbody>
    ${rows.map(u=>`<tr>
      <td><b>${esc(u.name)}</b></td><td>${esc(u.age||'')}</td><td>${esc(u.area||u.city||'')}</td>
      <td>${(u.interests||[]).slice(0,5).map(i=>`<span class="tag">${esc(i)}</span>`).join('')}</td>
      <td class="muted">${esc(u.source||'')}</td>
      <td class="muted">${u.paused||((u.receiving||{}).status==='paused')?'на паузе':(u.verified?'верифицирован':'')}</td>
      <td style="white-space:nowrap">
        <button class="act" onclick="openPerson('${esc(u.name).replace(/'/g,"\\'")}','${esc(u.id||'')}')">Карточка</button>
        <button class="act" onclick="verb('${esc(u.name).replace(/'/g,"\\'")}','${u.paused||((u.receiving||{}).status==='paused')?'unpause':'pause'}','${esc(u.id||'')}')">${u.paused||((u.receiving||{}).status==='paused')?'Снять паузу':'Пауза'}</button>
      </td>
    </tr>`).join('')}
    </tbody></table></div>
    ${rows.length>=200?'<div class="hint" style="margin-top:8px">Показаны первые 200 — уточни поиск.</div>':''}
  </div>` + accountsCard();
};

/* Человек — по id (kleal-ms/docs/IDENTITY.md): тёзки — норма, и по имени пауза, бан и карточка
   доставались первому из двух «Иванов». Имя — подпись и запасной ключ для однозначных. */
function openPerson(n, id){ S.pname=n; S.pid=id||''; setTab('person'); loadPerson(); }

/*
 * УПРАВЛЕНИЕ ЛЮДЬМИ БЫЛО ТОЛЬКО НА СТАРОЙ СТРАНИЦЕ — той, что открывалась по `?legacy=1`, о
 * которой надо было знать. На основной панели «поставить на паузу» сделать было нельзя вообще,
 * хотя ручки на сервере есть и покрыты тестами. Здесь они там, где человека и находят: в списке
 * и в карточке.
 *
 * Глаголы намеренно узкие: каждый правит ОДИН ключ строки и не проходит через нормализацию,
 * которая при любом сохранении дописывала человеку интересы, язык и радиус, которых он не
 * называл. Пауза не должна выдумывать профиль.
 */
async function verb(name, v, id){
  try {
    const r = await api('/api/admin/person/verb', { body: { name, id: id||'', verb: v } });
    if (r && r.ok === false) throw new Error(r.error || 'не вышло');
    toast(({pause:'На паузе', unpause:'Снят с паузы', verify:'Верифицирован',
            unverify:'Верификация снята'})[v] || 'Готово');
    if (S.pname === name) await loadPerson();
    if (S.users) await LOADERS.users();
  } catch(e){ toast(e.message, true); }
}

async function fatigue(name){
  try { await api('/api/admin/person/fatigue-reset', { body: { name } });
        toast('Счётчик усталости сброшен'); }
  catch(e){ toast(e.message, true); }
}

/**
 * Удаление требует ВПЕЧАТАТЬ имя. Раньше оно стояло красной кнопкой в одном ряду с «Карточка»
 * и «Edit», одного размера и без подтверждения: промах пальцем стирал живого человека.
 */
async function delPerson(name, id){
  const typed = prompt('Удалить человека без возврата.\nВпечатай имя, чтобы подтвердить:', '');
  if (typed === null) return;
  if (typed.trim().toLowerCase() !== String(name).trim().toLowerCase()){
    toast('Имя не совпало — ничего не тронул', true); return;
  }
  try {
    await api('/api/admin/user/' + encodeURIComponent(id) + '/delete', { body: {} });
    toast('Удалён'); S.person=null; S.pname='';
    if (S.users) await LOADERS.users();
    setTab('users');
  } catch(e){ toast(e.message, true); }
}

// ---------------------------------------------------------------- Карточка
LOADERS.person = () => { if (S.pname) loadPerson(); };
async function loadPerson(){
  const n = S.pname || document.getElementById('pn')?.value || '';
  if (!n) return;
  S.pname = n; busy('person', true); S.person_err='';
  try { S.person = await api('/api/admin/person?name=' + encodeURIComponent(n)
                              + (S.pid ? '&id=' + encodeURIComponent(S.pid) : ''));
        if (S.person && S.person.id) S.pid = S.person.id;
        S.person_busy=false; render(); }
  catch(e){ fail('person', e); }
}
VIEWS.person = () => {
  const p = S.person;
  const form = `<div class="row" style="margin-bottom:12px">
      <input id="pn" style="flex:1;min-width:220px" placeholder="имя человека" value="${esc(S.pname||'')}">
      <button class="act primary" onclick="S.pname=document.getElementById('pn').value;S.pid='';loadPerson()">Показать</button>
    </div>`;
  if (S.person_busy) return `<div class="card">${form}<span class="spin"></span> считаю видимость…</div>`;
  if (!p) return `<div class="card">${form}${errBox('person')}<div class="hint">Карточка отвечает на два вопроса: почему человека никто не находит и почему он не находит никого.</div></div>`;
  if (p.error === 'AMBIGUOUS_PERSON') return `<div class="card">${form}
    <h2>Несколько человек с таким именем — выбери</h2>
    <div class="scroll"><table><tbody>${(p.candidates||[]).map(c=>`<tr>
      <td><b>${esc(c.name)}</b></td><td>${esc(c.age||'')}</td><td>${esc(c.area||'')}</td>
      <td class="muted">${c.owned?'с учёткой':'без учётки'}</td><td class="muted">${esc(c.id)}</td>
      <td><button class="act" onclick="openPerson('${esc(c.name).replace(/'/g,"\\'")}','${esc(c.id)}')">Карточка</button></td>
    </tr>`).join('')}</tbody></table></div></div>`;
  const id = p.identity||{};
  const pid = esc(p.id||S.pid||'');
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

    <div class="card" style="margin-top:12px">
      <h2>Действия</h2>
      <div class="hint">Каждое правит одно поле и ничего не дописывает в профиль.</div>
      <div class="row" style="margin-top:10px">
        <button class="act" onclick="verb('${esc(p.name||S.pname).replace(/'/g,"\\'")}','${id.paused?'unpause':'pause'}','${pid}')">${id.paused?'Снять паузу':'Поставить на паузу'}</button>
        <button class="act" onclick="verb('${esc(p.name||S.pname).replace(/'/g,"\\'")}','${id.verified?'unverify':'verify'}','${pid}')">${id.verified?'Снять верификацию':'Верифицировать'}</button>
        <button class="act" onclick="fatigue('${esc(p.name||S.pname).replace(/'/g,"\\'")}')">Сбросить усталость</button>
      </div>
      <div class="row" style="margin-top:10px">
        ${id.banned || id.accountStatus === 'banned'
          ? `<button class="act" onclick="unban('${esc(p.name||S.pname).replace(/'/g,"\\'")}','${pid}')">Снять блокировку</button>
             <span class="muted">заблокирован: не в поиске и не в группах</span>`
          : `<button class="act" style="color:var(--bad);border-color:var(--bad)"
               onclick="banFrom('${esc(p.name||S.pname).replace(/'/g,"\\'")}','','${pid}')">Заблокировать</button>
             <span class="muted">это не пауза: пауза добровольная, блокировка — решение модератора</span>`}
      </div>
      ${p.id?`<div class="row" style="margin-top:16px;border-top:1px solid var(--line);padding-top:12px">
        <button class="act" style="color:var(--bad);border-color:var(--bad)"
          onclick="delPerson('${esc(p.name||S.pname).replace(/'/g,"\\'")}','${esc(p.id)}')">Удалить человека</button>
        <span class="muted">без возврата; спросит имя</span>
      </div>`:''}
    </div>
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
  // Кто ищет и что ищем — общее для лаборатории и прогонов под ней.
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
  </div>` + diagCard();
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

// ---------------------------------------------------------------- Прогоны (внутри «Матчинга»)
/*
 * ТРИ ИЗ ЧЕТЫРЁХ КНОПОК ЗДЕСЬ НЕ РАБОТАЛИ. Они звали ручку без тела запроса — то есть GET, —
 * а «воронка», «разнообразие» и «устойчивость» на сервере принимают только POST и только с
 * ищущим: это прогоны ПОИСКА, а поиск не бывает ничей. Ответом был честный «код 404», и
 * выглядело это как сломанная панель. Теперь они отправляют того же ищущего, что и лаборатория
 * строкой выше, и работают ровно там, где человек уже выбрал, от чьего лица смотрит.
 */
function diagBody(){
  // Те же поля, что у лаборатории строкой выше: `ls` — от чьего лица, `lq` — что ищем.
  const b = { self: (S.ls || '').trim(), query: (S.lq || '').trim() };
  if (S.lab && S.lab.intent) b.intent = S.lab.intent;
  return b;
}
async function diag(kind){
  if (kind !== 'cohorts' && !(S.ls || '').trim()){
    toast('Выбери, от чьего лица смотрим — прогон считает ЕГО поиск', true); return;
  }
  busy('diag', true); S.diag_err=''; S.diag=null; S.diag_kind=kind;
  try {
    S.diag = kind === 'cohorts'
      ? await api('/api/admin/cohorts')
      : await api('/api/admin/' + kind, { body: diagBody() });
    S.diag_busy=false; render();
  } catch(e){ fail('diag', e); }
}

function diagCard(){
  return `<div class="card">
    <h2>Прогоны</h2>
    <div class="hint">Считают не один поиск, а его свойства. «Когорты» читают хранилище и отвечают сразу;
      остальные зовут движок от лица выбранного человека и занимают до минуты.</div>
    <div class="row" style="margin:10px 0">
      <button class="act" onclick="diag('funnel')">Воронка</button>
      <button class="act" onclick="diag('diversity')">Разнообразие</button>
      <button class="act" onclick="diag('stability')">Устойчивость</button>
      <button class="act" onclick="diag('cohorts')">Когорты</button>
    </div>
    ${errBox('diag')}
    ${S.diag_busy?'<span class="spin"></span> считаю…':''}
    ${S.diag?`<div class="hint">${esc(S.diag_kind||'')}</div><pre>${esc(JSON.stringify(S.diag,null,2))}</pre>`:''}
  </div>`;
}


// ---------------------------------------------------------------- Модель
/*
 * «ТЕПЛОТА НЕЙРОСЕТИ». До сих пор её не было нигде: температура лежала двумя десятками чисел
 * прямо в коде четырёх сервисов, модель выбиралась переменной окружения, то есть перезапуском.
 * Здесь и то и другое стало настройкой — и это поправка К КОДУ, а не подмена его: пока режим
 * «как в коде», всё считается ровно так, как написано у каждого вызова.
 *
 * Почему режимы, а не одно число. У вызовов разные задачи: разговор идёт на 0.35 и на повторах
 * спускается до 0.1, чтобы ответ был повторяемым; придумывание идей — наоборот, выше. Одно
 * число на всё стирает эту разницу, поэтому оно спрятано за режимом «одно на всё», а обычный
 * способ подкрутить продукт целиком — «умножить все», сохраняя соотношения.
 */
LOADERS.model = async () => {
  busy('model', true); S.model_err='';
  try {
    const [s, m] = await Promise.all([api('/api/admin/settings'), api('/api/admin/model')]);
    S.set = s; S.mdl = m; S.model_busy=false; render();
  } catch(e){ fail('model', e); }
};

async function saveModel(patch){
  try {
    const r = await api('/api/admin/settings', { body: { model: patch } });
    S.set = await api('/api/admin/settings');
    toast('Сохранено — сервисы подхватят в течение нескольких секунд');
    render();
  } catch(e){ toast(e.message, true); }
}

VIEWS.model = () => {
  if (S.model_busy) return `<div class="card"><span class="spin"></span> читаю настройки…</div>`;
  if (!S.set || !S.mdl) return `<div class="card">${errBox('model')}<button class="act primary" onclick="LOADERS.model()">Загрузить</button></div>`;
  const m = S.set.model || {};
  const mode = m.temperature_mode || 'code';
  const models = S.mdl.models || [];
  const curId = m.id || S.mdl.code_default || '';
  const byTag = m.temperature_by_tag || {};

  const modeBtn = (k, label, note) =>
    `<button class="act ${mode===k?'primary':''}" title="${esc(note)}"
       onclick="saveModel({temperature_mode:'${k}'})">${label}</button>`;

  return `<div class="card">
    <h2>Теплота</h2>
    <div class="hint">Чем выше, тем разнообразнее и тем менее повторяем ответ. Выше ~0.5 одна и та же
      фраза перестаёт вести себя одинаково дважды — для поиска это уже подбрасывание монеты.</div>
    <div class="row" style="margin:12px 0">
      ${modeBtn('code',  'Как в коде',   'у каждого вызова своя температура — как написано у разработчика')}
      ${modeBtn('scale', 'Умножить все', 'подкрутить продукт целиком, сохранив соотношения между вызовами')}
      ${modeBtn('fixed', 'Одно на всё',  'одно число на каждый вызов — для опытов, не для боевого режима')}
    </div>
    ${mode==='fixed'?`<div class="row">
      <input id="tfix" type="number" step="0.05" min="0" max="2" style="width:120px" value="${esc(m.temperature!=null?m.temperature:0.4)}">
      <button class="act primary" onclick="saveModel({temperature:parseFloat(document.getElementById('tfix').value)})">Применить</button>
      <span class="muted">одно число вместо всех</span>
    </div>`:''}
    ${mode==='scale'?`<div class="row">
      <input id="tsc" type="number" step="0.05" min="0.1" max="3" style="width:120px" value="${esc(m.temperature_scale!=null?m.temperature_scale:1)}">
      <button class="act primary" onclick="saveModel({temperature_scale:parseFloat(document.getElementById('tsc').value)})">Применить</button>
      <span class="muted">1.0 — как в коде, 0.5 — вдвое спокойнее, 1.5 — вольнее</span>
    </div>`:''}

    <h2 style="margin-top:18px">По местам вызова</h2>
    <div class="hint">Точечная правка сильнее режима. Пусто — берётся из кода.</div>
    <div class="scroll" style="margin-top:10px"><table><thead><tr><th>место</th><th>в коде</th><th>сейчас</th><th></th></tr></thead><tbody>
    ${(S.set.code_temps||[]).map(c=>`<tr>
      <td><b>${esc(c.tag)}</b><div class="muted">${esc(c.note||'')}</div></td>
      <td class="muted">${esc(c.value)}</td>
      <td><input id="tt_${esc(c.tag)}" type="number" step="0.05" min="0" max="2" style="width:90px"
            placeholder="${esc(c.value)}" value="${byTag[c.tag]!=null?esc(byTag[c.tag]):''}"></td>
      <td><button class="act" onclick="saveTag('${esc(c.tag)}')">Сохранить</button>
          ${byTag[c.tag]!=null?`<button class="act" onclick="clearTag('${esc(c.tag)}')">Как в коде</button>`:''}</td>
    </tr>`).join('')}
    </tbody></table></div>
  </div>

  <div class="card">
    <h2>Какая модель отвечает</h2>
    <div class="hint">Список приходит от llm-сервиса — того единственного места, где лежат ключи.</div>
    <div class="row" style="margin:10px 0">
      <select id="mid" style="min-width:280px">
        ${models.map(x=>`<option value="${esc(x.id)}" ${x.id===curId?'selected':''}>${esc(x.label||x.id)}</option>`).join('')
          || `<option value="${esc(curId)}">${esc(curId)} (список недоступен)</option>`}
      </select>
      <button class="act primary" onclick="saveModel({id:document.getElementById('mid').value})">Выбрать</button>
      ${m.id?`<button class="act" onclick="saveModel({id:null})">Как в коде</button>`:''}
    </div>
    ${models.filter(x=>x.id===curId).map(x=>`<div class="hint">${esc(x.info||'')}</div>`).join('')}
    <div class="row" style="margin-top:14px">
      <button class="act" onclick="probe()">Спросить модель</button>
      <span class="muted">короткий живой запрос: отвечает ли она и за сколько</span>
    </div>
    ${S.probe_busy?'<span class="spin"></span> жду ответа…':''}
    ${S.probe?`<div class="${S.probe.ok?'calm':'err'}" style="margin-top:10px">
      ${S.probe.ok?`ответила за ${num(S.probe.ms)} мс: «${esc(S.probe.text)}»`:esc(S.probe.error)}</div>`:''}
  </div>

  ${(S.set.history||[]).length?`<div class="card">
    <h2>Что меняли</h2>
    <div class="scroll"><table><thead><tr><th>когда</th><th>что</th><th>было</th><th>стало</th></tr></thead><tbody>
    ${S.set.history.slice(0,20).map(h=>`<tr>
      <td class="muted">${esc(new Date((h.t||0)*1000).toLocaleString('ru'))}</td>
      <td>${esc(h.what)}</td><td class="muted">${esc(h.was==null?'как в коде':h.was)}</td>
      <td>${esc(h.now==null?'как в коде':h.now)}</td></tr>`).join('')}
    </tbody></table></div></div>`:''}`;
};

async function saveTag(tag){
  const el = document.getElementById('tt_' + tag);
  const v = el && el.value.trim() ? parseFloat(el.value) : null;
  const by = Object.assign({}, (S.set.model||{}).temperature_by_tag || {});
  if (v==null) delete by[tag]; else by[tag]=v;
  await saveModel({temperature_by_tag: by});
}
async function clearTag(tag){
  const by = Object.assign({}, (S.set.model||{}).temperature_by_tag || {});
  delete by[tag];
  await saveModel({temperature_by_tag: by});
}
async function probe(){
  S.probe=null; S.probe_busy=true; render();
  try { S.probe = await api('/api/admin/model/probe', {body:{}}); }
  catch(e){ S.probe = {ok:false, error:e.message}; }
  S.probe_busy=false; render();
}

// ---------------------------------------------------------------- Промпты
/*
 * ВСЕ ИНСТРУКЦИИ ПРОДУКТА В ОДНОМ МЕСТЕ. Их восемнадцать, и до сих пор каждая была константой
 * внутри своего сервиса: правка означала редактирование файла на боевом боксе и перезапуск.
 *
 * Список панель не хранит — его сообщает сам код: каждый сервис, читая свой промпт, записывает
 * в каталог, как тот выглядит «из коробки». Поэтому новый промпт появляется здесь сам, а не
 * тогда, когда о нём вспомнят.
 *
 * Правка — это ПОВЕРХ кода. «Вернуть как в коде» стирает поправку, а не пишет копию: значит
 * выкладка с новой редакцией промпта доедет до продукта, а не будет молча перекрыта старым
 * текстом из базы.
 */
LOADERS.prompts = async () => {
  busy('prompts', true); S.prompts_err='';
  try { S.set = await api('/api/admin/settings'); S.prompts_busy=false; render(); }
  catch(e){ fail('prompts', e); }
};

VIEWS.prompts = () => {
  if (S.prompts_busy) return `<div class="card"><span class="spin"></span> читаю каталог…</div>`;
  if (!S.set) return `<div class="card">${errBox('prompts')}<button class="act primary" onclick="LOADERS.prompts()">Загрузить</button></div>`;
  const list = S.set.prompts || [];
  if (!list.length) return `<div class="card"><h2>Промпты</h2>
    <div class="hint">Каталог пуст. Он заполняется сам, когда сервисы читают свои инструкции:
      открой любой экран приложения, который зовёт модель, и вернись сюда. Если база выключена
      (режим json), править промпты нельзя — они берутся только из кода.</div></div>`;

  const sel = S.psel || list[0].name;
  const cur = list.find(x=>x.name===sel) || list[0];
  const groups = {};
  list.forEach(x => { (groups[x.service] = groups[x.service] || []).push(x); });

  return `<div class="card">
    <h2>Промпты <span class="pill">${num(list.length)}</span></h2>
    <div class="hint">Слева — все инструкции продукта, сгруппированные по агенту. Точка значит, что
      промпт переопределён из панели и код на него больше не влияет.</div>
    <div class="row" style="align-items:flex-start;gap:16px;margin-top:12px">
      <div style="flex:0 0 250px;max-height:520px;overflow:auto">
        ${Object.keys(groups).sort().map(g=>`
          <div class="muted" style="margin:10px 0 4px;text-transform:uppercase;font-size:11px;letter-spacing:.06em">${esc(g)}</div>
          ${groups[g].map(x=>`<div class="prow ${x.name===sel?'on':''}" onclick="S.psel='${esc(x.name)}';render()">
            <span>${esc(x.name.split('.').slice(1).join('.')||x.name)}</span>
            <span class="muted">${x.overridden?'●':''} ${num(x.chars)}</span>
          </div>`).join('')}`).join('')}
      </div>
      <div style="flex:1;min-width:320px">
        <div class="row" style="margin-bottom:8px">
          <b>${esc(cur.name)}</b>
          <span class="pill">${cur.overridden?'правлен в панели':'как в коде'}</span>
          <span class="grow"></span>
          <button class="act primary" onclick="savePrompt('${esc(cur.name)}')">Применить</button>
          ${cur.overridden?`<button class="act" onclick="resetPrompt('${esc(cur.name)}')">Вернуть как в коде</button>`:''}
        </div>
        <textarea id="ptext" spellcheck="false"
          style="width:100%;height:420px;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
                 background:var(--code);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:12px"
        >${esc(cur.overridden ? cur.value : cur.default)}</textarea>
        <div class="hint" style="margin-top:6px">Сохранение действует на живой продукт в течение нескольких
          секунд, без перезапуска сервиса. Пустой текст настройкой не считается — вернётся код.</div>
      </div>
    </div>
  </div>`;
};

async function savePrompt(name){
  const v = document.getElementById('ptext').value;
  if (v.trim().length < 20){ toast('Слишком коротко — такой текст не будет применён', true); return; }
  try {
    await api('/api/admin/settings', { body: { prompts: { [name]: v } } });
    S.set = await api('/api/admin/settings');
    toast('Промпт применён'); render();
  } catch(e){ toast(e.message, true); }
}
async function resetPrompt(name){
  try {
    await api('/api/admin/settings', { body: { prompts: { [name]: null } } });
    S.set = await api('/api/admin/settings');
    toast('Вернул текст из кода'); render();
  } catch(e){ toast(e.message, true); }
}

// ---------------------------------------------------------------- Жалобы
/*
 * ОЧЕРЕДЬ, КОТОРОЙ НЕ БЫЛО. Жалобы писались исправно и не читались никем: строки копились в
 * хранилище матчинга, а экрана не существовало. «Спасибо, посмотрим» было фразой без адресата.
 *
 * Две вещи, которые видно сразу и которые решают дело: сколько ВСЕГО жалоб на этого человека
 * (одна — чей-то плохой вечер, пятая — уже картина) и что модератор с этой жалобой сделал.
 * Решение хранится ОТДЕЛЬНО от самой жалобы: список жалоб матчинг переписывает целым ключом из
 * своей памяти, и пометка внутри строки исчезла бы при следующей жалобе от кого угодно.
 *
 * Ответ доходит до человека. Это и было главной претензией: жалоба уходила в тишину.
 */
LOADERS.reports = async () => {
  busy('reports', true); S.reports_err='';
  try {
    const qs = S.rrq ? ('?reason=' + encodeURIComponent(S.rrq)) : '';
    S.reports = await api('/api/admin/reports' + qs); S.reports_busy=false; render();
  } catch(e){ fail('reports', e); }
};

/* ── РАЗБОР КАРТОЧКИ ВТОРОЙ МОДЕЛЬЮ ───────────────────────────────────────────────────────────
 * Обученная Qwen3-1.7B читает разговор вторым, независимым чтением и отдаёт занятие, предмет и
 * чипы. Смотреть на неё нужно ровно там же, где на батарею: это те же разговоры.
 * Главное в плитке ответов — последний столбец: что дала фильтрация против того, что сказала
 * модель. Расхождения подсвечены, совпадения намеренно бледные. */
function разборПлитки(){
  const d = S.card;
  if (!d) return батПлитка('РАЗБОР КАРТОЧКИ', 'вторая модель', '<div class="т-тихо">читаю…</div>', 12, 0, 'бат-разбор');
  const s = d.summary || {}, ob = s['обучение'] || {}, nb = s['набор'] || {}, ex = s['экзамен_эталон_500'] || {};
  const жив = d.alive
    ? '<span class="т-вверх">● ОТВЕЧАЕТ</span>' + (d.median_ms ? ' <span class="т-тихо">' + d.median_ms + ' мс</span>' : '')
    : '<span class="т-вниз">● МОЛЧИТ</span>';

  const учёба =
    '<div class="т-строка"><span class="т-имя">набор</span><b>' + num(nb['пар_всего']) + '</b> пар' +
      ' <span class="т-тихо">разговоров ' + num(nb['уникальных_разговоров']) + '</span></div>' +
    '<div class="т-строка"><span class="т-имя">языки</span><span class="т-тихо">' +
      esc(Object.entries(nb['языки'] || {}).map(([k, v]) => k + ' ' + v).join(' · ')) + '</span></div>' +
    '<div class="т-строка"><span class="т-имя">обучение</span>' + num(ob['эпох']) + ' эпохи · ' +
      num(ob['минут']) + ' мин · ' + (ob['видеопамять_ГБ'] || '—') + ' ГБ</div>' +
    '<div class="т-строка"><span class="т-имя">потеря</span><span class="т-тихо">' +
      esc((ob['loss'] || []).join(' → ')) + '</span></div>' +
    '<div class="т-строка"><span class="т-имя">на проверке</span><span class="т-тихо">' +
      esc((ob['eval_loss'] || []).join(' → ')) + '</span></div>' +
    '<div class="т-строка"><span class="т-имя">экзамен</span>не про то <b class="т-вверх">' +
      ((ex['затея_не_про_то'] || {}).модель ?? '—') + '</b> против ' +
      ((ex['затея_не_про_то'] || {}).сборка ?? '—') + '</div>' +
    '<div class="т-строка"><span class="т-имя">&nbsp;</span>отвергнутое <b class="т-вверх">' +
      ((ex['взяла_отвергнутое'] || {}).модель ?? '—') + '</b> против ' +
      ((ex['взяла_отвергнутое'] || {}).сборка ?? '—') + '</div>' +
    (d.why ? '<div class="т-строка т-вниз">' + esc(d.why) + '</div>' : '');

  const строки = (d.calls || []).slice(0, 14).map(c => {
    const g = c.got || {}, было = (c.was || []).join(', '), key = g.key || '';
    const расход = key && было && было.split(', ').indexOf(key) < 0;
    return '<div class="т-ряд">' +
      '<span class="т-тихо" style="flex:1 1 46%;overflow:hidden;text-overflow:ellipsis">' +
        esc((c.says || []).join(' | ').slice(0, 90)) + '</span>' +
      '<b class="' + (расход ? 'т-вниз' : '') + '" style="flex:0 0 22%">' + esc(key || '—') + '</b>' +
      '<span class="т-тихо" style="flex:0 0 22%">' + esc(было || '—') + '</span>' +
      '<span class="т-тихо" style="flex:0 0 10%;text-align:right">' + (c.ms || '—') + '</span></div>';
  }).join('') || '<div class="т-тихо">пусто — сборщик зовёт модель только при KLEAL_CARD_URL</div>';

  return батПлитка('РАЗБОР КАРТОЧКИ', жив, учёба, 4, 0, 'бат-разбор') +
    батПлитка('ЧТО ОТВЕЧАЕТ МОДЕЛЬ', 'разговор · модель · фильтрация · мс — красным расхождения',
      строки, 8, 0, 'бат-разбор-ответы');
}

VIEWS.reports = () => {
  if (S.reports_busy) return `<div class="card"><span class="spin"></span> читаю очередь…</div>`;
  const d = S.reports;
  if (!d) return `<div class="card">${errBox('reports')}<button class="act primary" onclick="LOADERS.reports()">Загрузить</button></div>`;
  const rows = d.reports || [];
  const open = rows.filter(r=>!r.action).length;

  return `<div class="card">
    <h2>Жалобы <span class="pill">${num(d.total)}</span>
      ${open?`<span class="pill" style="background:var(--badbg);color:var(--bad)">без ответа: ${num(open)}</span>`:''}</h2>
    <div class="hint">Свежие сверху. «Всего на него» — сколько жалоб на этого же человека за всё время.
      ${d.near_cap?'<b class="bad">Очередь у предела в 2000 строк: самые старые начнут пропадать.</b>':''}</div>
    <div class="row" style="margin:10px 0">
      <select onchange="S.rrq=this.value;LOADERS.reports()">
        <option value="">все причины</option>
        ${(d.reasons||[]).map(r=>`<option value="${esc(r)}" ${S.rrq===r?'selected':''}>${esc(r)}</option>`).join('')}
      </select>
      <button class="act" onclick="LOADERS.reports()">Обновить</button>
    </div>
    ${rows.length?rows.map(r=>reportRow(r)).join(''):'<div class="hint">Пусто — жалоб нет.</div>'}
  </div>`;
};

/* Файл к жалобе — по токену панели: обычная ссылка токена не несёт, а без него файл не отдаётся. */
async function openEvidence(id, name){
  try {
    const r = await fetch('/api/admin/evidence/' + encodeURIComponent(id), { headers: { 'X-Admin-Token': TOK } });
    if (!r.ok) throw new Error('код ' + r.status);
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement('a'); a.href = url; a.download = name || id; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch(e){ toast('Файл не открылся: ' + e.message, true); }
}

function reportRow(r){
  const a = r.action;
  const grp = r.kind === 'group';
  const ev = (r.evidence||[]).map(e=>`<button class="act" onclick="openEvidence('${esc(e.id)}','${esc(e.name||'').replace(/'/g,"\\'")}')">📎 ${esc(e.name||'файл')} · ${Math.round((e.size||0)/1024)} КБ</button>`).join(' ');
  return `<div class="card" style="margin:10px 0;${a?'opacity:.72':''}">
    <div class="row">
      <b>${grp ? 'Группа «' + esc(r.group_title||r.gid||'') + '»' : esc(r.about)}</b>
      ${grp && r.case_no ? `<span class="pill">${esc(r.case_no)}</span>` : ''}
      <span class="pill">${esc(r.reason)}</span>
      ${r.about_count>1?`<span class="pill" style="background:var(--badbg);color:var(--bad)">всего на него: ${num(r.about_count)}</span>`:''}
      <span class="grow"></span>
      <span class="muted">${esc(new Date((r.at||0)*1000).toLocaleString('ru'))}</span>
    </div>
    <div class="muted" style="margin-top:4px">пожаловался: ${esc(r.by)}</div>
    ${r.text?`<div style="margin-top:8px">${esc(r.text)}</div>`
            :`<div class="hint" style="margin-top:8px">Текста нет — приложение его не присылает, есть только причина.</div>`}
    ${ev?`<div class="row" style="margin-top:8px">${ev}</div>`:''}
    ${a?`<div class="calm" style="margin-top:10px">${esc(a.status)}${a.answered?' · ответ отправлен':''}${a.note?' — '+esc(a.note):''}</div>`:`
    <div class="row" style="margin-top:10px">
      ${grp ? '' : `<button class="act" onclick="openPerson('${esc(r.about).replace(/'/g,"\\'")}','${esc(r.about_id||'')}')">Карточка</button>
      <button class="act" onclick="banFrom('${esc(r.about).replace(/'/g,"\\'")}','${esc(r.id)}','${esc(r.about_id||'')}')" style="color:var(--bad);border-color:var(--bad)">Заблокировать</button>`}
      <button class="act" onclick="closeReport('${esc(r.id)}','dismissed')">Без последствий</button>
    </div>
    <div class="row" style="margin-top:8px">
      <input id="ans_${esc(r.id)}" style="flex:1;min-width:240px" placeholder="ответ тому, кто пожаловался — придёт ему в приложение">
      <button class="act primary" onclick="answerReport('${esc(r.id)}','${esc(r.by).replace(/'/g,"\\'")}','${esc(r.by_id||'')}')">Ответить и закрыть</button>
    </div>`}
  </div>`;
}

async function closeReport(id, status, extra){
  try {
    await api('/api/admin/report/action', { body: Object.assign({ id, status }, extra||{}) });
    toast('Жалоба закрыта'); await LOADERS.reports();
  } catch(e){ toast(e.message, true); }
}
async function answerReport(id, to, toId){
  const el = document.getElementById('ans_' + id);
  const text = (el && el.value || '').trim();
  if (text.length < 2){ toast('Напиши ответ — он придёт человеку в приложение', true); return; }
  await closeReport(id, 'answered', { answer: text, to, to_id: toId||'' });
}
async function banFrom(name, rid, id){
  if (!confirm('Заблокировать ' + name + '?\n\nЕго перестанут находить в поиске и звать в группы, открытые приглашения снимутся, назначенные встречи отменятся.')) return;
  try {
    const r = await api('/api/admin/ban', { body: { name, id: id||'', on: true } });
    if (r.ok === false) throw new Error(r.error || 'не вышло');
    const c = r.swept || {};
    toast('Заблокирован' + (c.plans||c.requests ? ` · снято приглашений: ${c.requests||0}, встреч: ${c.plans||0}` : ''));
    if (rid) await closeReport(rid, 'banned');
    if (S.users) await LOADERS.users();
  } catch(e){ toast(e.message, true); }
}
async function unban(name, id){
  try {
    await api('/api/admin/ban', { body: { name, id: id||'', on: false } });
    toast('Блокировка снята'); if (S.pname === name) await loadPerson();
    if (S.users) await LOADERS.users();
  } catch(e){ toast(e.message, true); }
}

// ---------------------------------------------------------------- Учётки
/*
 * Человек и его учётка лежали в разных местах и не сопоставлялись вовсе: профиль — в базе по
 * имени, почта и входы — в файле. Для поддержки это означало «вижу профиль, но не могу сказать,
 * заходил ли он вообще». Здесь они рядом, и отсюда же делаются две вещи, которых не было:
 * отозвать входы и удалить учётку целиком.
 */
LOADERS.accounts = async () => {
  busy('accounts', true); S.accounts_err='';
  try { S.accs = await api('/api/admin/accounts' + (S.aq?('?q='+encodeURIComponent(S.aq)):'')); S.accounts_busy=false; render(); }
  catch(e){ fail('accounts', e); }
};

function accountsCard(){
  const d = S.accs;
  return `<div class="card">
    <h2>Учётки ${d?`<span class="pill">${num(d.count)}</span>`:''}</h2>
    <div class="hint">Почта, когда заведена и сколько живых входов. Пароли и токены сюда не попадают.</div>
    <div class="row" style="margin:10px 0">
      <input style="flex:1;min-width:220px" placeholder="почта или имя" value="${esc(S.aq||'')}"
        onchange="S.aq=this.value;LOADERS.accounts()">
      <button class="act" onclick="LOADERS.accounts()">${d?'Обновить':'Загрузить'}</button>
    </div>
    ${errBox('accounts')}
    ${S.accounts_busy?'<span class="spin"></span> читаю…':''}
    ${d?`<div class="scroll"><table><thead><tr><th>почта</th><th>имя</th><th>входов</th><th>заведена</th><th></th></tr></thead><tbody>
    ${(d.accounts||[]).map(a=>`<tr>
      <td>${esc(a.email)}</td><td>${esc(a.name||'')}</td>
      <td>${num(a.sessions)}</td>
      <td class="muted">${a.created?esc(new Date(a.created*1000).toLocaleDateString('ru')):'—'}</td>
      <td style="white-space:nowrap">
        ${a.sessions?`<button class="act" onclick="revoke('${esc(a.key).replace(/'/g,"\\'")}')">Отозвать входы</button>`:''}
        <button class="act" style="color:var(--bad);border-color:var(--bad)"
          onclick="delAccount('${esc(a.key).replace(/'/g,"\\'")}','${esc(a.email).replace(/'/g,"\\'")}')">Удалить учётку</button>
      </td></tr>`).join('')}
    </tbody></table></div>`:''}
  </div>`;
}

async function revoke(key){
  if (!confirm('Отозвать все входы для ' + key + '?\n\nЧеловека разлогинит на всех устройствах, войти он сможет заново по коду на почту.')) return;
  try {
    const r = await api('/api/admin/account/revoke', { body: { account: key } });
    if (!r.ok) throw new Error(r.error||'не вышло');
    toast('Снято входов: ' + r.revoked); await LOADERS.accounts();
  } catch(e){ toast(e.message, true); }
}

/**
 * Удаление учётки — единственное действие панели, которое нельзя отменить.
 * Поэтому сперва СПРАШИВАЕМ сервер, кого именно удалим, показываем это человеку, и только потом
 * просим впечатать почту. Связь «учётка → строка в популяции» держится полем владельца; когда она
 * не разрешается однозначно, сервер отказывает, а не угадывает: тёзки в базе неразличимы.
 */
async function delAccount(key, email){
  let who;
  try { who = await api('/api/admin/account/resolve', { body: { account: key } }); }
  catch(e){ toast(e.message, true); return; }
  if (!who.ok){
    toast('Удалять нельзя: ' + (who.error||'') + (who.candidates?(' · кандидатов: '+who.candidates.length):''), true);
    return;
  }
  const lines = [
    'Удалить учётку без возврата.',
    '',
    'почта: ' + (who.email||key),
    'человек: ' + (who.name || '— строки в популяции нет'),
    'живых входов: ' + who.sessions,
    (who.warning ? '\nвнимание: ' + who.warning : ''),
    '',
    'Будут стёрты: учётка и все входы, строка в популяции, переписки, встречи и приглашения.',
    '',
    'Впечатай почту, чтобы подтвердить:'
  ].join('\n');
  const typed = prompt(lines, '');
  if (typed === null) return;
  if (typed.trim().toLowerCase() !== String(who.email||key).trim().toLowerCase()){
    toast('Почта не совпала — ничего не тронул', true); return;
  }
  try {
    const r = await api('/api/admin/account/delete', { body: { account: key } });
    if (!r.ok) throw new Error((r.deleted&&r.deleted.error) || r.error || 'не вышло');
    const g = (r.purged&&r.purged.purged) || {};
    toast('Удалено · переписок: ' + (g.messages||0) + ', встреч: ' + (g.plans||0));
    await LOADERS.accounts(); if (S.users) await LOADERS.users();
  } catch(e){ toast(e.message, true); }
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
envPill();
render();
(LOADERS[TAB]||(()=>{}))();
</script></body></html>'''
