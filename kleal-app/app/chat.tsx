/**
 * Онбординг — кадры A.04–A.13.
 *
 * Устройство экрана взято с борда и отличается от того, как это было сделано в вебе:
 *
 *  — Шапка «Creating Profile» с процентом справа и тонкой полосой прогресса под ней.
 *  — Реплики — пузыри со временем; свои справа красным, агента слева серым.
 *  — Виджеты (чипы, кольцо возраста, карта) живут ВНУТРИ ленты, под репликой агента, а не в
 *    отдельном доке снизу. Лента прокручивается вместе с ними.
 *  — Внизу композер «Message…» с микрофоном. Это не украшение: на любом шаге можно ответить
 *    словами вместо нажатия, текст уходит в /api/onboarding/chat, и агент сам разбирает ответ и
 *    правит профиль. Виджет — быстрый путь, разговор — основной.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, TextInput,
  KeyboardAvoidingView, Platform, ActivityIndicator, Image,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import * as ImageManipulator from 'expo-image-manipulator';
import {
  STEP_PROGRESS, HEADER_TITLE, COMPOSER_PLACEHOLDER, STEP_START, STEP_BASICS, SEXES, sexLabel,
  STEP_AREA, STEP_LANGUAGES, LANGS, langLabel, langPlain, STEP_HOBBIES, HOBBIES, hobbyLabel,
  hobbyPlain, STEP_PHOTO, StepId,
} from '../src/onboarding';
import { useLang, T, getLang } from '../src/i18n';
import { useOnb, set, patch } from '../src/state';
import { onboarding } from '../src/api';
import { AgeDial } from '../src/components/AgeDial';
import { AreaPicker, Area } from '../src/components/AreaPicker';
import { color, radius as rad, space, type } from '../src/theme';

type Msg = { who: 'bot' | 'me'; text: string; at: string; photo?: string };

const now = () =>
  new Date().toLocaleTimeString(getLang() === 'ru' ? 'ru-RU' : 'en-US', {
    hour: '2-digit', minute: '2-digit', hour12: getLang() !== 'ru',
  });

const ORDER: StepId[] = ['start', 'basics', 'area', 'languages', 'hobbies', 'photo'];

export default function Chat() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const scroller = useRef<ScrollView>(null);

  const [thread, setThread] = useState<Msg[]>([]);
  const [step, setStep] = useState<StepId>('start');
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState('');
  const [funnel, setFunnel] = useState<{ role: string; content: string }[]>([]);
  const started = useRef(false);

  const say = useCallback((who: 'bot' | 'me', text: string, photo?: string) => {
    setThread((t) => [...t, { who, text, at: now(), photo }]);
  }, []);

  // Первая реплика. Ref, а не состояние: в строгом режиме эффект выполняется дважды, и без
  // защиты приветствие приходит два раза — это видно.
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      say('bot', STEP_START.ask());
    }, 500);
  }, [say]);

  useEffect(() => {
    const id = setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(id);
  }, [thread.length, typing, step]);

  const botAfter = (text: string, ms = 650) => {
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      say('bot', text);
    }, ms);
  };

  const goto = (next: StepId, botLine: string) => {
    setStep(next);
    botAfter(botLine);
  };

  /** Свободный текст — сюда отвечает модель, а не сценарий. */
  const send = async () => {
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    say('me', text);

    // На шаге имени ответ разбирать не нужно: что написали, то и имя.
    if (step === 'start' && !st.profile.name) {
      set('name', text);
      goto('basics', STEP_BASICS.bot());
      return;
    }

    const next = [...funnel, { role: 'user', content: text }];
    setFunnel(next);
    setTyping(true);
    try {
      const r: any = await onboarding.chat({ messages: next, profile: st.profile, lang: getLang() });
      setTyping(false);
      if (r?.reply) {
        say('bot', String(r.reply));
        setFunnel((f) => [...f, { role: 'assistant', content: String(r.reply) }]);
      }
      // Модель возвращает профиль целиком; фото она не видит, поэтому его сохраняем.
      if (r?.profile && typeof r.profile === 'object') {
        const photo = st.profile.photo;
        patch({ profile: photo ? { ...r.profile, photo } : r.profile });
      }
    } catch {
      setTyping(false);
      say('bot', T('Связь на секунду пропала. Повторишь?', 'I lost the connection for a second. Say that again?'));
    }
  };

  const pct = STEP_PROGRESS[step] ?? 0;

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <View style={s.head}>
          <View style={s.avatar} />
          <Text style={s.headTitle}>{HEADER_TITLE()}</Text>
          <Text style={s.headPct}>{pct}%</Text>
        </View>
        <View style={s.track}>
          <View style={[s.trackFill, { width: `${pct}%` }]} />
        </View>

        <ScrollView ref={scroller} contentContainerStyle={s.thread} keyboardShouldPersistTaps="handled">
          {thread.map((m, i) => (
            <View key={i} style={{ alignItems: m.who === 'me' ? 'flex-end' : 'flex-start' }}>
              {m.photo ? (
                <Image source={{ uri: m.photo }} style={s.threadPhoto} />
              ) : (
                <View style={[s.bub, m.who === 'me' ? s.bubMe : s.bubBot]}>
                  <Text style={[s.bubText, m.who === 'me' && { color: color.onPrimary }]}>{m.text}</Text>
                </View>
              )}
              <Text style={s.time}>{m.at}</Text>
            </View>
          ))}

          {typing ? (
            <View style={[s.bub, s.bubBot, { alignSelf: 'flex-start' }]}>
              <ActivityIndicator size="small" color={color.muted} />
            </View>
          ) : null}

          {!typing ? (
            <StepWidget
              step={step}
              say={say}
              goto={goto}
              onDone={() => router.push('/summary')}
            />
          ) : null}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: Math.max(insets.bottom, 10) }]}>
          <Pressable style={s.back} onPress={() => router.back()} accessibilityLabel={T('Назад', 'Back')}>
            <Text style={s.backIcon}>‹</Text>
          </Pressable>
          <View style={s.composer}>
            <TextInput
              style={s.input}
              value={draft}
              onChangeText={setDraft}
              placeholder={COMPOSER_PLACEHOLDER()}
              placeholderTextColor={color.neutral400}
              onSubmitEditing={send}
              returnKeyType="send"
            />
            <Pressable onPress={send} accessibilityLabel={T('Отправить', 'Send')}>
              <Text style={s.mic}>{draft.trim() ? '↑' : '🎙'}</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

// ============================================================ виджеты шагов

function StepWidget({
  step, say, goto, onDone,
}: {
  step: StepId;
  say: (who: 'bot' | 'me', text: string, photo?: string) => void;
  goto: (s: StepId, line: string) => void;
  onDone: () => void;
}) {
  const st = useOnb();

  if (step === 'start') return <StartW say={say} goto={goto} />;
  if (step === 'basics') return <BasicsW say={say} goto={goto} />;
  if (step === 'area') return <AreaW say={say} goto={goto} />;
  if (step === 'languages') return <LangW say={say} goto={goto} />;
  if (step === 'hobbies') return <HobbyW say={say} goto={goto} name={st.profile.name || ''} />;
  if (step === 'photo') return <PhotoW say={say} onDone={onDone} name={st.profile.name || ''} />;
  return null;
}

function Hint({ children }: { children: React.ReactNode }) {
  return <Text style={s.hint}>{children}</Text>;
}

function Chip({ label, on, onPress }: { label: string; on?: boolean; onPress?: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: !!on }}
      style={({ pressed }) => [s.chip, on && s.chipOn, pressed && { opacity: 0.85 }]}
    >
      <Text style={[s.chipText, on && { color: color.onPrimary }]}>{label}</Text>
    </Pressable>
  );
}

function Cta({ label, onPress, disabled, kind = 'primary' }: {
  label: string; onPress?: () => void; disabled?: boolean; kind?: 'primary' | 'dark' | 'muted';
}) {
  const bg = kind === 'primary' ? color.primary : kind === 'dark' ? color.ink : color.neutral100;
  const fg = kind === 'muted' ? color.fg : color.onPrimary;
  return (
    <Pressable
      onPress={disabled ? undefined : onPress}
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      style={({ pressed }) => [s.cta, { backgroundColor: bg, opacity: disabled ? 0.45 : pressed ? 0.9 : 1 }]}
    >
      <Text style={[s.ctaText, { color: fg }]}>{label}</Text>
    </Pressable>
  );
}

/** A.04 — согласие, потом имя. Имя человек пишет в композер: так на борде. */
function StartW({ say, goto }: any) {
  const st = useOnb();
  const [asked, setAsked] = useState(false);
  if (st.profile.name) return null;
  return (
    <View style={s.widget}>
      <Hint>{STEP_START.hint()}</Hint>
      <View style={s.row}>
        <Chip
          label={STEP_START.why()}
          onPress={() => {
            if (asked) return;
            setAsked(true);
            say('me', STEP_START.why());
            setTimeout(() => say('bot', STEP_START.whyAnswer()), 600);
          }}
        />
        <Chip
          label={STEP_START.go()}
          on
          onPress={() => {
            say('me', STEP_START.go());
            setTimeout(() => say('bot', STEP_START.askName()), 600);
          }}
        />
      </View>
    </View>
  );
}

/** A.05 — кольцо возраста и пол. */
function BasicsW({ say, goto }: any) {
  const [age, setAge] = useState(28);
  const [sex, setSex] = useState<string | null>(null);
  return (
    <View style={s.widget}>
      <Text style={s.label}>{STEP_BASICS.ageLabel()}</Text>
      <AgeDial value={age} onChange={setAge} />
      <Text style={s.label}>{STEP_BASICS.sexLabel()}</Text>
      <View style={s.row}>
        {SEXES.map(([k]) => (
          <Chip key={k} label={sexLabel(k)} on={sex === k} onPress={() => setSex(k)} />
        ))}
      </View>
      <Cta
        label={STEP_BASICS.cta()}
        disabled={!sex}
        onPress={() => {
          set('age', age);
          // «Any is fine» — это не пол, а отсутствие предпочтения. В профиль он не пишется,
          // иначе матчинг получит «Any» как значение и станет искать людей с таким полом.
          if (sex && sex !== 'Any') set('gender', sex);
          say('me', `${age}, ${sexLabel(sex!)}`);
          goto('area', STEP_AREA.bot());
        }}
      />
    </View>
  );
}

/** A.06 — страна, радиус, карта. */
function AreaW({ say, goto }: any) {
  const [area, setArea] = useState<Area>({ label: 'Spain', lat: 41.3874, lon: 2.1686, km: 19 });
  return (
    <View style={s.widget}>
      <AreaPicker value={area} onChange={setArea} />
      <Cta
        label={STEP_AREA.cta()}
        onPress={() => {
          set('city', area.label);
          set('geo.comfortableAreas', [area.label]);
          set('geo.located', true);
          set('geo.coarseLat', area.lat);
          set('geo.coarseLon', area.lon);
          set('geo.maxDistanceKm', area.km);
          say('me', `${area.label}, ${area.km} km`);
          goto('languages', STEP_LANGUAGES.bot());
        }}
      />
    </View>
  );
}

/** A.07 — языки с флагами. */
function LangW({ say, goto }: any) {
  const [sel, setSel] = useState<string[]>([]);
  const toggle = (k: string) => setSel((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  return (
    <View style={s.widget}>
      <Hint>{STEP_LANGUAGES.hint()}</Hint>
      <View style={s.row}>
        {LANGS.map(([k]) => (
          <Chip key={k} label={langLabel(k)} on={sel.includes(k)} onPress={() => toggle(k)} />
        ))}
        <Chip label={'+ ' + STEP_LANGUAGES.own()} />
      </View>
      <Cta
        label={STEP_LANGUAGES.cta()}
        disabled={!sel.length}
        onPress={() => {
          set('languages.comfortable', sel);
          say('me', sel.map(langPlain).join(', '));
          goto('hobbies', STEP_HOBBIES.bot());
        }}
      />
    </View>
  );
}

/** A.08 — увлечения с эмодзи. */
function HobbyW({ say, goto, name }: any) {
  const [sel, setSel] = useState<string[]>([]);
  const toggle = (k: string) => setSel((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  return (
    <View style={s.widget}>
      <Hint>{STEP_HOBBIES.hint()}</Hint>
      <View style={s.row}>
        {HOBBIES.map(([k]) => (
          <Chip key={k} label={hobbyLabel(k)} on={sel.includes(k)} onPress={() => toggle(k)} />
        ))}
        <Chip label={'+ ' + STEP_HOBBIES.own()} />
      </View>
      <Cta
        label={STEP_HOBBIES.cta()}
        disabled={!sel.length}
        onPress={() => {
          set('interests.explicit', sel);
          say('me', sel.map(hobbyPlain).join(', '));
          goto('photo', STEP_PHOTO.greet(name));
          setTimeout(() => say('bot', STEP_PHOTO.ask()), 1400);
        }}
      />
    </View>
  );
}

/** A.09–A.13 — снять, загрузить или пропустить; затем подтверждение. */
function PhotoW({ say, onDone, name }: any) {
  const [uri, setUri] = useState<string | null>(null);
  const [stage, setStage] = useState<'ask' | 'result' | 'confirmed'>('ask');
  const [busy, setBusy] = useState(false);

  const shrink = async (src: string) => {
    // Ужимаем ДО отправки: сервер режет всё тяжелее 600 КБ, и снимок с камеры не пролезает.
    const ctx = ImageManipulator.ImageManipulator.manipulate(src);
    const img = await ctx.resize({ width: 512, height: null }).renderAsync();
    const out = await img.saveAsync({ compress: 0.75, format: ImageManipulator.SaveFormat.JPEG, base64: true });
    set('photo', `data:image/jpeg;base64,${out.base64}`);
    set('photoStatus', 'set');
    return out.uri;
  };

  const take = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return;
    const r = await ImagePicker.launchCameraAsync({ cameraType: ImagePicker.CameraType.front, allowsEditing: true, aspect: [1, 1], quality: 0.9 });
    if (r.canceled || !r.assets?.length) return;
    setBusy(true);
    try { setUri(await shrink(r.assets[0].uri)); setStage('result'); } finally { setBusy(false); }
  };

  const upload = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsEditing: true, aspect: [1, 1], quality: 0.9 });
    if (r.canceled || !r.assets?.length) return;
    setBusy(true);
    try { setUri(await shrink(r.assets[0].uri)); setStage('result'); } finally { setBusy(false); }
  };

  if (stage === 'ask') {
    return (
      <View style={s.widget}>
        <Hint>{STEP_PHOTO.hint()}</Hint>
        <Cta label={STEP_PHOTO.take()} onPress={take} />
        <Cta label={STEP_PHOTO.upload()} kind="dark" onPress={upload} />
        <Cta
          label={STEP_PHOTO.skip()}
          kind="muted"
          onPress={() => {
            set('photoStatus', 'skipped');
            onDone();
          }}
        />
        {busy ? <ActivityIndicator color={color.primary} /> : null}
      </View>
    );
  }

  if (stage === 'result') {
    return (
      <View style={s.widget}>
        {uri ? <Image source={{ uri }} style={s.resultPhoto} /> : null}
        <View style={s.bubBot}><Text style={s.bubText}>{STEP_PHOTO.praise()}</Text></View>
        <Hint>{STEP_PHOTO.pickHint()}</Hint>
        <View style={s.rowSplit}>
          <View style={{ flex: 1 }}>
            <Cta label={STEP_PHOTO.use()} onPress={() => { say('bot', STEP_PHOTO.confirmed()); setStage('confirmed'); }} />
          </View>
          <View style={{ flex: 1 }}>
            <Cta label={STEP_PHOTO.retake()} kind="muted" onPress={() => { setUri(null); setStage('ask'); }} />
          </View>
        </View>
      </View>
    );
  }

  return (
    <View style={s.widget}>
      <View style={s.doneCard}>
        {uri ? <Image source={{ uri }} style={s.doneAvatar} /> : <View style={[s.doneAvatar, { backgroundColor: color.neutral100 }]} />}
        <View style={{ flex: 1 }}>
          <Text style={s.doneTitle}>{STEP_PHOTO.cardTitle()}</Text>
          <Text style={s.doneSub}>{STEP_PHOTO.cardSub(name)}</Text>
        </View>
        <Text style={s.check}>✓</Text>
      </View>
      <View style={s.bubBot}><Text style={s.bubText}>{STEP_PHOTO.next()}</Text></View>
      <Cta label={STEP_PHOTO.cta()} onPress={onDone} />
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20, paddingBottom: 10 },
  avatar: { width: 34, height: 34, borderRadius: 17, backgroundColor: color.primary },
  headTitle: { flex: 1, ...type.title, color: color.fg, fontWeight: '700' } as any,
  headPct: { ...type.labelMedium, color: color.muted } as any,
  track: { height: 3, backgroundColor: color.neutral100, marginHorizontal: 20, borderRadius: 2 },
  trackFill: { height: 3, backgroundColor: color.primary, borderRadius: 2 },

  thread: { paddingHorizontal: 20, paddingTop: space.lg, paddingBottom: space.lg, gap: 4 },
  bub: { maxWidth: '86%', paddingVertical: 12, paddingHorizontal: 14, marginTop: space.sm },
  bubBot: { alignSelf: 'flex-start', backgroundColor: color.neutral100, borderRadius: 16 },
  bubMe: { alignSelf: 'flex-end', backgroundColor: color.primary, borderRadius: 16 },
  bubText: { ...type.body, color: color.fg } as any,
  time: { ...type.caption, color: color.neutral400, marginTop: 3 } as any,
  threadPhoto: { width: 150, height: 190, borderRadius: 14, marginTop: space.sm },

  widget: { gap: space.md, marginTop: space.md, width: '100%' },
  hint: { ...type.caption, color: color.muted } as any,
  label: { ...type.bodySmall, color: color.muted } as any,
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  rowSplit: { flexDirection: 'row', gap: space.sm },
  chip: {
    height: 38, paddingHorizontal: 14, borderRadius: rad.full, borderWidth: 1,
    borderColor: color.border, backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  chipOn: { backgroundColor: color.primary, borderColor: color.primary },
  chipText: { ...type.labelMedium, color: color.fg } as any,
  cta: { height: 52, borderRadius: rad.full, alignItems: 'center', justifyContent: 'center' },
  ctaText: { ...type.button } as any,

  resultPhoto: { width: '100%', height: 260, borderRadius: rad.md },
  doneCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: color.card,
    borderRadius: rad.lg, padding: 12,
  },
  doneAvatar: { width: 40, height: 40, borderRadius: 20 },
  doneTitle: { ...type.title, color: color.fg } as any,
  doneSub: { ...type.bodySmall, color: color.muted } as any,
  check: { color: color.successText, fontSize: 20, fontWeight: '700' },

  dock: {
    flexDirection: 'row', alignItems: 'center', gap: space.md,
    paddingHorizontal: 16, paddingTop: space.sm, backgroundColor: color.bg,
  },
  back: {
    width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: color.border,
    backgroundColor: color.card, alignItems: 'center', justifyContent: 'center',
  },
  backIcon: { fontSize: 26, color: color.fg, marginTop: -3 },
  composer: {
    flex: 1, height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  input: { flex: 1, color: color.fg, fontSize: 15 },
  mic: { fontSize: 18, color: color.muted },
});
