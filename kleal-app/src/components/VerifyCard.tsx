/**
 * Блок «Пройди проверку» на экране «Что Kleal знает о тебе» (18.10.2026, Иван: «а там добавить красивый
 * блок с началом верификации»).
 *
 * Что даёт проверка — тремя строками, одна кнопка. Ведёт в тот же путь, что и обязательная проверка
 * возраста (src/age-verification.ts → сессия Didit → возврат kleal://age-verification, статус решает
 * только сервер). Никаких своих выводов «проверен» по возврату из браузера.
 *
 * Когда виден:
 *   • проверка пройдена (approved + 18+) — компактная плашка «Проверен»;
 *   • сервер разрешает начать (canStart) — приглашение с кнопкой;
 *   • иначе блока нет — ничего нерабочего человеку не показываем.
 *
 * ТЕСТОВЫЙ АВТОПРОХОД (Иван, 18.10.2026: «кнопку пройти автоматически, для тестировщиков, чтобы они
 * каждый раз не искали новые документы»). Тихая кнопка под основной, только когда сервер в тестовом
 * режиме (enrollment.testPass). Ставит «проверен» с пометкой test; снять — ссылкой в состоянии
 * «проверен (тест)». Обычный путь — только через Didit.
 */
import { useEffect, useState } from 'react';
import { AppState, Linking, StyleSheet, Text, View } from 'react-native';
import { T } from '../i18n';
import { isHostedVerificationURL } from '../age-verification';
import { api, getSession } from '../api';
import { getLang } from '../i18n';

/**
 * Статус добровольной проверки. НЕ через ageRequest: его строгая проверка ответа написана для
 * обязательного шлюза и считает «admitted:true при not_started» невозможным, а добровольный режим
 * отвечает именно так (контракт ЛОГИКИ, 18.10.2026). Здесь проверяем только то, на что смотрит блок.
 */
type VStatus = { status: string; over18: boolean; canStart: boolean; method?: string; url?: string; voluntary: boolean; onboarded: boolean };
const V_STATUSES = new Set(['not_started', 'pending', 'review', 'approved', 'declined', 'cancelled', 'expired', 'legacy_exempt']);
const asStatus = (r: any): VStatus | null =>
  r && V_STATUSES.has(String(r.status))
    ? { status: String(r.status), over18: r.over18 === true, canStart: r.canStart === true, method: r.method, url: typeof r.url === 'string' ? r.url : undefined,
        voluntary: r.voluntary === true, onboarded: r.onboarded !== false }
    : null;
async function vStatus(): Promise<VStatus | null> {
  if (!getSession()) return null;
  return asStatus(await api.get('/api/onboarding/age-verification/status'));
}
import { GlassSurface } from './LiquidGlass';
import { GlassPill } from './Glass';
import { IconVerified } from './icons';
import { color, font, space } from '../theme';

/** Прошёл ли человек проверку — по статусу сервера. Для галочки рядом с именем: рисовать её всем подряд
 *  значило бы обещать «проверен» тем, кому тут же предлагают проверку пройти. */
export function useAgeVerified(): boolean {
  const [ok, setOk] = useState(false);
  useEffect(() => {
    let alive = true;
    vStatus().then((r) => { if (alive) setOk(!!r && r.status === 'approved' && r.over18); }).catch(() => {});
    return () => { alive = false; };
  }, []);
  return ok;
}

/**
 * `ensureRegistered` — сохранить анкету (та же регистрация, что делает «Готово»). На сводке строки
 * человека ещё нет, и сервер не даёт начать проверку (onboarded:false) — поэтому блок виден в
 * добровольном режиме и до регистрации, а по нажатию сначала сохраняет анкету (баг Ивана 18.10).
 */
export function VerifyCard({ preview, onChange, ensureRegistered }: {
  preview?: 'start' | 'done'; onChange?: (verified: boolean) => void; ensureRegistered?: () => Promise<boolean>;
}) {
  const [res, setRes] = useState<VStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  /** Сервер в тестовом режиме — показываем автопроход (enrollment.testPass). */
  const [testPass, setTestPass] = useState(false);
  const [testBusy, setTestBusy] = useState(false);

  useEffect(() => {
    if (preview) return;
    let alive = true;
    const load = () => vStatus().then((r) => { if (alive) setRes(r); }).catch(() => {});
    load();
    api.get<{ testPass?: boolean }>('/api/onboarding/age-verification/enrollment')
      .then((e) => { if (alive) setTestPass(!!e?.testPass); }).catch(() => {});
    // Вернулись из браузера Didit — статус перечитываем с сервера.
    const sub = AppState.addEventListener('change', (s) => { if (s === 'active') load(); });
    return () => { alive = false; sub.remove(); };
  }, [preview]);

  const verified = preview === 'done' || (!!res && res.status === 'approved' && res.over18);
  const isTest = res?.method === 'test';
  // До регистрации сервер даёт canStart:false — в добровольном режиме блок всё равно виден (см. выше).
  const canStart = preview === 'start' || (!!res && !verified && (res.canStart || (res.voluntary && !res.onboarded)));

  /** Перед стартом — сохранить анкету, если её строки ещё нет. false — причину показал экран. */
  const ready = async (): Promise<boolean> => {
    if (!res || res.onboarded) return true;
    if (!ensureRegistered) return false;
    const ok = await ensureRegistered();
    if (ok) { const r = await vStatus().catch(() => null); if (r) setRes(r); }
    return ok;
  };
  useEffect(() => { onChange?.(verified); }, [verified]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Тестовый автопроход и его снятие. Ответ сервера — не полный статус, поэтому статус перечитываем. */
  const testCall = async (undo: boolean) => {
    if (testBusy) return;
    setTestBusy(true);
    setErr('');
    try {
      if (!undo && !(await ready())) { setErr(V.saveFirst()); return; }
      const r = await api.post<{ ok?: boolean; status?: string }>('/api/onboarding/age-verification/test-pass', undo ? { undo: true } : {});
      if (!r?.ok && !r?.status) throw new Error('test');
      setRes(await vStatus());
    } catch { setErr(V.later()); }
    finally { setTestBusy(false); }
  };

  if (!verified && !canStart) return null;

  if (verified) {
    return (
      <GlassSurface tone="light" radius={16} style={s.doneRow}>
        <IconVerified size={18} />
        <Text style={s.doneText}>{isTest ? V.doneTest() : V.done()}</Text>
        {isTest && testPass ? (
          <Text style={s.undo} onPress={() => testCall(true)} accessibilityRole="button">{testBusy ? '…' : V.undo()}</Text>
        ) : null}
      </GlassSurface>
    );
  }

  const start = async () => {
    if (busy || preview) return;
    setBusy(true);
    setErr('');
    try {
      if (!(await ready())) { setErr(V.saveFirst()); return; }
      // Каждый старт — платная сессия Didit: зовём только по нажатию человека.
      const r = asStatus(await api.post('/api/onboarding/age-verification/session', { language: getLang() }));
      if (r?.url && isHostedVerificationURL(r.url)) await Linking.openURL(r.url);
      else setErr(V.later());
    } catch { setErr(V.later()); }
    finally { setBusy(false); }
  };

  return (
    <View style={s.shadow}>
      <GlassSurface tone="light" radius={16} style={s.card}>
        <View style={s.head}>
          <View style={s.badge}><IconVerified size={22} /></View>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={s.title}>{V.title()}</Text>
            <Text style={s.sub}>{V.sub()}</Text>
          </View>
        </View>
        <View style={s.points}>
          {[V.p1(), V.p2(), V.p3()].map((t) => (
            <View key={t} style={s.point}>
              <View style={s.dot} />
              <Text style={s.pointText}>{t}</Text>
            </View>
          ))}
        </View>
        {err ? <Text style={s.err}>{err}</Text> : null}
        <GlassPill tone="light" label={V.start()} busy={busy} onPress={start} style={s.cta} />
        <Text style={s.note}>{V.note()}</Text>
        {testPass ? (
          /* Тихая: текстовая кнопка без заливки и с пометкой — чтобы никто не принял её за обычный путь. */
          <View style={s.testWrap}>
            <Text style={s.testBtn} onPress={() => testCall(false)} accessibilityRole="button">
              {testBusy ? '…' : V.test()}
            </Text>
            <Text style={s.testNote}>{V.testNote()}</Text>
          </View>
        ) : null}
      </GlassSurface>
    </View>
  );
}

const V = {
  title: () => T('Пройди проверку', 'Get verified', 'Verifícate'),
  sub: () => T('Пара минут — и рядом с именем галочка', 'A couple of minutes — and a check next to your name', 'Un par de minutos y una marca junto a tu nombre'),
  p1: () => T('Галочка «проверен» в профиле', 'A “verified” check on your profile', 'Marca de «verificado» en tu perfil'),
  p2: () => T('Больше доверия — на приглашения отвечают охотнее', 'More trust — people answer invites more readily', 'Más confianza: responden antes a tus invitaciones'),
  p3: () => T('Доступ к свиданиям 18+', 'Access to 18+ dating', 'Acceso a citas 18+'),
  start: () => T('Начать проверку', 'Start verification', 'Empezar verificación'),
  note: () => T('Проверку проводит Didit: селфи и документ. Результат подтверждает только сервер Kleal.',
    'Verification is done by Didit: a selfie and an ID. Only the Kleal server confirms the result.',
    'La verificación la hace Didit: un selfi y un documento. Solo el servidor de Kleal confirma el resultado.'),
  done: () => T('Ты проверен — галочка уже в профиле', 'You’re verified — the check is on your profile', 'Estás verificado: la marca ya está en tu perfil'),
  test: () => T('Пройти автоматически (для тестов)', 'Pass automatically (for testing)', 'Pasar automáticamente (pruebas)'),
  testNote: () => T('только для тестировщиков', 'testers only', 'solo para testers'),
  doneTest: () => T('Проверен (тест)', 'Verified (test)', 'Verificado (prueba)'),
  undo: () => T('Снять', 'Undo', 'Deshacer'),
  saveFirst: () => T('Сначала нужно сохранить анкету — проверь сообщение выше и попробуй ещё раз.', 'Your profile needs to be saved first — check the message above and try again.', 'Primero hay que guardar tu perfil: revisa el mensaje de arriba e inténtalo de nuevo.'),
  later: () => T('Сейчас не получилось начать — попробуй чуть позже.', 'Couldn’t start right now — try again a bit later.', 'No se pudo empezar ahora: inténtalo un poco más tarde.'),
};

// ===== вид
const s = StyleSheet.create({
  shadow: { shadowColor: '#0A0A14', shadowOpacity: 0.06, shadowRadius: 16, shadowOffset: { width: 0, height: 6 } },
  card: { padding: 16, gap: 12 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  badge: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,56,92,0.10)' },
  title: { fontFamily: font.displaySemi, fontSize: 17, lineHeight: 22, color: color.fg } as any,
  sub: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: '#5A616E' } as any,
  points: { gap: 8 },
  point: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: color.primary },
  pointText: { flex: 1, fontFamily: font.text, fontSize: 14, lineHeight: 20, color: color.fg } as any,
  cta: { height: 44, marginTop: space.xs },
  note: { fontFamily: font.text, fontSize: 11, lineHeight: 15, color: '#5A616E', textAlign: 'center' } as any,
  err: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.primary } as any,
  doneRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 12, paddingHorizontal: 14 },
  testWrap: { alignItems: 'center', gap: 2, paddingTop: 4 },
  testBtn: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: '#5A616E', textDecorationLine: 'underline' } as any,
  testNote: { fontFamily: font.text, fontSize: 10, lineHeight: 14, color: '#8A909B' } as any,
  undo: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: color.primary } as any,
  doneText: { flex: 1, fontFamily: font.textMedium, fontSize: 14, lineHeight: 20, color: color.fg } as any,
});
