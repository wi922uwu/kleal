/**
 * Разговор с Бадди — кадры O.02 и O.03.
 *
 * UX-КАРКАС: вид натянется поверх. Оформление держится на токенах темы и вынесено вниз файла одним
 * блоком; вся копия — в src/buddy.ts. Менять внешность можно, не притрагиваясь к логике.
 *
 * Бадди тут просто собеседник. Написанное ему НЕ становится интентом само собой: сервер только
 * сообщает, что распознал в сказанном план, и тогда появляется окно выбора — создавать или
 * продолжать разговор. Та же кнопка «Создать» в шапке открывает то же окно.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput,
  KeyboardAvoidingView, Platform, Modal,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { IconChevronLeft, IconSend } from '../src/components/icons';
import { useLang, getLang, T } from '../src/i18n';
import { useOnb } from '../src/state';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { buddy as buddyApi, VoicePayload } from '../src/api';
import { BUDDY, SHEET, looksLikeIntent, intentPhrase, sheetWhat, sheetKept, packHistory, Turn } from '../src/buddy';
import { Sheet } from '../src/components/Sheet';
import { color, radius as rad, space, type } from '../src/theme';
import { useVoiceMessage, VoiceBubble, VoiceMessageControl } from '../src/voice';
import Markdown from '../src/components/Markdown';
import { Thinking } from '../src/components/Thinking';
import { makeReveal } from '../src/reveal';

/**
 * `hello` — первая реплика экрана. Это не ответ модели, а обращение к человеку, и выглядеть оно
 * должно как заголовок страницы, а не как первая строчка переписки: с него разговор начинается.
 * Признак хранится ОТДЕЛЬНО, а не «# » в тексте: тот же текст уходит модели в историю, и решётка
 * попала бы к ней в контекст.
 */
type Msg = { who: 'bot' | 'me'; text: string; at: string; voice?: VoicePayload; hello?: boolean;
  /** Текст ещё пишется — под ним мигает курсор. */ live?: boolean };

const now = () =>
  new Date().toLocaleTimeString(getLang() === 'ru' ? 'ru-RU' : 'en-US', {
    hour: '2-digit', minute: '2-digit', hour12: getLang() !== 'ru',
  });

export default function Buddy() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх дока — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const scroller = useRef<ScrollView>(null);

  /** Текст с главного экрана: человек уже сказал, что хочет, — повторять вопрос незачем. */
  const seed = String(useLocalSearchParams<{ q?: string }>().q || '').trim();

  const [thread, setThread] = useState<Msg[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [typing, setTyping] = useState(false);
  const [sheet, setSheet] = useState(false);
  /** Что распознал Kleal — заголовок для окна и для реплики «а я думал…». */
  const [what, setWhat] = useState('');
  /** Тема, с которой откроется создание интента, если человек его выберет. */
  const [topic, setTopic] = useState('');
  const started = useRef(false);

  const say = useCallback((who: 'bot' | 'me', text: string, hello = false) => {
    setThread((t) => [...t, { who, text, at: now(), hello }]);
  }, []);

  useEffect(() => {
    const id = setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [thread.length, typing]);

  const profile = () => ({
    name: st.profile.name, age: st.profile.age, city: st.profile.city,
    interests: st.profile.interests?.explicit || [],
    languages: st.profile.languages || {},
  });

  /**
   * Что сделать с готовым ответом. Развилка та же, что была до потока, — вынесена отдельно,
   * потому что теперь она срабатывает в `done`, а не сразу после запроса.
   *
   * `shown` — показался ли текст потоком. От него зависит и то, печатать ли реплику (уже
   * напечатана), и то, надо ли её УБРАТЬ, если ответ оказался планом.
   */
  const finish = useCallback((r: any, reply: string, text: string, next: Turn[], shown: boolean) => {
    if (looksLikeIntent(r)) {
      /**
       * Распознан план — на экране реплики быть не должно, вместо неё окно выбора. Раньше человек
       * получал и ответ агента, и окно поверх него: разговор продолжался и одновременно
       * прерывался, и было непонятно, на что отвечать. С потоком добавилось второе: текст уже
       * успел появиться, поэтому его надо снять, а не просто не печатать.
       *
       * В историю ответ всё же кладём: он был, модель на него опирается, и после «продолжим
       * общаться» разговор не должен начинаться с пустоты.
       */
      if (shown) setThread((prev) => prev.slice(0, -1));
      // Фраза, а не подпись карточки: «поговорить про Jesus», см. intentPhrase.
      const label = intentPhrase(r, text);
      setTurns(reply ? [...next, { role: 'assistant', content: reply }] : next);
      setTopic(text);
      setWhat(label);
      setSheet(true);
      return;
    }
    if (reply) {
      if (!shown) say('bot', reply);       // потоком не приходило — печатаем целиком
      setTurns([...next, { role: 'assistant', content: reply }]);
    }
  }, [say]);

  /**
   * ОТВЕТ ПОЯВЛЯЕТСЯ ПО МЕРЕ НАПИСАНИЯ.
   *
   * Измерено на живом сервере: модель начинает писать через 0,24 с, а весь ответ выходит за 15
   * секунд — токен за токеном. Ускорить генерацию нельзя; можно перестать ждать её конца. Первые
   * слова теперь на экране через ~1,9 с вместо 7,5 — это разница между «приложение думает» и
   * «приложение отвечает».
   *
   * Текст растёт ПРЯМО В ЛЕНТЕ, а не в отдельном состоянии: иначе пришлось бы держать две копии
   * и склеивать их в конце, а расхождение между ними человек увидел бы как мигание.
   */
  const send = useCallback((text: string, hist: Turn[]) => new Promise<void>((resolve) => {
    const next: Turn[] = [...hist, { role: 'user', content: text }];
    setTurns(next);
    setTyping(true);

    let acc = '';
    let opened = false;

    /**
     * Показ развязан с приходом: буквы приезжают рывками (201 кусок на 656 символов, между ними
     * то 10 мс, то 400), а на экран выдаются ровным темпом. См. src/reveal.ts — там же объяснено,
     * почему хвост с незакрытой разметкой придерживается.
     */
    const show = (shown: string) => {
      setTyping(false);
      setThread((prev) => {
        if (!opened) { opened = true; return [...prev, { who: 'bot', text: shown, at: now(), live: true }]; }
        const out = prev.slice();
        out[out.length - 1] = { ...out[out.length - 1], text: shown, live: true };
        return out;
      });
    };
    const rev = makeReveal(show);
    const grow = (t: string) => { acc += t; rev.push(t); };

    buddyApi.chatStream(next, profile(), {
      delta: grow,
      error: async () => {
        /**
         * ПОТОК ОБОРВАЛСЯ — ЭТО НЕ ПОВОД ТЕРЯТЬ ОТВЕТ.
         *
         * Поток — способ доставки, а не сам ответ. Сообщено с телефона: «Связь пропала.
         * Повторишь?» приходило на каждое сообщение подряд, хотя сервер отвечал исправно —
         * рвался именно поток, и вместе с ним выбрасывался готовый ответ. Человек видел
         * приложение, которое перестало работать.
         *
         * Поэтому здесь не извинение, а ВТОРАЯ ПОПЫТКА обычным запросом. Извиняемся только если
         * и она не прошла: тогда связи действительно нет.
         */
        if (opened) { rev.stop(); setTyping(false); resolve(); return; }   // половина уже на экране
        try {
          const r: any = await buddyApi.chat(next, profile());
          setTyping(false);
          const reply = String(r?.reply || '');
          if (reply) finish(r, reply, text, next, false);
          else say('bot', BUDDY.offline());
        } catch {
          setTyping(false);
          say('bot', BUDDY.offline());
        }
        resolve();
      },
      done: (r: any) => {
        setTyping(false);
        rev.finish();
        const reply = String(r?.reply || acc);
        // Итог разошёлся с показанным (вторая попытка, обрезка по границе, заготовка при отказе)
        // — переписываем. Иначе над настоящим ответом висела бы оборванная половина.
        if (opened) {
          // Дописываем итог и гасим курсор. Ждать, пока машинка домотает сама, нельзя: она
          // допечатывает уже принятый текст, а `done` может нести ДРУГОЙ (вторая попытка,
          // обрезка по границе) — тогда курсор мигал бы под старым текстом.
          rev.stop();
          setThread((prev) => {
            const out = prev.slice();
            const cur = out[out.length - 1];
            out[out.length - 1] = { ...cur, text: r?.replaced ? reply : cur.text, live: false };
            return out;
          });
        }
        finish(r, reply, text, next, opened);
        resolve();
      },
    });
  }), [say, finish, st.profile]);

  /** Голосовое ложится в ленту своим пузырём, а модели уходит расшифровка — ей слушать нечем. */
  const deliverVoice = useCallback(async (payload: VoicePayload) => {
    setThread((t) => [...t, { who: 'me', text: payload.transcript, voice: payload, at: now() }]);
    await send(payload.transcript, turns);
  }, [send, turns]);
  const voice = useVoiceMessage(deliverVoice, typing);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (seed) {
      say('me', seed);
      send(seed, []);
      return;
    }
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      const hello = BUDDY.hello(st.profile.name || '');
      say('bot', hello, true);
      /**
       * Приветствие идёт и В ИСТОРИЮ, а не только на экран.
       *
       * `say()` рисует пузырь, `turns` — то, что видит модель. Пока приветствие жило только в
       * первом, модель получала первую реплику человека как самую первую в разговоре, сервер
       * помечал её «[FIRST MESSAGE] … greet them as a new acquaintance», и модель здоровалась
       * ВТОРОЙ раз: «Привет, Иван. О чём поговорим?» — «привет» — «Привет, Иван! …».
       *
       * Она и не могла поступить иначе: поздороваться было нечем — в её истории приветствия не
       * было. Кладём его туда, и правило промпта «do NOT greet again» наконец применимо.
       */
      setTurns((t) => (t.length ? t : [{ role: 'assistant', content: hello }]));
    }, 450);
  }, []);

  const submit = () => {
    const t = draft.trim();
    if (!t || typing) return;
    setDraft('');
    say('me', t);
    send(t, turns);
  };

  /**
   * В создание уезжает не только последняя фраза, но и весь разговор до неё. «Поговорить с кем-то
   * ОБ ЭТОМ» без истории не значит ничего — построитель переспрашивал «о чём?», хотя человек
   * рассказывал ему это минуту назад.
   */
  /**
   * «Продолжим общаться»: окно закрывается, и Kleal вслух называет, что он понял. Молчаливое
   * закрытие оставляло человека с догадкой — распознал агент что-то или нет.
   */
  const keepChatting = () => {
    setSheet(false);
    if (!what) return;
    const line = sheetKept(what);
    say('bot', line);
    setTurns((t) => [...t, { role: 'assistant', content: line }]);
  };

  const toCreate = () => {
    setSheet(false);
    const params: Record<string, string> = {};
    if (topic) params.seed = topic;
    // Затравка уже лежит последней в turns — в историю для сервера она попадёт оттуда, поэтому
    // здесь отрезаем её, чтобы не уехала дважды.
    const hist = topic ? turns.filter((t) => t.content !== topic) : turns;
    const packed = packHistory(hist);
    if (packed) params.history = packed;
    router.navigate({ pathname: '/create', params });
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" style={s.back} onPress={() => (router.canGoBack() ? router.back() : router.replace('/home'))}>
            <IconChevronLeft />
          </Pressable>
          <View style={{ flex: 1 }} />
          <Pressable
            accessibilityRole="button"
            style={s.createBtn}
            onPress={() => { setTopic(''); setSheet(true); }}
          >
            <Text style={s.createPlus}>+</Text>
            <Text style={s.createText}>{BUDDY.create()}</Text>
          </Pressable>
        </View>

        <ScrollView ref={scroller} contentContainerStyle={s.thread} keyboardShouldPersistTaps="handled">
          {/*
            РЕПЛИКА И ОТВЕТ ВЫГЛЯДЯТ ПО-РАЗНОМУ, и это не украшение.

            Человек говорит — его слова остаются пузырём справа. Модель пишет — её ответ идёт
            страницей во всю ширину, без подложки и без рамки. Пока оба были пузырями, экран
            сообщал, что разбор на восемь абзацев — такая же проходная реплика, как «ок», и
            читался он так же бегло. Плюс разметка внутри пузыря схлопывалась в кашу из звёздочек
            и решёток: она не просто не рисовалась, она МЕШАЛА.
          */}
          {thread.map((m, i) => {
            const mine = m.who === 'me';
            if (m.voice) {
              return (
                <View key={i} style={{ alignItems: mine ? 'flex-end' : 'flex-start' }}>
                  <VoiceBubble voice={m.voice} mine={mine} />
                  <Text style={s.time}>{m.at}</Text>
                </View>
              );
            }
            if (mine) {
              return (
                <View key={i} style={{ alignItems: 'flex-end' }}>
                  <View style={[s.bub, s.bubMe]}>
                    <Text style={[s.bubText, { color: color.onPrimary }]}>{m.text}</Text>
                  </View>
                  <Text style={s.time}>{m.at}</Text>
                </View>
              );
            }
            if (m.hello) {
              return (
                <View key={i} style={s.answer}>
                  <Text style={s.hello}>{m.text}</Text>
                  <Text style={[s.time, s.timeAnswer]}>{m.at}</Text>
                </View>
              );
            }
            return (
              <View key={i} style={s.answer}>
                <Markdown text={m.text} />
                {/* Время под ответом приглушено сильнее, чем под репликой: у страницы оно
                    служебная пометка, а не часть разговора. */}
                <Text style={[s.time, s.timeAnswer]}>{m.at}</Text>
              </View>
            );
          })}
          {/* Ожидание — не вертушка, а живая строка: см. src/components/Thinking.tsx. */}
          {typing ? <Thinking /> : null}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: dockBottom(insets.bottom, kb) }]}>
          <View style={s.field}>
            {/*
              Во время записи поля нет — полоса записи занимает его место. Именно `null`, а не
              перестроенная разметка: соседняя кнопка обязана остаться на СВОЁМ месте в дереве,
              иначе React пересоберёт её ровно в миг старта записи и жест удержания оборвётся.
            */}
            {voice.phase === 'idle' ? (
              <TextInput
                style={s.input}
                value={draft}
                onChangeText={setDraft}
                placeholder={BUDDY.placeholder()}
                placeholderTextColor={color.neutral400}
                onSubmitEditing={submit}
                returnKeyType="send"
              />
            ) : null}
            {voice.phase === 'idle' && draft.trim() ? (
              <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send')} onPress={submit} hitSlop={8}>
                <IconSend size={18} c={color.primary} />
              </Pressable>
            ) : (
              <VoiceMessageControl voice={voice} />
            )}
          </View>
        </View>

        <GetStarted
          open={sheet}
          what={what}
          onCreate={toCreate}
          onKeep={keepChatting}
          bottomInset={insets.bottom}
        />
      </View>
    </KeyboardAvoidingView>
  );
}

/**
 * Окно O.03. Одно на оба входа — и на кнопку, и на распознанный триггер, — потому что вопрос в
 * обоих случаях один и тот же: создавать интент или продолжать разговор.
 */
export function GetStarted({
  open, what, onCreate, onKeep, bottomInset = 0,
}: {
  open: boolean;
  /** Что именно распознал Kleal. Человек соглашается на конкретную затею, а не на «интент». */
  what?: string;
  onCreate: () => void;
  onKeep: () => void;
  bottomInset?: number;
}) {
  return (
    <Sheet visible={open} onClose={onKeep} title={SHEET.title()} bottomInset={Math.max(bottomInset, 18)} grip>
        {what ? <Text style={sh.what}>{sheetWhat(what)}</Text> : null}
        <Pressable accessibilityRole="button" style={[sh.btn, sh.btnPri]} onPress={onCreate}>
          <Text style={sh.btnPriText}>{SHEET.create()}</Text>
        </Pressable>
        <Pressable accessibilityRole="button" style={[sh.btn, sh.btnSec]} onPress={onKeep}>
          <Text style={sh.btnSecText}>{SHEET.keep()}</Text>
        </Pressable>
    </Sheet>
  );
}

// ============================================================ вид
// Всё ниже — оформление UX-каркаса: цвета и размеры берутся из токенов темы, своих значений тут
// нет. При натягивании UI меняется этот блок, логика выше остаётся.

const s = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingBottom: space.sm },
  wrap: { flex: 1, backgroundColor: color.bg },
  back: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  createBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6, height: 40, paddingHorizontal: 16,
    borderRadius: rad.full, backgroundColor: color.card, borderWidth: 1, borderColor: color.border,
  },
  createPlus: { fontSize: 18, color: color.fg, marginTop: -2 },
  createText: { ...type.labelMedium, color: color.fg } as any,

  thread: { paddingHorizontal: 20, paddingTop: space.md, paddingBottom: space.lg, gap: 4 },
  bub: { maxWidth: '86%', paddingVertical: 12, paddingHorizontal: 14, marginTop: space.sm },
  bubBot: { alignSelf: 'flex-start', backgroundColor: color.neutral100, borderRadius: 16 },
  bubMe: { alignSelf: 'flex-end', backgroundColor: color.primary, borderRadius: 16 },
  bubText: { ...type.body, color: color.fg } as any,
  /**
   * Ответ модели. Ни подложки, ни рамки, ни ограничения ширины: это страница, а не реплика.
   * Верхняя отбивка больше нижней — ответ отделяется от предыдущего вопроса сильнее, чем от
   * собственной пометки времени.
   */
  answer: { alignSelf: 'stretch', marginTop: space.lg, marginBottom: space.xs },
  timeAnswer: { color: color.neutral300, marginTop: space.xs } as any,
  /** Приветствие — ступень заголовка документа: разговор им ОТКРЫВАЕТСЯ, а не продолжается. */
  hello: { ...type.mdH1, color: color.fg } as any,
  time: { ...type.caption, color: color.neutral400, marginTop: 3 } as any,

  dock: { paddingHorizontal: 16, paddingTop: space.sm, backgroundColor: color.bg },
  field: {
    height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  input: { flex: 1, color: color.fg, fontSize: 15 },
});

const sh = StyleSheet.create({
  /** Строка «Похоже, ты хочешь …» — под заголовком окна, перед кнопками. */
  what: { ...type.bodySmall, color: color.muted, marginBottom: 4 } as any,
  btn: { height: 54, borderRadius: rad.full, alignItems: 'center', justifyContent: 'center' },
  btnPri: { backgroundColor: color.primary },
  btnPriText: { ...type.button, color: color.onPrimary } as any,
  btnSec: { backgroundColor: color.neutral100 },
  btnSecText: { ...type.button, color: color.fg } as any,
});
