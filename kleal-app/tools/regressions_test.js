// Три починки 10 августа 2026 — покрытие по исходникам приложения.
//
//   node tools/regressions_test.js
//
// Тот же приём, что в kleal-ms/tools/*_test.js: утверждения читаются из НАСТОЯЩИХ файлов, поэтому
// проверка не может пройти на коде, где правку выкинули или переименовали. Каждая из трёх ошибок
// была невидимой — ни падения, ни красной строки, — и заметить возврат можно только так.
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

// Исходник БЕЗ комментариев. В этом проекте комментарии длинные и цитируют неправильный код
// («в профиле стояло ImageManipulator.manipulate(...)»), поэтому поиск по всему тексту находит
// описание ошибки и объявляет её живой. Проверка обязана смотреть на то, что исполняется.
const code = (p) => read(p).replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');

let failed = 0;
function check(name, ok, detail) {
  if (ok) {
    console.log('  ok   ' + name);
  } else {
    failed++;
    console.log('  FAIL ' + name + (detail ? '\n         ' + detail : ''));
  }
}

// ---------------------------------------------------------------- 1. интересы доезжают до сервера
//
// «Профиль → Интересы → Добавить» ведёт в разговор, а тот пишет только в состояние на устройстве:
// /api/onboarding/chat в стор не пишет, выход из разговора просто переключает экран. Отправляли
// интересы лишь тумблер и удаление, поэтому человек, который больше ничего не трогал, оставался
// невидим по тому, что сам про себя рассказал. Сводку при этом сторож отправлял — и в строке
// оставался рассказ про интерес, которого нет в списке.
console.log('\nинтересы из профиля доезжают до сервера');
{
  const scr = read('app/profile/interests.tsx');
  const mod = read('src/profile.ts');

  check('экран отправляет интересы при возвращении на него',
    /useFocusEffect\(/.test(scr) && /pushInterests\(\)/.test(scr),
    'ушёл useFocusEffect — интерес из разговора снова останется на телефоне');

  check('pushInterests существует и шлёт плоский список',
    /export async function pushInterests/.test(mod) && /patchFor\(\['interests'\]\)/.test(mod),
    'вложенный объект сервер запишет слепым row.update() и сломает матчинг молча');

  check('запись идёт через profile-update, а не мимо',
    /profileApi\.update\(name, patch\)/.test(mod));

  check('до регистрации ничего не шлётся',
    /if \(!name \|\| !st\.done\) return false/.test(mod),
    'иначе patch уедет для человека, которого на сервере ещё нет');

  check('отпечаток обновляется только после удачной записи',
    mod.indexOf('_sentInterests = sig') > mod.indexOf('const r: any = await profileApi.update'),
    'иначе неудачная отправка запомнится как удачная и повтора не будет');
}

// ---------------------------------------------------------------- 2. со сводки нельзя уйти мимо записи
//
// «Все настройки профиля» делала router.push('/done') без регистрации: человек получал
// поздравление, не существуя в users.json, и `done` не ставился — следующий запуск открывал интро.
console.log('\nсо сводки нельзя уйти, не записав профиль');
{
  const scr = read('app/summary.tsx');

  check('оба выхода идут через register()',
    /const finish = async \(\) => \{\s*if \(await register\(\)\)/.test(scr) &&
    /const toProfile = async \(\) => \{\s*if \(await register\(\)\)/.test(scr),
    'выход без проверки результата = уход с непрописанным профилем');

  check('нет перехода на /done мимо регистрации',
    !/onPress=\{\(\) => router\.(push|replace)\('\/done'\)\}/.test(scr),
    'ровно так и выглядела ошибка');

  check('done ставится только после успешного register',
    /patch\(\{ done: true \}\);\s*\n\s*return true;/.test(scr));

  check('«Все настройки профиля» ведёт в профиль, а не в финал',
    /onPress=\{sending \? undefined : toProfile\}/.test(scr));
}

// ---------------------------------------------------------------- 3. подготовка фото — одна на двоих
//
// В профиле стоял ImageManipulator.manipulate(...), а модуль отдаёт класс со статическим методом:
// такого экспорта нет. try/catch тоже не было, поэтому смена фото молча не работала. В онбординге
// та же функция была написана правильно — две копии разошлись на одну строку.
console.log('\nподготовка фото не может снова разъехаться');
{
  const files = ['app/profile/index.tsx', 'app/chat.tsx', 'src/photo.ts'];
  const bad = files.filter((f) => /(?<!ImageManipulator\.)ImageManipulator\.manipulate\(/.test(code(f)));

  check('плоского ImageManipulator.manipulate( нет нигде', bad.length === 0, 'нашлось в: ' + bad.join(', '));

  check('оба экрана зовут общий squarePhoto',
    /squarePhoto\(/.test(code('app/profile/index.tsx')) && /squarePhoto\(/.test(code('app/chat.tsx')),
    'вернулась вторая копия — значит вернётся и расхождение');

  check('в модуле вызов через класс',
    /ImageManipulator\.ImageManipulator\.manipulate\(/.test(code('src/photo.ts')));

  check('сбой подготовки виден человеку',
    /catch \{[\s\S]{0,200}setPhotoErr\(/.test(code('app/profile/index.tsx')),
    'без этого следующий сбой снова будет тишиной');
}

// ------------------------------------------------- 4. кадр группового плана считается в одном месте
//
// `frameOf` в app/gplan.tsx решает, какой кадр борда показать, и у него есть ПОРТ на питоне —
// `frame_of` в kleal-ms/tools/gplan_screen_smoke.py. Порт нужен, чтобы гонять все состояния по
// живому серверу без симулятора; ценой этого стало второе место, где записан порядок веток.
// Разойдутся — тест продолжит зеленеть на логике, которой в приложении уже нет.
console.log('\nкадр группового плана считается по одному правилу');
{
  const ts = code('app/gplan.tsx');
  const py = fs.readFileSync(path.join(ROOT, '..', 'kleal-ms/tools/gplan_screen_smoke.py'), 'utf8');

  // Имена кадров в порядке появления. Берём ИМЕННО возвращаемые значения, по одному return'у за
  // раз: тернарник отдаёт сразу два имени, а состояния плана ('locked', 'proposed') стоят в
  // условии и в возврат не попадают. Лишние строки внутри return (вроде plan.get("can_fix"))
  // отсекает словарь кадров — других имён у экрана нет.
  const FRAMES = new Set(['none', 'proposed', 'confirmed', 'fix', 'stayOrLeave', 'acceptOrLeave',
                          'voteOpen', 'voteDecide', 'voteWait', 'locked', 'below', 'closed']);
  const pick = (body, re, q) => [...body.matchAll(re)]
    .flatMap((m) => [...m[1].matchAll(new RegExp(`${q}([a-zA-Z_]+)${q}`, 'g'))].map((x) => x[1]))
    .filter((n) => FRAMES.has(n));

  const tsBody = (ts.match(/function frameOf\([\s\S]*?\n\}/) || [''])[0];
  const pyBody = (py.match(/def frame_of\([\s\S]*?\n\n/) || [''])[0];
  const tsOrder = pick(tsBody, /return ([^;]+);/g, "'");
  const pyOrder = pick(pyBody, /return (.+)$/gm, '"');

  check('порт на питоне вообще нашёлся', pyOrder.length > 0, 'gplan_screen_smoke.py переименован?');
  check('порядок веток совпадает с точностью до имени',
    tsOrder.join(',') === pyOrder.join(','),
    'экран: ' + tsOrder.join(',') + '\n         тест:  ' + pyOrder.join(','));

  // Порядок — не украшение: личный выбор обязан идти РАНЬШЕ общего состояния плана, иначе человеку
  // с «останься или выйди» покажут обычный утверждённый план и вопроса он не увидит.
  const iStay = tsOrder.indexOf('stayOrLeave');
  const iAccept = tsOrder.indexOf('acceptOrLeave');
  const iConfirmed = tsOrder.indexOf('confirmed');
  check('личный выбор проверяется раньше общего состояния',
    iStay >= 0 && iAccept >= 0 && iStay < iConfirmed && iAccept < iConfirmed,
    'иначе GR.31/GR.33 не покажутся вовсе');

  // Правила сервера экран не пересчитывает — он читает флаги. Своя арифметика по раундам здесь
  // уже разъезжалась с сервером в 1:1, и повторять это незачем.
  check('экран не считает раунды сам',
    !/round[^)]{0,20}>=\s*3|rounds\s*>\s*3/.test(ts),
    'потолок раундов приходит с сервера (max_rounds), сам его выводить нельзя');
}

// ------------------------------------------------- 5. профиль под поиск уходит в форме сервера
//
// Сервер читает языки как prof['languages']['comfortable'] — объектом. Два экрана отдавали плоский
// список, и match_candidates_legacy падал на первой же строке с «'list' object has no attribute
// 'get'». Обработчик клал текст исключения в ответ, экран рисовал пустую выдачу, и человек читал
// это как «никого подходящего нет». Поиск людей не работал ВООБЩЕ — ни в группу, ни один на один.
console.log('\nпрофиль под поиск уходит в форме, которую сервер понимает');
{
  const callers = ['app/intent.tsx', 'app/group.tsx', 'app/buddy.tsx', 'app/create.tsx'];
  const flat = callers.filter((f) => /languages:\s*[^,\n]*\.comfortable/.test(code(f)));

  check('никто не расплющивает languages в список', flat.length === 0,
    'плоский список в: ' + flat.join(', ') + ' — сервер ждёт объект {comfortable: [...]}');

  // Сервер обязан пережить и плоский список: цена ошибки в одном поле не должна быть
  // «поиск не находит никого», потому что такую поломку замечают не по логу, а через неделю.
  const srv = fs.readFileSync(path.join(ROOT, '..', 'kleal-ms/services/matching/app.py'), 'utf8');
  check('сервер терпит обе формы', /def _langs_of\(/.test(srv) && /_langs_of\(prof\)/.test(srv),
    'вернулся прямой prof.get("languages").get("comfortable")');
  check('упавший поиск пишет трассировку, а не только текст ошибки',
    /_blew_up\("\/api\/agent\/match"/.test(srv),
    'без этого следующее падение снова будет выглядеть как «никого не нашлось»');
}

// ------------------------------------------------- 6. у плана есть НАСТОЯЩЕЕ время, а не подпись
//
// В экране группового плана время спрашивалось текстовым полем — «например: чт 24 июля, 20:30».
// Вид не совпадал ни с кадром GR.09, ни с соседним мастером интента, но хуже было другое: у плана
// не оказывалось момента времени вовсе. Сервер считает двухчасовой замок и отказ TOO_LATE по
// `starts_at`, а он не отправлялся — групповой план нельзя было ни заморозить перед встречей, ни
// отклонить как назначенный на прошлое. Проверено: до правки план на час вперёд создавался.
console.log('\nу группового плана есть момент времени, а не только подпись');
{
  const gp = code('app/gplan.tsx');

  check('время выбирают пикером с кадра, а не печатают',
    /<WhenPicker/.test(gp) && !/value=\{when\}\s+onChangeText/.test(gp),
    'вернулось текстовое поле — вместе с ним вернётся и план без starts_at');

  check('пикер общий с мастером интента, а не своя копия',
    /from '\.\.\/src\/components\/WhenPicker'/.test(gp) &&
    fs.existsSync(path.join(ROOT, 'src/components/WhenPicker.tsx')),
    'две копии выбора времени разъедутся так же, как разъехалась подготовка фото');

  // Все три отправки условий — создание, встречное предложение, правка — обязаны слать момент.
  // Голосование за перенос тоже: без него принятый советом перенос оставил бы план без времени.
  check('момент уходит вместе с подписью',
    /const timeArgs = \(\) => \(\{ when: whenLabel\(when\), starts_at: whenStartsAt\(when\) \}\)/.test(gp),
    'если timeArgs переименовали — проверь, что starts_at всё ещё уходит');
  // Четыре ВЫЗОВА: создать план, предложить своё, править сверху, позвать на голосование.
  // Объявление сюда не попадает: в нём стоит `timeArgs = ()`, а не `timeArgs()`.
  const senders = (gp.match(/timeArgs\(\)/g) || []).length;
  check('его шлют все четыре действия (создать, предложить, править, голосовать)',
    senders === 4, 'нашлось отправок: ' + senders);
}

// ------------------------------------------------- 7. mediaUrl не портит абсолютные адреса
//
// Помощник дописывает базу к относительному пути картинки. Список пропуска был перечнем ЗНАКОМЫХ
// схем (http, file, blob), поэтому своё фото — а это всегда `data:image/jpeg;base64,…` из
// src/photo.ts — получало базу спереди: «https://…comdata:image/…». Такой адрес не разбирается
// как URL, и React Native падает КРАСНЫМ ЭКРАНОМ «URI parsing error» в нативном ImageManager.
// Тем же объясняется «в профиле нет аватарки»: там всегда своё фото.
console.log('\nmediaUrl не ломает абсолютные адреса');
{
  const src = code('src/api.ts');
  const m = src.match(/export const mediaUrl = \(url: string\) =>\s*([\s\S]*?);/);
  check('mediaUrl нашёлся', !!m, 'переименовали?');

  if (m) {
    // Собираем НАСТОЯЩУЮ функцию из исходника: проверять регуляркой по тексту — значит проверять
    // формулировку, а не поведение.
    const API_BASE = 'https://base.example';
    const mediaUrl = new Function('url', 'API_BASE', 'return (' + m[1] + ');');
    const cases = [
      ['data:image/jpeg;base64,AAAA', 'data:image/jpeg;base64,AAAA', 'своё фото — data-URL'],
      ['file:///tmp/a.jpg', 'file:///tmp/a.jpg', 'файл с устройства'],
      ['blob:abc', 'blob:abc', 'blob'],
      ['https://a.b/c.jpg', 'https://a.b/c.jpg', 'уже абсолютный'],
      ['', '', 'пусто остаётся пустым'],
      ['/api/onboarding/photo/x.jpg', API_BASE + '/api/onboarding/photo/x.jpg', 'чужое фото — путь с сервера'],
    ];
    for (const [input, want, what] of cases) {
      let got;
      try { got = mediaUrl(input, API_BASE); } catch (e) { got = 'ОШИБКА: ' + e.message; }
      check(what, got === want, 'дано ' + JSON.stringify(input) + ' → ' + JSON.stringify(got));
    }
  }
}

// ------------------------------------------------- 8. профиль читает поле в ОБЕИХ его формах
//
// Третий случай одного и того же класса за два дня, поэтому проверка отдельная:
//   — `languages`: экран слал плоский список, сервер ждал объект → ранжирование падало, и это
//     выглядело как «никого не нашлось»;
//   — `interests`: экран читал `interests.explicit`, сервер отдаёт ПЛОСКИЙ список (проверено на
//     проде: {"interests": ["sports","team","rugby",…]}) → «Интересы · Пока не заполнено» у
//     человека с восемью интересами;
//   — `photo`: свой снимок — data-URL, чужой — путь с сервера (см. проверку mediaUrl выше).
// Общее у всех трёх: одно поле живёт в двух формах, и несовпадение даёт МОЛЧАЛИВУЮ пустоту
// вместо ошибки. Такое находят не по логу, а через неделю и случайно.
console.log('\nпрофиль понимает обе формы своих полей');
{
  const prof = code('src/profile.ts');

  check('есть один помощник, понимающий обе формы интересов',
    /export function explicitInterests\(/.test(prof) && /Array\.isArray\(raw\)/.test(prof),
    'с сервера интересы приходят массивом, из онбординга — объектом .explicit');

  // Главное — что читателей ОДИН. Копий было две (строка хаба и profileData), первую починили,
  // вторая осталась врать — и именно её человек видел на экране: «Интересы · Пока не заполнено»
  // при восьми интересах. Прямое чтение `.interests.explicit` мимо помощника и есть возврат копии.
  const direct = ['src/profile.ts', 'app/profile/index.tsx', 'app/profile/interests.tsx', 'src/home.ts']
    .filter((f) => /\.interests\?\.explicit|\.interests\.explicit/.test(code(f)));
  check('никто не читает interests.explicit в обход помощника', direct.length === 0,
    'прямое чтение в: ' + direct.join(', '));

  // Языки на клиенте уже читаются обеими формами (comfortable || fluent); держим это.
  check('языки читаются обеими формами',
    /op\.languages\.comfortable \|\| op\.languages\.fluent/.test(prof));

  const srv = fs.readFileSync(path.join(ROOT, '..', 'kleal-ms/services/matching/app.py'), 'utf8');
  check('и сервер терпит обе формы языков', /def _langs_of\(/.test(srv),
    'помощник _langs_of исчез — вернётся падение ранжирования');
}

// ------------------------------------------------- 9. голосовое: удержание и размер пузыря
//
// Две разные поломки в одном файле, обе видны глазами и обе тихие в коде.
console.log('\nголосовое ведёт себя как в мессенджерах');
{
  const v = code('src/voice.tsx');

  // Пузырь. `flex: 1` у playRow в КОЛОНКЕ означает «займи оставшуюся высоту», и шестисекундное
  // сообщение разворачивалось красным полотном почти на весь экран. Признак `grow` разделяет
  // строку композера и колонку пузыря; вернуть flex:1 в общий стиль — вернуть полотно.
  check('проигрыватель растягивается только там, где его об этом просят',
    /playRowGrow: \{ flex: 1 \}/.test(v) && !/playRow: \{[^}]*flex: 1/.test(v),
    'flex:1 вернулся в общий playRow — пузырь снова станет во весь экран');
  check('и просят об этом только в композере',
    (v.match(/<AudioPlay[^>]*grow/g) || []).length === 1,
    'grow должен стоять ровно у одного вызова — в превью композера');

  // Механика записи: прижал → пишет, отпустил → ушло, вверх → закрепил, влево → отмена.
  check('запись идёт по удержанию, а не по тапу', /PanResponder\.create\(/.test(v));
  check('отпускание отправляет без промежуточного шага',
    /onPanResponderRelease/.test(v) && /stopAndSend\(\)/.test(v),
    'иначе снова три касания: начать, стоп, отправить');
  check('есть закрепление протяжкой вверх', /LOCK_AT/.test(v) && /dy < LOCK_AT/.test(v));
  check('есть отмена протяжкой влево', /CANCEL_AT/.test(v) && /dx < CANCEL_AT/.test(v),
    'запись, которую нельзя оборвать, — ловушка');
  check('отмену промахнуться труднее, чем закрепление',
    /const LOCK_AT = -56/.test(v) && /const CANCEL_AT = -80/.test(v));
  check('перехват жеста считается отменой, а не отправкой',
    /onPanResponderTerminate/.test(v),
    'отправлять то, чего человек не заканчивал, нельзя');
  check('случайный тап не улетает шорохом',
    /MIN_DURATION_MS/.test(v) && /ms < MIN_DURATION_MS/.test(v));

  // Обработчики жеста создаются один раз — состояние они читать не могут, только ссылку.
  check('жест ходит к хуку через ссылку, а не через замыкание',
    v.indexOf('const voiceRef = useRef(voice)') < v.indexOf('const responder = useRef('),
    'иначе кнопка навсегда останется подключённой к первому рендеру');
}

console.log('');
if (failed) {
  console.log(failed + ' проверок не прошло');
  process.exit(1);
}
console.log('все проверки прошли');
