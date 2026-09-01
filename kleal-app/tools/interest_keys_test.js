/**
 * Каждый ключ, который приложение способно положить в профиль, обязан быть известен серверу.
 *
 * ЗАЧЕМ. С 27.08 онбординг проверяет интересы по общей таксономии и отклоняет ВЕСЬ вызов
 * `register`, если хоть один ключ неизвестен: `{"ok": false, "error": "unconfirmed interests: …"}`.
 * Одна неизвестная строка — и человек не может закончить анкету вообще, потому что обе кнопки на
 * сводке идут через `register`. Так и случилось: двенадцать ключей колоды сервер не знал, из них
 * восемь расходились только написанием (`museums` против `museum`, `photo` против `photography`).
 *
 * ЧТО ПРОВЕРЯЕМ ЗДЕСЬ. Оффлайн-половину: карта строится из дерева и `EXTRA_ROOT`, и ни один ключ
 * оттуда не должен оказаться неизвестным колоде или дереву. Полную проверку против живого каталога
 * делает tools/check_interest_keys.py — она требует доступа к серверу и потому отдельно.
 *
 * Запуск: node tools/interest_keys_test.js
 */
const fs = require('fs');
const path = require('path');

const read = (p) => fs.readFileSync(path.join(__dirname, '..', p), 'utf8');

const deck = [...read('src/interests-deck.ts').matchAll(/card\('([^']+)'/g)].map((m) => m[1]);
// Дерево теперь генерируется из общего реестра (kleal-ms/shared/interests.json) и лежит
// отдельным файлом. Читаем его: в interests-wheel.ts остались только помощники и копия.
const wheelSrc = read('src/interests-tree.generated.ts');
const tree = [...wheelSrc.matchAll(/\b(?:TOP|N)\('([^']+)'/g)].map((m) => m[1]);
const mm = read('src/mindmap.ts');

const extraBlock = mm.slice(mm.indexOf('const EXTRA_ROOT'), mm.indexOf('};', mm.indexOf('const EXTRA_ROOT')));
const extra = [...extraBlock.matchAll(/'?([a-z][a-z0-9_ ]*)'?\s*:\s*'([a-z]+)'/g)].map((m) => m[1].trim());
const off = [...mm.matchAll(/OFF_TAXONOMY = \[([^\]]+)\]/g)]
  .flatMap((m) => [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1]));

let bad = 0;
const fail = (msg) => { console.log('  ПАДАЕТ  ' + msg); bad++; };
const ok = (msg) => console.log('  ок      ' + msg);

// 1. Каждая карточка колоды либо в дереве, либо в EXTRA_ROOT, либо снята намеренно.
const treeSet = new Set(tree);
const extraSet = new Set(extra);
const offSet = new Set(off);
const lost = deck.filter((k) => !treeSet.has(k) && !extraSet.has(k) && !offSet.has(k));
lost.length ? fail(`карточки без категории и без пометки: ${lost.join(', ')}`)
            : ok(`все ${deck.length} карточек колоды разложены`);

// 2. Снятое намеренно действительно есть в колоде — иначе пометка протухла.
const stale = off.filter((k) => !deck.includes(k));
stale.length ? fail(`OFF_TAXONOMY указывает на несуществующие карточки: ${stale.join(', ')}`)
             : ok(`OFF_TAXONOMY (${off.length}) сходится с колодой`);

// 3. Ключи EXTRA_ROOT не должны дублировать дерево — иначе непонятно, чей родитель победит.
const dup = extra.filter((k) => treeSet.has(k));
dup.length ? fail(`EXTRA_ROOT дублирует ключи дерева: ${dup.join(', ')}`)
           : ok(`EXTRA_ROOT (${extra.length}) не пересекается с деревом`);

// 4. Ни один ключ не должен содержать кириллицу: в базе хранятся английские ручки.
const cyr = [...deck, ...tree, ...extra].filter((k) => /[А-Яа-яЁё]/.test(k));
cyr.length ? fail(`кириллица в ключах: ${cyr.join(', ')}`)
           : ok(`кириллицы в ключах нет (проверено ${deck.length + tree.length + extra.length})`);

console.log(bad ? `\n${bad} проверок упало` : '\nвсе проверки прошли');
process.exit(bad ? 1 : 0);
