/**
 * Склонение имён в интерфейсе.
 *
 * Приложение обращается к человеку по имени десятки раз: «Пригласить Костя?», «Написать Костя…»,
 * «Создаю план с Костя», «откроется чат с Даша». Все они собраны шаблоном `${name}` и потому стоят
 * в именительном падеже — по-русски это читается как машинный перевод, ровно тот же дефект речи,
 * что и склейка слов.
 *
 * Правила ниже покрывают обычные русские имена и НЕ трогают:
 *  — латиницу (Timur, Marco): такие имена в русском тексте не склоняются;
 *  — имена на -о/-е/-и/-у/-ы/-э/-ю (Отто, Мери, Люси): несклоняемые и так;
 *  — составные строки с пробелом (полное имя из пула): падеж там угадывать нечем.
 *
 * Где ошибётся: женское имя, оканчивающееся на согласную (Кармен, Мадлен). Пол по имени не
 * определить, а в плане и переписке его нет вовсе — сервер отдаёт только имя. Такие имена
 * заимствованные и редкие; менять из-за них падеж у Ивана, Тимура и Максима было бы хуже.
 */

export type NameCase = 'acc' | 'gen' | 'dat' | 'ins';

const CYR = /^[А-Яа-яЁё-]+$/;
/** Заднеязычные и шипящие: после них в родительном пишется «и», а не «ы» (Маша → Маши). */
const HUSH = 'гкхжчшщ';
/** Только шипящие и «ц»: в творительном после них «-ей», а не «-ой» (Даша → Дашей, не Дашой). */
const SIB = 'жчшщц';

/**
 * Беглая гласная: в косвенных падежах она выпадает, и правило «согласная + а» даёт «Пётра»
 * вместо «Петра». Имён с таким чередованием немного, и это ровно те, что встречаются часто.
 */
const IRREGULAR: Record<string, string> = {
  'пётр': 'Петр', 'петр': 'Петр',
  'лев': 'Льв',
  'павел': 'Павл',
  'михаил': 'Михаил', 'даниил': 'Даниил',   // регулярные, но пусть стоят явно
};

export function nameCase(raw: string, form: NameCase): string {
  const name = String(raw || '').trim();
  if (!name || name.includes(' ') || !CYR.test(name)) return name;
  const odd = IRREGULAR[name.toLowerCase()];
  if (odd) {
    if (form === 'acc' || form === 'gen') return odd + 'а';
    if (form === 'dat') return odd + 'у';
    return odd + 'ом';
  }
  const last = name.slice(-1);
  const stem = name.slice(0, -1);
  const prev = stem.slice(-1).toLowerCase();

  // Даша, Анна, Никита, Лёша
  if (last === 'а') {
    if (form === 'acc') return stem + 'у';
    if (form === 'gen') return stem + (HUSH.includes(prev) ? 'и' : 'ы');
    if (form === 'dat') return stem + 'е';
    return stem + (SIB.includes(prev) ? 'ей' : 'ой');
  }
  // Костя, Катя, Женя, Илья
  if (last === 'я') {
    if (form === 'acc') return stem + 'ю';
    if (form === 'gen' || form === 'dat') return stem + (form === 'gen' ? 'и' : 'е');
    return stem + 'ей';
  }
  // Андрей, Сергей
  if (last === 'й') {
    if (form === 'acc' || form === 'gen') return stem + 'я';
    if (form === 'dat') return stem + 'ю';
    return stem + 'ем';
  }
  // Игорь
  if (last === 'ь') {
    if (form === 'acc' || form === 'gen') return stem + 'я';
    if (form === 'dat') return stem + 'ю';
    return stem + 'ем';
  }
  // Несклоняемые окончания.
  if ('оеиуыэю'.includes(last.toLowerCase())) return name;
  // Согласная: Иван, Тимур, Максим.
  if (form === 'acc' || form === 'gen') return name + 'а';
  if (form === 'dat') return name + 'у';
  return name + 'ом';
}

/** Короткие обёртки — чтобы в строках копии читалось падежом, а не аргументом. */
export const acc = (n: string) => nameCase(n, 'acc');   // вижу кого — «Пригласить Костю»
export const gen = (n: string) => nameCase(n, 'gen');   // нет кого — «у Кости»
export const dat = (n: string) => nameCase(n, 'dat');   // кому — «Написать Косте»
export const ins = (n: string) => nameCase(n, 'ins');   // с кем — «с Костей»
