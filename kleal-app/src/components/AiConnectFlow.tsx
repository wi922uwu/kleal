/**
 * ПОДКЛЮЧЕНИЕ ChatGPT — три шага и одна главная кнопка (18.10.2026, Иван: «там скопировать, там
 * скопировать, там скопировать… надо обыграть профессионально — красиво, легко и понятно»).
 *
 *   1. Подключи Kleal в ChatGPT — главная кнопка копирует личную ссылку коннектора. Как добавить
 *      коннектор (режим разработчика, chatgpt.com на компьютере) — под раскрытием, не на виду.
 *   2. Напиши в ChatGPT — фраза копируется касанием по самому блоку или главной кнопкой.
 *   3. Жди черновик — экран сам узнаёт, что он пришёл; что делать, если не приходит, — тут же.
 *
 * Главная кнопка внизу одна и меняется по шагу: «Скопировать ссылку» → «Скопировать фразу» →
 * «Ждём ChatGPT…» → «Посмотреть черновик». Пройденные шаги отмечены, текущий выделен. Вставить ответ
 * вручную — запасной путь мелкой ссылкой. Движения нет, кроме отклика на нажатие.
 */
import { useEffect, useRef, useState } from 'react';
import { Pressable, Share, StyleSheet, Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { T } from '../i18n';
import { hOk, hTap } from '../haptics';
import { GlassSurface } from './LiquidGlass';
import { GlassPill } from './Glass';
import { ChatGPTMark } from './ChatGPTMark';
import { IconCheck, IconChevronDown } from './icons';
import { color, font, space } from '../theme';

export function AiConnectFlow({ url, prompt, expired, arrived, onReview, onNewLink, onPaste }: {
  url: string; prompt: string; expired: boolean; arrived: boolean;
  onReview: () => void; onNewLink: () => void; onPaste: () => void;
}) {
  const [linkDone, setLinkDone] = useState(false);
  const [phraseDone, setPhraseDone] = useState(false);
  const [howOpen, setHowOpen] = useState(false);
  const [flash, setFlash] = useState<'link' | 'phrase' | null>(null);
  const t = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (t.current) clearTimeout(t.current); }, []);

  const copy = async (what: 'link' | 'phrase') => {
    try { await Clipboard.setStringAsync(what === 'link' ? url : prompt); } catch { return; }
    hOk();
    if (what === 'link') setLinkDone(true); else setPhraseDone(true);
    setFlash(what);
    if (t.current) clearTimeout(t.current);
    t.current = setTimeout(() => setFlash(null), 1800);
  };

  // Текущий шаг: 1 — ссылка, 2 — фраза, 3 — ждём. Пришёл черновик — все пройдены.
  const step = arrived ? 4 : !linkDone ? 1 : !phraseDone ? 2 : 3;

  const cta = arrived ? { label: F.review(), on: onReview, tone: 'brand' as const }
    : expired ? { label: F.newLink(), on: onNewLink, tone: 'brand' as const }
    : step === 1 ? { label: flash === 'link' ? F.copied() : F.copyLink(), on: () => copy('link'), tone: 'brand' as const }
    : step === 2 ? { label: flash === 'phrase' ? F.copied() : F.copyPhrase(), on: () => copy('phrase'), tone: 'brand' as const }
    : { label: F.waiting(), on: undefined, tone: 'light' as const };

  return (
    <View style={s.wrap}>
      <View style={s.hero}>
        <View style={s.heroMark}><ChatGPTMark size={28} /></View>
        <Text style={s.heroTitle}>{F.title()}</Text>
        <Text style={s.heroSub}>{F.sub()}</Text>
      </View>

      <GlassSurface tone="light" radius={20} style={s.card}>
        <Step n={1} state={step > 1 ? 'done' : 'now'} title={F.s1()}
              sub={expired ? F.expired() : linkDone ? F.s1done() : F.s1sub()}>
          <Pressable onPress={() => { hTap(); setHowOpen((v) => !v); }} style={s.howRow} hitSlop={6}>
            <Text style={s.how}>{F.how()}</Text>
            <View style={howOpen ? { transform: [{ rotate: '180deg' }] } : undefined}><IconChevronDown size={16} c={color.primary} /></View>
          </Pressable>
          {howOpen ? (
            <View style={s.howBox}>
              {[F.h1(), F.h2(), F.h3(), F.h4()].map((h, i) => (
                <Text key={i} style={s.howText}>{`${i + 1}. ${h}`}</Text>
              ))}
              <Text style={s.howNote}>{F.hNote()}</Text>
              <Text style={s.share} onPress={() => Share.share({ message: url }).catch(() => {})}>{F.share()}</Text>
            </View>
          ) : null}
        </Step>

        <Step n={2} state={step > 2 ? 'done' : step === 2 ? 'now' : 'next'} title={F.s2()} sub={F.s2sub()}>
          <Pressable onPress={() => copy('phrase')} accessibilityRole="button" accessibilityLabel={F.copyPhrase()}
                     style={({ pressed }) => [s.phrase, pressed && { opacity: 0.85 }]}>
            <Text style={s.phraseText}>«{prompt}»</Text>
            <Text style={s.phraseHint}>{flash === 'phrase' ? F.copied() : F.tapToCopy()}</Text>
          </Pressable>
        </Step>

        <Step n={3} state={arrived ? 'done' : step === 3 ? 'now' : 'next'} title={F.s3()}
              sub={arrived ? F.s3done() : step === 3 ? F.s3wait() : F.s3sub()} last />
      </GlassSurface>

      <GlassPill tone={cta.tone} label={cta.label} disabled={!cta.on} onPress={cta.on} style={s.cta} />
      <Text style={s.paste} onPress={onPaste}>{F.paste()}</Text>
    </View>
  );
}

function Step({ n, state, title, sub, children, last }: {
  n: number; state: 'done' | 'now' | 'next'; title: string; sub: string; children?: React.ReactNode; last?: boolean;
}) {
  return (
    <View style={s.step}>
      <View style={s.rail}>
        <View style={[s.dot, state === 'now' && s.dotNow, state === 'done' && s.dotDone]}>
          {state === 'done' ? <IconCheck size={14} c="#FFFFFF" /> : <Text style={[s.dotText, state === 'now' && s.dotTextNow]}>{n}</Text>}
        </View>
        {!last ? <View style={[s.line, state === 'done' && s.lineDone]} /> : null}
      </View>
      <View style={[s.stepBody, !last && { paddingBottom: space.lg }]}>
        <Text style={[s.stepTitle, state === 'next' && s.dim]}>{title}</Text>
        <Text style={[s.stepSub, state === 'next' && s.dim]}>{sub}</Text>
        {state !== 'next' ? children : null}
      </View>
    </View>
  );
}

const F = {
  title: () => T('Заполни профиль через ChatGPT', 'Fill your profile with ChatGPT', 'Rellena tu perfil con ChatGPT'),
  sub: () => T('Три шага, пара минут. Всё, что он пришлёт, ты проверишь перед сохранением.',
    'Three steps, a couple of minutes. You review everything it sends before saving.',
    'Tres pasos, un par de minutos. Revisas todo lo que envíe antes de guardar.'),
  s1: () => T('Подключи Kleal в ChatGPT', 'Connect Kleal in ChatGPT', 'Conecta Kleal en ChatGPT'),
  s1sub: () => T('Скопируй личную ссылку и добавь её как коннектор.', 'Copy your personal link and add it as a connector.', 'Copia tu enlace personal y añádelo como conector.'),
  s1done: () => T('Ссылка скопирована — добавь её в ChatGPT как коннектор.', 'Link copied — add it in ChatGPT as a connector.', 'Enlace copiado: añádelo en ChatGPT como conector.'),
  expired: () => T('Ссылка истекла — сделаем новую.', 'The link expired — let’s make a new one.', 'El enlace caducó: hagamos uno nuevo.'),
  how: () => T('Как добавить коннектор', 'How to add a connector', 'Cómo añadir un conector'),
  h1: () => T('Открой chatgpt.com на компьютере (нужен Plus или Pro).', 'Open chatgpt.com on a computer (Plus or Pro).', 'Abre chatgpt.com en el ordenador (Plus o Pro).'),
  h2: () => T('Настройки → Apps & Connectors → Advanced → включи Developer mode.', 'Settings → Apps & Connectors → Advanced → turn on Developer mode.', 'Ajustes → Apps & Connectors → Advanced → activa Developer mode.'),
  h3: () => T('Create → имя «Kleal», вставь ссылку, авторизация — No authentication.', 'Create → name “Kleal”, paste the link, authentication — No authentication.', 'Create → nombre «Kleal», pega el enlace, autenticación — No authentication.'),
  h4: () => T('В новом чате нажми «+» и выбери Kleal.', 'In a new chat tap “+” and pick Kleal.', 'En un chat nuevo pulsa «+» y elige Kleal.'),
  hNote: () => T('Ссылка личная и действует 24 часа — не пересылай её другим.', 'The link is personal and valid for 24 hours — don’t share it.', 'El enlace es personal y vale 24 horas: no lo compartas.'),
  share: () => T('Отправить ссылку себе на компьютер', 'Send the link to my computer', 'Enviarme el enlace al ordenador'),
  s2: () => T('Напиши в ChatGPT', 'Message ChatGPT', 'Escribe a ChatGPT'),
  s2sub: () => T('С выбранным Kleal отправь эту фразу:', 'With Kleal selected, send this phrase:', 'Con Kleal elegido, envía esta frase:'),
  tapToCopy: () => T('Нажми, чтобы скопировать', 'Tap to copy', 'Toca para copiar'),
  s3: () => T('Получи черновик', 'Get your draft', 'Recibe tu borrador'),
  s3sub: () => T('Он появится здесь сам.', 'It shows up here on its own.', 'Aparecerá aquí solo.'),
  s3wait: () => T('Ждём ChatGPT… Не приходит? Проверь, что в чате выбран Kleal в меню «+».', 'Waiting for ChatGPT… Nothing yet? Check Kleal is selected in the “+” menu.', 'Esperando a ChatGPT… ¿No llega? Comprueba que Kleal está elegido en el menú «+».'),
  s3done: () => T('Черновик пришёл — посмотри и оставь то, что про тебя.', 'Your draft is here — keep what’s you.', 'Ha llegado tu borrador: quédate con lo tuyo.'),
  copyLink: () => T('Скопировать ссылку', 'Copy link', 'Copiar enlace'),
  copyPhrase: () => T('Скопировать фразу', 'Copy phrase', 'Copiar frase'),
  copied: () => T('Скопировано ✓', 'Copied ✓', 'Copiado ✓'),
  waiting: () => T('Ждём ChatGPT…', 'Waiting for ChatGPT…', 'Esperando a ChatGPT…'),
  review: () => T('Посмотреть черновик', 'Review draft', 'Ver borrador'),
  newLink: () => T('Новая ссылка', 'New link', 'Nuevo enlace'),
  paste: () => T('Нет компьютера? Вставь ответ ChatGPT вручную', 'No computer? Paste ChatGPT’s answer instead', '¿Sin ordenador? Pega la respuesta de ChatGPT'),
};

// ===== вид
const s = StyleSheet.create({
  wrap: { gap: space.md },
  hero: { alignItems: 'center', gap: 8, paddingVertical: 4 },
  heroMark: { width: 52, height: 52, borderRadius: 16, backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center' },
  heroTitle: { fontFamily: font.displaySemi, fontSize: 22, lineHeight: 28, color: color.fg, textAlign: 'center' } as any,
  heroSub: { fontFamily: font.text, fontSize: 14, lineHeight: 20, color: '#5A616E', textAlign: 'center' } as any,
  card: { padding: 16 },
  step: { flexDirection: 'row', gap: 12 },
  rail: { alignItems: 'center', width: 28 },
  dot: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(24,27,34,0.06)' },
  dotNow: { backgroundColor: 'rgba(255,56,92,0.14)' },
  dotDone: { backgroundColor: color.primary },
  dotText: { fontFamily: font.textSemibold, fontSize: 13, color: '#8A909B' } as any,
  dotTextNow: { color: color.primary },
  line: { flex: 1, width: 2, marginVertical: 4, borderRadius: 1, backgroundColor: 'rgba(24,27,34,0.08)' },
  lineDone: { backgroundColor: 'rgba(255,56,92,0.45)' },
  stepBody: { flex: 1, gap: 4 },
  stepTitle: { fontFamily: font.textSemibold, fontSize: 16, lineHeight: 22, color: color.fg } as any,
  stepSub: { fontFamily: font.text, fontSize: 14, lineHeight: 20, color: '#5A616E' } as any,
  dim: { opacity: 0.5 },
  howRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 },
  how: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: color.primary } as any,
  howBox: { gap: 6, marginTop: 8, padding: 12, borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.7)' },
  howText: { fontFamily: font.text, fontSize: 13, lineHeight: 19, color: color.fg } as any,
  howNote: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: '#5A616E', marginTop: 2 } as any,
  share: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: color.primary, marginTop: 4 } as any,
  phrase: { marginTop: 8, padding: 14, borderRadius: 14, backgroundColor: '#FFFFFF', gap: 6, borderWidth: 1, borderColor: 'rgba(255,56,92,0.18)' },
  phraseText: { fontFamily: font.text, fontSize: 15, lineHeight: 21, color: color.fg } as any,
  phraseHint: { fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: color.primary } as any,
  cta: { height: 52 },
  paste: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: '#5A616E', textAlign: 'center', textDecorationLine: 'underline' } as any,
});
