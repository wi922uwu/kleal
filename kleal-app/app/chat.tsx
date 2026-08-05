/**
 * Онбординг-чат: агент задаёт по одному вопросу, под каждым — свой виджет.
 *
 * Порт вебовой реализации, шаг в шаг: ready → name → basics → location → language → interests →
 * photo. Реплики агента приходят по одной с паузой — это не украшение: одновременно вываленные
 * два пузыря читаются как форма, а не как разговор, а весь смысл этого экрана в том, что профиль
 * собирается разговором.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  StyleSheet,
  Text,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Image,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import * as ImageManipulator from 'expo-image-manipulator';
import { SCRIPT, GENDERS, genderLabel, LANGS, langLabel, INTERESTS, intLabel } from '../src/onboarding';
import { useLang, T } from '../src/i18n';
import { useOnb, set, patch } from '../src/state';
import { Btn, Chip, Field } from '../src/components/ui';
import { color, radius, space, type } from '../src/theme';

type Msg = { who: 'bot' | 'me'; text: string };

export default function Chat() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const [thread, setThread] = useState<Msg[]>([]);
  const [stepIdx, setStepIdx] = useState(0);
  const [typing, setTyping] = useState(false);
  const scroller = useRef<ScrollView>(null);

  const step = SCRIPT[stepIdx];

  // Реплики текущего шага — по одной, с паузой между ними.
  useEffect(() => {
    if (!step) return;
    let alive = true;
    const lines = step.bot({ name: st.profile.name });
    setTyping(true);
    (async () => {
      for (let i = 0; i < lines.length; i++) {
        await new Promise((r) => setTimeout(r, i === 0 ? 350 : 700));
        if (!alive) return;
        setThread((t) => [...t, { who: 'bot', text: lines[i] }]);
      }
      if (alive) setTyping(false);
    })();
    return () => {
      alive = false;
    };
    // намеренно только по индексу шага: имя внутри реплики берётся на момент показа
  }, [stepIdx]);

  useEffect(() => {
    const id = setTimeout(() => scroller.current?.scrollToEnd({ animated: true }), 60);
    return () => clearTimeout(id);
  }, [thread.length, typing]);

  const answer = useCallback(
    (echo: string) => {
      setThread((t) => [...t, { who: 'me', text: echo }]);
      setTimeout(() => {
        if (stepIdx + 1 >= SCRIPT.length) {
          patch({ step: SCRIPT.length });
          router.push('/summary');
        } else {
          setStepIdx((i) => i + 1);
          patch({ step: stepIdx + 1 });
        }
      }, 250);
    },
    [stepIdx, router]
  );

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[s.wrap, { paddingTop: insets.top + 8 }]}>
        <View style={s.head}>
          <Text style={s.mark}>kleal</Text>
          <View style={s.progress}>
            <View style={[s.progressBar, { width: `${((stepIdx + 1) / SCRIPT.length) * 100}%` }]} />
          </View>
        </View>

        <ScrollView ref={scroller} contentContainerStyle={s.thread} keyboardShouldPersistTaps="handled">
          {thread.map((m, i) => (
            <View key={i} style={[s.bub, m.who === 'me' ? s.bubMe : s.bubBot]}>
              <Text style={[s.bubText, m.who === 'me' && { color: color.onPrimary }]}>{m.text}</Text>
            </View>
          ))}
          {typing ? (
            <View style={[s.bub, s.bubBot, { flexDirection: 'row', gap: 6 }]}>
              <ActivityIndicator size="small" color={color.muted} />
            </View>
          ) : null}
        </ScrollView>

        <View style={[s.dock, { paddingBottom: Math.max(insets.bottom, 12) }]}>
          {step?.hint ? <Text style={s.hint}>{step.hint()}</Text> : null}
          {!typing && step ? <Widget id={step.id} onAnswer={answer} /> : null}
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------- виджеты шагов

function Widget({ id, onAnswer }: { id: string; onAnswer: (echo: string) => void }) {
  switch (id) {
    case 'ready':
      return <ReadyW onAnswer={onAnswer} />;
    case 'name':
      return <NameW onAnswer={onAnswer} />;
    case 'basics':
      return <BasicsW onAnswer={onAnswer} />;
    case 'location':
      return <LocationW onAnswer={onAnswer} />;
    case 'language':
      return <LanguageW onAnswer={onAnswer} />;
    case 'interests':
      return <InterestsW onAnswer={onAnswer} />;
    case 'photo':
      return <PhotoW onAnswer={onAnswer} />;
    default:
      return null;
  }
}

function ReadyW({ onAnswer }: { onAnswer: (e: string) => void }) {
  return (
    <View style={{ gap: space.md }}>
      <Btn label={T('Давай', 'Sure, let’s go')} onPress={() => onAnswer(T('Давай', 'Sure, let’s go'))} />
    </View>
  );
}

function NameW({ onAnswer }: { onAnswer: (e: string) => void }) {
  const [v, setV] = useState('');
  const ok = v.trim().length >= 1;
  return (
    <View style={{ gap: space.md }}>
      <Field
        value={v}
        onChangeText={setV}
        placeholder={T('Как тебя зовут?', 'Your name')}
        autoCapitalize="words"
        returnKeyType="done"
        onSubmitEditing={() => ok && (set('name', v.trim()), onAnswer(v.trim()))}
      />
      <Btn
        label={T('Дальше', 'Next')}
        disabled={!ok}
        onPress={() => {
          set('name', v.trim());
          onAnswer(v.trim());
        }}
      />
    </View>
  );
}

function BasicsW({ onAnswer }: { onAnswer: (e: string) => void }) {
  const [age, setAge] = useState('');
  const [g, setG] = useState<string | null>(null);
  const n = parseInt(age, 10);
  // 18 — не оформительское ограничение: возраст младше режется жёстким гейтом в матчинге,
  // и человек, введя 16, получил бы пустую выдачу без единого объяснения.
  const ok = !!g && Number.isFinite(n) && n >= 18 && n <= 100;
  return (
    <View style={{ gap: space.md }}>
      <View style={s.row}>
        {GENDERS.map(([k]) => (
          <Chip key={k} label={genderLabel(k)} on={g === k} onPress={() => setG(k)} />
        ))}
      </View>
      <Field
        value={age}
        onChangeText={(t) => setAge(t.replace(/[^0-9]/g, '').slice(0, 3))}
        placeholder={T('Возраст, от 18', 'Age, 18 or over')}
        keyboardType="number-pad"
      />
      <Btn
        label={T('Дальше', 'Next')}
        disabled={!ok}
        onPress={() => {
          set('gender', g);
          set('age', n);
          onAnswer(`${genderLabel(g!)}, ${n}`);
        }}
      />
    </View>
  );
}

function LocationW({ onAnswer }: { onAnswer: (e: string) => void }) {
  const [city, setCity] = useState('');
  const ok = city.trim().length >= 2;
  return (
    <View style={{ gap: space.md }}>
      <Field value={city} onChangeText={setCity} placeholder={T('Город или район', 'City or area')} />
      <Btn
        label={T('Дальше', 'Next')}
        disabled={!ok}
        onPress={() => {
          const v = city.trim();
          set('city', v);
          set('geo.comfortableAreas', [v]);
          set('geo.located', true);
          // Пока без карты: точку человек уточняет в профиле, а радиус по умолчанию тот же,
          // что и на вебе. Карта с перетаскиваемым пином — отдельный шаг переноса.
          set('geo.maxDistanceKm', 15);
          onAnswer(v);
        }}
      />
    </View>
  );
}

function LanguageW({ onAnswer }: { onAnswer: (e: string) => void }) {
  const [sel, setSel] = useState<string[]>([]);
  const toggle = (l: string) => setSel((p) => (p.includes(l) ? p.filter((x) => x !== l) : [...p, l]));
  return (
    <View style={{ gap: space.md }}>
      <View style={s.row}>
        {LANGS.map((l) => (
          <Chip key={l} label={langLabel(l)} on={sel.includes(l)} onPress={() => toggle(l)} />
        ))}
      </View>
      <Btn
        label={T('Дальше', 'Next')}
        disabled={!sel.length}
        onPress={() => {
          set('languages.comfortable', sel);
          onAnswer(sel.map(langLabel).join(', '));
        }}
      />
    </View>
  );
}

function InterestsW({ onAnswer }: { onAnswer: (e: string) => void }) {
  const [sel, setSel] = useState<string[]>([]);
  const [own, setOwn] = useState('');
  const toggle = (k: string) => setSel((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  const all = () => {
    const extra = own.split(',').map((x) => x.trim().toLowerCase()).filter(Boolean);
    return Array.from(new Set([...sel, ...extra]));
  };
  const list = all();
  return (
    <View style={{ gap: space.md }}>
      <View style={s.row}>
        {INTERESTS.map(([k]) => (
          <Chip key={k} label={intLabel(k)} on={sel.includes(k)} onPress={() => toggle(k)} />
        ))}
      </View>
      <Field value={own} onChangeText={setOwn} placeholder={T('Своё, через запятую', 'Your own, comma separated')} />
      <Btn
        label={T('Дальше', 'Next')}
        disabled={!list.length}
        onPress={() => {
          set('interests.explicit', list);
          onAnswer(list.map(intLabel).join(', '));
        }}
      />
    </View>
  );
}

function PhotoW({ onAnswer }: { onAnswer: (e: string) => void }) {
  const [uri, setUri] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pick = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) return;
    const r = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.9,
    });
    if (r.canceled || !r.assets?.length) return;
    setBusy(true);
    try {
      // Ужимаем ДО отправки: сервер режет всё тяжелее 600 КБ, и фото с современной камеры
      // не пролезает — на вебе ровно та же уценка перед загрузкой.
      const ctx = ImageManipulator.ImageManipulator.manipulate(r.assets[0].uri);
      const img = await ctx.resize({ width: 512, height: null }).renderAsync();
      const out = await img.saveAsync({ compress: 0.75, format: ImageManipulator.SaveFormat.JPEG, base64: true });
      setUri(out.uri);
      set('photo', `data:image/jpeg;base64,${out.base64}`);
      set('photoStatus', 'set');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ gap: space.md }}>
      {uri ? <Image source={{ uri }} style={s.preview} /> : null}
      <Btn
        kind="secondary"
        label={uri ? T('Выбрать другое', 'Pick another') : T('Добавить фото', 'Add a photo')}
        busy={busy}
        onPress={pick}
      />
      <Btn
        label={uri ? T('Готово', 'Done') : T('Пока без фото', 'Skip for now')}
        onPress={() => {
          if (!uri) set('photoStatus', 'skipped');
          onAnswer(uri ? T('Фото добавлено', 'Photo added') : T('Пока без фото', 'Skip for now'));
        }}
      />
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { paddingHorizontal: 20, paddingBottom: space.md, gap: space.sm },
  mark: { fontSize: 18, fontWeight: '700', color: color.primary },
  progress: { height: 4, borderRadius: 2, backgroundColor: color.neutral100, overflow: 'hidden' },
  progressBar: { height: 4, borderRadius: 2, backgroundColor: color.primary },
  thread: { paddingHorizontal: 20, paddingBottom: space.lg, gap: space.sm },
  bub: { maxWidth: '86%', paddingVertical: 12, paddingHorizontal: 14 },
  bubBot: {
    alignSelf: 'flex-start',
    backgroundColor: color.neutral100,
    borderRadius: 18,
    borderBottomLeftRadius: 4,
  },
  bubMe: {
    alignSelf: 'flex-end',
    backgroundColor: color.primary,
    borderRadius: 18,
    borderBottomRightRadius: 4,
  },
  bubText: { ...type.body, color: color.fg } as any,
  dock: {
    paddingHorizontal: 20,
    paddingTop: space.md,
    gap: space.sm,
    borderTopWidth: 1,
    borderTopColor: color.line,
    backgroundColor: color.bg,
  },
  hint: { ...type.caption, color: color.muted } as any,
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  preview: { width: 96, height: 96, borderRadius: radius.full, alignSelf: 'center' },
});
