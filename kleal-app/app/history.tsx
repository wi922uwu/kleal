/**
 * История разговоров с Kleal (кнопка-часы в шапке чата с Буди).
 *
 * ПЕРЕДЕЛАНА 18.10.2026 (Иван: «экран устарел и не проработан, функционально не работает — я должен
 * уметь восстановить диалог; по нормам нашего UI/UX»):
 *   • нажатие на разговор ОТКРЫВАЕТ ЕГО В ЧАТЕ С KLEAL и продолжает: та же лента, тот же контекст для
 *     модели, окно затеи там, где было (app/buddy.tsx, параметр resume; хранение — src/history.ts);
 *   • строка — стеклянная карточка: заголовок (затея или первая фраза), дата, превью последней
 *     реплики, признак «затея создана»;
 *   • удаление — кнопкой «…» на строке с подтверждением; «Новый разговор» — сверху;
 *   • пустое состояние; без лишнего движения — как договорились по карте.
 * История живёт на телефоне (оговорка внизу списка); перенос между устройствами — отдельная задача.
 */
import { useCallback, useState } from 'react';
import { Alert, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { HISTORY } from '../src/home';
import { BUDDY } from '../src/buddy';
import { useLang, T, dateLocale, use12h } from '../src/i18n';
import { loadHistory, deleteConversation, type HistoryItem } from '../src/history';
import { color, font, space } from '../src/theme';
import { Ambient, GLOW_FORM } from '../src/components/Ambient';
import { GlassSurface } from '../src/components/LiquidGlass';
import { GlassPill } from '../src/components/Glass';
import { IconChevronLeft, IconDots, IconPlusRound } from '../src/components/icons';
import { LogoFace } from '../src/components/Logo';

export default function History() {
  const lang = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<HistoryItem[] | null>(null);

  // Перечитываем на каждом появлении: разговор мог закончиться минуту назад.
  useFocusEffect(useCallback(() => {
    let alive = true;
    // Только разговоры с Kleal — их можно продолжить. Разговор анкеты сюда не относится. Старые записи
    // Буди без поля source узнаём по заголовку BUDDY.title() («Kleal»).
    loadHistory().then((h) => alive && setItems(h.filter((x) => x.source === 'buddy' || (!x.source && x.topic === BUDDY.title()))));
    return () => { alive = false; };
  }, []));

  /** Открыть разговор в чате с Kleal. История — модальное окно над чатом: закрываем его и подменяем чат. */
  const openConv = (id?: string) => {
    if (router.canGoBack()) router.back();
    setTimeout(() => router.replace(id ? { pathname: '/buddy', params: { resume: id } } : '/buddy'), 60);
  };

  const remove = (it: HistoryItem) =>
    Alert.alert(H.deleteAsk(), titleOf(it), [
      { text: H.cancel(), style: 'cancel' },
      { text: H.delete(), style: 'destructive', onPress: () => {
        deleteConversation(it.id).then(() => setItems((x) => (x || []).filter((y) => y.id !== it.id)));
      } },
    ]);

  const ru = lang === 'ru';
  const when = (ms: number) => {
    const d = new Date(ms), now = new Date();
    const time = d.toLocaleTimeString(dateLocale(ru), { hour: '2-digit', minute: '2-digit', hour12: use12h(ru) });
    if (d.toDateString() === now.toDateString()) return `${H.today()}, ${time}`;
    const y = new Date(now.getTime() - 86400000);
    if (d.toDateString() === y.toDateString()) return `${H.yesterday()}, ${time}`;
    return d.toLocaleDateString(dateLocale(ru, 'en-GB'), { day: 'numeric', month: 'short' }) + `, ${time}`;
  };

  return (
    // На iOS экран — модальный лист: статус-бар уже над ним, своего отступа под него не нужно.
    <View style={[s.wrap, { paddingTop: Platform.OS === 'ios' ? 12 : insets.top + 8 }]}>
      <Ambient glows={GLOW_FORM} />
      <View style={s.head}>
        <Pressable accessibilityRole="button" accessibilityLabel={HISTORY.close()} hitSlop={10}
                   onPress={() => router.back()} style={s.back}>
          <IconChevronLeft size={22} c={color.fg} />
        </Pressable>
        <Text style={s.title} numberOfLines={1}>{HISTORY.title()}</Text>
        <View style={s.spacer} />
      </View>

      <ScrollView contentContainerStyle={[s.body, { paddingBottom: insets.bottom + space.xl }]} showsVerticalScrollIndicator={false}>
        <GlassPill tone="brand" label={H.newChat()} icon={<IconPlusRound size={18} c="#FFFFFF" />}
                   onPress={() => openConv()} style={s.newBtn} />

        {items && !items.length ? (
          <GlassSurface tone="light" radius={20} style={s.empty}>
            <LogoFace size={44} />
            <Text style={s.emptyTitle}>{HISTORY.empty()}</Text>
            <Text style={s.emptyHint}>{H.emptyHint()}</Text>
          </GlassSurface>
        ) : null}

        {(items || []).map((it) => (
          <Pressable key={it.id} accessibilityRole="button" accessibilityLabel={titleOf(it)} onPress={() => openConv(it.id)}
                     style={({ pressed }) => [pressed && s.pressed]}>
            <GlassSurface tone="light" radius={18} style={s.row}>
              <View style={s.rowTop}>
                <Text style={s.rowTitle} numberOfLines={1}>{titleOf(it)}</Text>
                <Pressable accessibilityRole="button" accessibilityLabel={H.delete()} hitSlop={10} onPress={() => remove(it)} style={s.dots}>
                  <IconDots size={18} c={color.muted} />
                </Pressable>
              </View>
              <Text style={s.preview} numberOfLines={2}>{previewOf(it)}</Text>
              <View style={s.rowBottom}>
                <Text style={s.meta}>{when(it.updatedAt || it.startedAt)} · {HISTORY.lines(it.lines.length)}</Text>
                {it.created ? <View style={s.badge}><Text style={s.badgeText}>{H.created()}</Text></View> : null}
              </View>
            </GlassSurface>
          </Pressable>
        ))}

        {items && items.length ? <Text style={s.local}>{HISTORY.local()}</Text> : null}
      </ScrollView>
    </View>
  );
}

/** Заголовок разговора: затея, если Kleal её распознал; иначе первая фраза человека. */
function titleOf(it: HistoryItem): string {
  const t = it.intent?.seen?.title?.trim();
  if (t) return t;
  const first = it.lines.find((l) => l.who === 'me')?.text?.trim();
  return first ? first : it.topic;
}

/** Превью — последняя реплика, кто её сказал. */
function previewOf(it: HistoryItem): string {
  const last = [...it.lines].reverse().find((l) => !l.hello) || it.lines[it.lines.length - 1];
  if (!last) return '';
  return `${last.who === 'me' ? H.you() : 'Kleal'}: ${last.text.replace(/\s+/g, ' ').trim()}`;
}

const H = {
  newChat: () => T('Новый разговор', 'New conversation', 'Nueva conversación'),
  emptyHint: () => T('Здесь будут твои разговоры с Kleal — любой можно открыть и продолжить с того же места.',
    'Your conversations with Kleal will show up here — open any of them to pick up where you left off.',
    'Aquí aparecerán tus conversaciones con Kleal: abre cualquiera para seguir donde lo dejaste.'),
  today: () => T('Сегодня', 'Today', 'Hoy'),
  yesterday: () => T('Вчера', 'Yesterday', 'Ayer'),
  you: () => T('Ты', 'You', 'Tú'),
  created: () => T('Затея создана', 'Intent created', 'Plan creado'),
  delete: () => T('Удалить', 'Delete', 'Eliminar'),
  cancel: () => T('Отмена', 'Cancel', 'Cancelar'),
  deleteAsk: () => T('Удалить этот разговор?', 'Delete this conversation?', '¿Eliminar esta conversación?'),
};

// ===== вид
const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: 8, gap: 8 },
  back: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.85)' },
  spacer: { width: 44, height: 44 },
  title: { flex: 1, textAlign: 'center', fontFamily: font.displaySemi, fontSize: 17, lineHeight: 22, color: color.fg } as any,
  body: { paddingHorizontal: 16, paddingTop: 8, gap: 10 },
  newBtn: { height: 48, marginBottom: 6 },
  pressed: { transform: [{ scale: 0.98 }] },
  row: { padding: 14, gap: 6 },
  rowTop: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  rowTitle: { flex: 1, fontFamily: font.textSemibold, fontSize: 16, lineHeight: 22, color: color.fg } as any,
  dots: { width: 28, height: 28, alignItems: 'center', justifyContent: 'center' },
  preview: { fontFamily: font.text, fontSize: 14, lineHeight: 20, color: '#5A616E' } as any,
  rowBottom: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginTop: 2 },
  meta: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: color.muted } as any,
  badge: { paddingHorizontal: 10, height: 24, borderRadius: 12, justifyContent: 'center', backgroundColor: 'rgba(255,56,92,0.10)' },
  badgeText: { fontFamily: font.textMedium, fontSize: 12, lineHeight: 16, color: color.primary } as any,
  empty: { padding: 24, alignItems: 'center', gap: 10, marginTop: 8 },
  emptyTitle: { fontFamily: font.displaySemi, fontSize: 17, lineHeight: 22, color: color.fg, textAlign: 'center' } as any,
  emptyHint: { fontFamily: font.text, fontSize: 14, lineHeight: 20, color: '#5A616E', textAlign: 'center' } as any,
  local: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: color.muted, textAlign: 'center', marginTop: 8 } as any,
});
