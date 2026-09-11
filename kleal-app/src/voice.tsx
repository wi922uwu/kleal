import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator, Alert, Animated, Easing, PanResponder, Platform, Pressable,
  StyleSheet, Text, View,
} from 'react-native';
import * as Haptics from 'expo-haptics';
import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioPlayer,
  useAudioPlayerStatus,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { Asset } from 'expo-asset';
import { appendUploadFile } from './upload-file';
import { mediaUrl, speech, VoicePayload } from './api';
import { T } from './i18n';
import { color } from './theme';
import { IconChevronUp, IconLock, IconMic, IconPlay, IconSend, IconTrash } from './components/icons';

type DictationPhase = 'idle' | 'recording' | 'transcribing';
type MessagePhase = 'idle' | 'recording' | 'preview' | 'uploading';

const MAX_DURATION_MS = 60000;
/**
 * Короче этого — не сообщение, а случайное касание микрофона. При удержании кнопка отправляет
 * сразу по отпусканию, поэтому без нижней границы промах пальцем улетал бы собеседнику шорохом.
 */
const MIN_DURATION_MS = 700;

/** Столбиков в готовом голосовом и в живой полоске во время записи. */
const WAVE_BARS = 34;
const LIVE_BARS = 22;

/**
 * ТАКТИЛЬНЫЙ ОТКЛИК. Запись ведут вслепую: палец закрывает кнопку, глаза чаще на собеседнике, а
 * не на экране. Поэтому каждый рубеж жеста отзывается пальцу, и отклики РАЗНЫЕ — по силе понятно,
 * что случилось, не глядя.
 *
 * Их ровно пять, и ни один не «просто приятный»: лишняя вибрация на каждый чих обесценивает те,
 * что несут смысл.
 *   старт    — лёгкий: запись пошла (иначе непонятно, поймала ли кнопка нажатие);
 *   рубеж    — лёгкий: перешагнул порог отмены, отпустишь — не отправится;
 *   замок    — средний, заметно сильнее: жест кончился, палец можно убирать;
 *   ушло     — лёгкий: сообщение отправлено;
 *   пропало  — предупреждающий: НИЧЕГО не отправлено (отмена или слишком короткое нажатие).
 *              Здесь отклик обязателен: молчаливая пропажа читается как поломка.
 */
const canBuzz = Platform.OS !== 'web';
const buzz = (style: Haptics.ImpactFeedbackStyle) => {
  if (canBuzz) Haptics.impactAsync(style).catch(() => {});
};
const buzzStarted = () => buzz(Haptics.ImpactFeedbackStyle.Light);
const buzzEdge = () => buzz(Haptics.ImpactFeedbackStyle.Light);
const buzzLocked = () => buzz(Haptics.ImpactFeedbackStyle.Medium);
const buzzSent = () => buzz(Haptics.ImpactFeedbackStyle.Light);
const buzzLost = () => {
  if (canBuzz) Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
};
const buzzTick = () => {
  if (canBuzz) Haptics.selectionAsync().catch(() => {});
};

/**
 * Уровень микрофона приходит в децибелах полной шкалы: 0 — предел, минус бесконечность — тишина.
 * Шкала логарифмическая, и разговорная речь живёт в её верхней трети, поэтому окно взято −50…0:
 * при честных −160 столбики не двигались бы вовсе.
 */
const LEVEL_FLOOR_DB = -50;
const levelOf = (db?: number | null) => {
  if (typeof db !== 'number' || !isFinite(db)) return 0;
  return Math.max(0, Math.min(1, (db - LEVEL_FLOOR_DB) / -LEVEL_FLOOR_DB));
};

/** Уровень нужен для живых столбиков — в пресете его нет, включается отдельно. */
const RECORDING_OPTIONS = { ...RecordingPresets.HIGH_QUALITY, isMeteringEnabled: true };

const formatDuration = (durationMs: number) => {
  const seconds = Math.max(0, Math.floor(durationMs / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
};

const audioForm = async (uri: string) => {
  const form = new FormData();
  if (Platform.OS === 'web') {
    const blob = await (await fetch(uri)).blob();
    form.append('file', blob, `voice-${Date.now()}.webm`);
  } else {
    await appendUploadFile(form, uri, `voice-${Date.now()}.m4a`, 'audio/mp4');
  }
  return form;
};

/**
 * ОГИБАЮЩАЯ — те самые столбики вместо полоски прогресса.
 *
 * Настоящая огибающая есть только у записи, сделанной здесь и сейчас: пока идёт запись, expo-audio
 * отдаёт уровень микрофона, он складывается в массив и кладётся сюда под тем id, который вернул
 * сервер. Всё остальное — чужие сообщения и свои после перезапуска — рисуется формой, выведенной
 * из самого id. Она не настоящая, но ПОСТОЯННАЯ: одно и то же сообщение всегда выглядит одинаково,
 * а разные — по-разному, и глазу этого хватает, чтобы отличать их в ленте.
 *
 * Чтобы столбики стали настоящими у всех, огибающую надо сохранять рядом с файлом на сервере
 * (`/api/speech/*` — чужая зона, см. AGENTS.md). Тогда правится ровно одна строка: источник в
 * `peaksFor`.
 */
const PEAKS = new Map<string, number[]>();

/** Сжать поток уровней до нужного числа столбиков: в каждом — самый громкий момент отрезка. */
export const barsFrom = (samples: number[], n = WAVE_BARS) => {
  if (!samples.length) return [];
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const from = Math.floor((i * samples.length) / n);
    const to = Math.max(from + 1, Math.floor(((i + 1) * samples.length) / n));
    let peak = 0;
    for (let j = from; j < to && j < samples.length; j++) peak = Math.max(peak, samples[j]);
    out.push(peak);
  }
  // Нормировка по собственному максимуму: тихая запись должна выглядеть так же живо, как громкая,
  // иначе сказанное вполголоса превращается в ровную ниточку.
  const top = Math.max(...out);
  return out.map((v) => (top > 0 ? Math.max(0.1, v / top) : 0.1));
};

/** Форма из id: одинаковая при каждом открытии, разная у разных сообщений. */
export const pseudoPeaks = (seed: string, n = WAVE_BARS) => {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const phase = ((h >>> 0) % 628) / 100;
  const rand = () => {
    h ^= h << 13; h ^= h >>> 17; h ^= h << 5;
    return ((h >>> 0) % 1000) / 1000;
  };
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    // Медленная волна даёт слоги, быстрая случайность — неровность внутри слога.
    const syllable = 0.55 + 0.45 * Math.sin(i * 0.9 + phase);
    out.push(Math.max(0.14, Math.min(1, syllable * (0.5 + 0.5 * rand()))));
  }
  return out;
};

const peaksFor = (id: string) => PEAKS.get(id) || pseudoPeaks(id || 'voice');

export const appendTranscript = (draft: string, transcript: string) =>
  draft.trim() ? `${draft.trimEnd()} ${transcript}` : transcript;

/** Existing dictation behavior used by onboarding text fields. */
export function useVoiceInput(onTranscript: (text: string) => void, disabled = false) {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder, 250);
  const [phase, setPhase] = useState<DictationPhase>('idle');
  const stopping = useRef(false);

  const fail = useCallback((message: string) => {
    setPhase('idle');
    Alert.alert(T('Не удалось распознать речь', 'Could not transcribe speech', 'No se pudo transcribir la voz'), message);
  }, []);

  const stop = useCallback(async () => {
    if (stopping.current || phase !== 'recording') return;
    stopping.current = true;
    setPhase('transcribing');
    try {
      await recorder.stop();
      await setAudioModeAsync({ allowsRecording: false });
      if (!recorder.uri) throw new Error('NO_RECORDING');
      const result = await speech.transcribe(await audioForm(recorder.uri));
      const text = String(result?.text || '').trim();
      if (!text) throw new Error('NO_SPEECH');
      onTranscript(text);
      setPhase('idle');
    } catch (error) {
      const code = String((error as any)?.body?.error || (error as any)?.message || '');
      fail(code === 'NO_SPEECH'
        ? T('Речь не обнаружена. Попробуйте ещё раз.', 'No speech was detected. Try again.', 'No se detectó ninguna voz. Inténtalo de nuevo.')
        : T('Проверьте соединение и повторите запись.', 'Check your connection and record again.', 'Comprueba tu conexión y vuelve a grabar.'));
    } finally {
      stopping.current = false;
    }
  }, [fail, onTranscript, phase, recorder]);

  const start = useCallback(async () => {
    if (disabled || phase !== 'idle') return;
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted) {
        return fail(T('Разрешите доступ к микрофону в настройках устройства.', 'Allow microphone access in device settings.', 'Permite el acceso al micrófono en los ajustes del dispositivo.'));
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setPhase('recording');
    } catch {
      fail(T('Не удалось начать запись.', 'Could not start recording.', 'No se pudo iniciar la grabación.'));
    }
  }, [disabled, fail, phase, recorder]);

  // Та же ловушка, что и у голосового сообщения: опрос успевает отдать снимок прошлой записи,
  // и предел срабатывает на ещё не начавшейся. Проверяем по снимку, который сам себя объявил.
  useEffect(() => {
    if (phase === 'recording' && recorderState.isRecording && recorderState.durationMillis >= MAX_DURATION_MS) stop();
  }, [phase, recorderState.isRecording, recorderState.durationMillis, stop]);

  return {
    phase, durationMillis: recorderState.durationMillis,
    toggle: phase === 'recording' ? stop : start,
    disabled: disabled || phase === 'transcribing',
  };
}

export type VoiceInput = ReturnType<typeof useVoiceInput>;

export function VoiceControl({ voice }: { voice: VoiceInput }) {
  const recording = voice.phase === 'recording';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={recording ? T('Остановить запись', 'Stop recording', 'Detener grabación') : T('Голосовой ввод', 'Voice input', 'Entrada por voz')}
      accessibilityState={{ disabled: voice.disabled, busy: voice.phase === 'transcribing' }}
      disabled={voice.disabled}
      onPress={voice.toggle}
      style={[s.iconButton, recording && s.recording]}
      hitSlop={8}
    >
      {voice.phase === 'transcribing' ? <ActivityIndicator size="small" color={color.primary} />
        : recording ? <><View style={s.stop} /><Text style={s.timer}>{formatDuration(voice.durationMillis)}</Text></>
        : <IconMic />}
    </Pressable>
  );
}

export function useVoiceMessage(onSend: (voice: VoicePayload) => void | Promise<void>, disabled = false) {
  const recorder = useAudioRecorder(RECORDING_OPTIONS);
  const recorderState = useAudioRecorderState(recorder, 100);
  const [phase, setPhase] = useState<MessagePhase>('idle');
  const [uri, setUri] = useState('');
  const [durationMillis, setDurationMillis] = useState(0);
  const [peaks, setPeaks] = useState<number[]>([]);
  const stopping = useRef(false);
  /** Весь поток уровней за запись: из него получится и живая полоска, и итоговая огибающая. */
  const samples = useRef<number[]>([]);

  // Уровень снимается по тику опроса, а не по изменению самого уровня: две одинаковые громкости
  // подряд — это два столбика, а не один, иначе временная ось поехала бы.
  useEffect(() => {
    if (phase !== 'recording') return;
    samples.current.push(levelOf(recorderState.metering));
  }, [phase, recorderState.metering, recorderState.durationMillis]);

  const reset = useCallback(() => {
    samples.current = [];
    setPeaks([]);
    setUri('');
    setDurationMillis(0);
    setPhase('idle');
  }, []);

  const fail = useCallback((title: string, message: string) => {
    reset();
    Alert.alert(title, message);
  }, [reset]);

  const stop = useCallback(async () => {
    if (stopping.current || phase !== 'recording') return;
    stopping.current = true;
    const recordedMs = Math.min(MAX_DURATION_MS, Math.max(250, recorderState.durationMillis));
    try {
      await recorder.stop();
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
      if (!recorder.uri) throw new Error('NO_RECORDING');
      setUri(recorder.uri);
      setDurationMillis(recordedMs);
      setPeaks(barsFrom(samples.current));
      setPhase('preview');
    } catch {
      fail(T('Запись не сохранена', 'Recording was not saved', 'La grabación no se guardó'), T('Попробуйте записать ещё раз.', 'Try recording again.', 'Inténtalo de nuevo.'));
    } finally {
      stopping.current = false;
    }
  }, [fail, phase, recorder, recorderState.durationMillis]);

  const start = useCallback(async () => {
    if (disabled || phase !== 'idle') return;
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted) {
        return Alert.alert(T('Нет доступа к микрофону', 'Microphone access is disabled', 'El acceso al micrófono está deshabilitado'), T(
          'Разрешите доступ к микрофону в настройках устройства.', 'Allow microphone access in device settings.'
        , 'Permite el acceso al micrófono en los ajustes del dispositivo.'));
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      samples.current = [];
      recorder.record();
      setPhase('recording');
    } catch {
      fail(T('Не удалось начать запись', 'Could not start recording', 'No se pudo iniciar la grabación'), T('Попробуйте ещё раз.', 'Try again.', 'Inténtalo de nuevo.'));
    }
  }, [disabled, fail, phase, recorder]);

  /**
   * Отправка. `from` — чтобы можно было отправить СРАЗУ после остановки, не дожидаясь, пока
   * состояние доедет до экрана.
   *
   * Зачем: при удержании кнопки запись заканчивается отпусканием пальца, и следом надо слать. Если
   * читать `uri` из состояния, его там ещё нет — `setUri` внутри `stop()` применяется на следующем
   * кадре, и отправка уходила бы с пустым файлом. Поэтому «остановить и отправить» передаёт путь
   * напрямую, а обычная отправка из превью по-прежнему берёт его из состояния. Огибающая едет тем
   * же путём и по той же причине.
   */
  const upload = useCallback(async (from?: { uri: string; ms: number; peaks: number[] }) => {
    const src = from?.uri || uri;
    const ms = from?.ms ?? durationMillis;
    const bars = from?.peaks || peaks;
    if (!src) return;
    setPhase('uploading');
    try {
      const result = await speech.uploadVoice(await audioForm(src), ms);
      const transcript = String(result?.transcript || result?.text || '').trim();
      if (!result?.id || !result?.url || !transcript) throw new Error('INVALID_VOICE_RESPONSE');
      if (bars.length) PEAKS.set(String(result.id), bars);
      await onSend({
        id: String(result.id), url: String(result.url), duration_ms: Number(result.duration_ms),
        transcript, mime_type: String(result.mime_type || 'audio/mp4'), language: result.language,
      });
      // Отклик здесь, а не у кнопки: отправка бывает двух путей — отпусканием и из превью, — но
      // подтверждать надо только по-настоящему ушедшее. Ошибка ниже уходит в свою ветку.
      buzzSent();
      reset();
    } catch (error) {
      // Возврат в превью, а НЕ в пустоту: запись цела, и человек может отправить её ещё раз или
      // послушать. Терять надиктованное из-за отвалившейся сети нельзя.
      setUri(src);
      setDurationMillis(ms);
      setPeaks(bars);
      setPhase('preview');
      const code = String((error as any)?.body?.error || (error as any)?.message || '');
      Alert.alert(
        T('Не удалось отправить голосовое', 'Could not send voice message', 'No se pudo enviar el mensaje de voz'),
        code === 'NO_SPEECH'
          ? T('Речь не обнаружена. Запишите сообщение ещё раз.', 'No speech was detected. Record the message again.', 'No se detectó ninguna voz. Vuelve a grabar el mensaje.')
          : T('Проверьте соединение и повторите отправку.', 'Check your connection and try sending again.', 'Comprueba tu conexión y vuelve a enviar.')
      );
    }
  }, [durationMillis, onSend, peaks, reset, uri]);

  /**
   * Отпустил палец — записать и отправить одним движением. Так работает удержание в мессенджерах:
   * между «сказал» и «ушло» не должно быть ещё одного касания.
   *
   * Слишком короткое нажатие записью не считается: случайный тап по микрофону иначе отправлял бы
   * собеседнику двухсотмиллисекундный шорох.
   */
  const stopAndSend = useCallback(async () => {
    if (stopping.current || phase !== 'recording') return;
    stopping.current = true;
    const ms = Math.min(MAX_DURATION_MS, recorderState.durationMillis);
    const bars = barsFrom(samples.current);
    try {
      await recorder.stop();
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
      const src = recorder.uri;
      if (!src) throw new Error('NO_RECORDING');
      // Слишком короткое нажатие выбрасывается молча — но не беззвучно для пальца: иначе человек
      // уверен, что отправил, а в переписке пусто.
      if (ms < MIN_DURATION_MS) { buzzLost(); reset(); return; }
      await upload({ uri: src, ms, peaks: bars });
    } catch {
      fail(T('Запись не сохранена', 'Recording was not saved', 'La grabación no se guardó'),
           T('Попробуйте записать ещё раз.', 'Try recording again.', 'Inténtalo de nuevo.'));
    } finally {
      stopping.current = false;
    }
  }, [fail, phase, recorder, recorderState.durationMillis, reset, upload]);

  const send = useCallback(async () => {
    if (phase !== 'preview' || !uri) return;
    await upload({ uri, ms: durationMillis, peaks });
  }, [durationMillis, peaks, phase, upload, uri]);

  /**
   * Минутный предел. Условие смотрит на `isRecording`, и это не перестраховка.
   *
   * `recorderState` — ОПРОС, и в первые кадры после старта он ещё отдаёт снимок ПРОШЛОЙ записи.
   * После записи, дошедшей до предела, там лежит ровно 60000 — и следующая запись умирала, не
   * начавшись: жест только успевал прижать кнопку, а экран уже прыгал в превью с «00:00» и
   * плоской волной. Снимок, который сам говорит «идёт запись», всегда свежий, и в нём отсчёт
   * начинается с нуля.
   */
  useEffect(() => {
    if (phase === 'recording' && recorderState.isRecording && recorderState.durationMillis >= MAX_DURATION_MS) stop();
  }, [phase, recorderState.isRecording, recorderState.durationMillis, stop]);

  return {
    phase, uri, peaks,
    durationMillis: phase === 'recording' ? recorderState.durationMillis : durationMillis,
    /** Мгновенная громкость 0…1 — по ней дышит ореол вокруг микрофона. */
    level: phase === 'recording' ? levelOf(recorderState.metering) : 0,
    /** Хвост записи для живой полоски у закреплённой записи. */
    liveBars: samples.current.slice(-LIVE_BARS),
    start, stop, stopAndSend, cancel: reset, send, disabled: disabled || phase === 'uploading',
  };
}

export type VoiceMessage = ReturnType<typeof useVoiceMessage>;

// ======================================================================== проигрывание

/**
 * Столбики вместо полоски. Заполнение сделано двумя одинаковыми рядами: нижний приглушённый,
 * верхний цветной внутри окна, которое растёт по мере проигрывания.
 *
 * Окно двигается ДВУМЯ смещениями навстречу друг другу — маска уезжает влево, содержимое внутри
 * неё возвращается вправо на столько же. Так столбики стоят на месте, а не ползут, и всё это
 * остаётся трансформами: их считает нативная сторона, и заполнение не дёргается на каждом кадре
 * ленты. Ширину анимировать нельзя — она пересчитывает разметку в JS.
 */
function Waveform({
  peaks, progress, mine, onSeek,
}: {
  peaks: number[]; progress: number; mine: boolean; onSeek: (fraction: number) => void;
}) {
  const [width, setWidth] = useState(0);
  /**
   * Пока палец ведёт, заполнение слушается ЕГО, а не плеера: позиция от плеера приходит раз в
   * 200 мс, и если ждать её, полоса тащится за пальцем с заметным отставанием. После отпускания
   * ещё четверть секунды держим своё значение — ровно чтобы дождаться первого отчёта с новой
   * позиции и не дать заполнению отскочить назад.
   */
  const [scrub, setScrub] = useState<number | null>(null);
  const p = useRef(new Animated.Value(0)).current;
  const widthRef = useRef(0);
  widthRef.current = width;
  const seekRef = useRef(onSeek);
  seekRef.current = onSeek;

  useEffect(() => {
    // Плеер сообщает позицию раз в 200 мс. Догоняем её ровно за этот шаг — тогда движение
    // непрерывное, а не ступенчатое.
    Animated.timing(p, {
      toValue: scrub ?? progress, duration: scrub == null ? 220 : 0, easing: Easing.linear, useNativeDriver: true,
    }).start();
  }, [p, progress, scrub]);

  // Обработчики создаются один раз: пересборка на каждом кадре роняла бы жест на полпути.
  const responder = useRef(PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: (e) => grab(e.nativeEvent.locationX),
    onPanResponderMove: (e) => grab(e.nativeEvent.locationX),
    onPanResponderRelease: () => release(),
    onPanResponderTerminate: () => release(),
  })).current;

  function grab(x: number) {
    if (widthRef.current <= 0) return;
    const f = Math.max(0, Math.min(1, x / widthRef.current));
    setScrub(f);
    seekRef.current(f);
  }
  function release() {
    setTimeout(() => setScrub(null), 260);
  }

  const back = Animated.multiply(Animated.add(p, -1), width);
  const forth = Animated.multiply(Animated.add(p, -1), -width);
  const bars = peaks.length ? peaks : pseudoPeaks('empty');

  const row = (tint: string) => (
    <View style={[s.waveRow, width > 0 && { width }]} pointerEvents="none">
      {bars.map((v, i) => (
        <View key={i} style={[s.waveBar, { height: 3 + Math.round(v * 17), backgroundColor: tint }]} />
      ))}
    </View>
  );

  return (
    <View
      style={s.wave}
      onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
      {...responder.panHandlers}
    >
      {row(mine ? color.onCoverSoft : color.neutral300)}
      <Animated.View style={[s.waveMask, { width, transform: [{ translateX: back }] }]} pointerEvents="none">
        <Animated.View style={{ width, transform: [{ translateX: forth }] }}>
          {row(mine ? color.onPrimary : color.primary)}
        </Animated.View>
      </Animated.View>
    </View>
  );
}

/**
 * Проигрыватель — и в пузыре сообщения, и в композере перед отправкой.
 *
 * `grow` РАЗДЕЛЯЕТ эти два случая, и разделять их обязательно. В композере проигрыватель стоит в
 * СТРОКЕ рядом с «удалить» и «отправить», и там `flex: 1` значит «займи оставшуюся ШИРИНУ». В
 * пузыре он стоит в КОЛОНКЕ над ссылкой «Показать текст», и тот же `flex: 1` значит «займи
 * оставшуюся ВЫСОТУ» — из-за чего шестисекундное голосовое разворачивалось красным полотном почти
 * на весь экран (снято 12 августа). Одного стиля на оба случая не бывает.
 */
function AudioPlay({
  source, durationMs, peaks, mine = false, grow = false,
}: { source: string; durationMs: number; peaks: number[]; mine?: boolean; grow?: boolean }) {
  /**
   * ЧУЖОЕ ГОЛОСОВОЕ СКАЧИВАЕТСЯ ЦЕЛИКОМ, и только потом попадает к проигрывателю.
   *
   * Иначе оно не играет вовсе. Проигрыватель на iOS тянет удалённый файл по кускам и требует от
   * сервера частичных запросов. Наш их не умеет: `Range: bytes=0-1023` возвращает 200 и файл
   * целиком вместо 206, заголовка `Accept-Ranges` нет — при том что сам файл отдаётся верно
   * (200, audio/mp4, столько байт, сколько на диске). Замерено на симуляторе 12 августа:
   * с прямым адресом состояние проигрывателя навсегда `isLoaded=0, isBuffering=1, duration=0`,
   * с локальным файлом — `isLoaded=1, duration=4.5`.
   *
   * Скачиваем САМИ, а не встроенным `downloadFirst`. Тот делает то же, но иначе: создаёт
   * проигрыватель с пустым источником и подменяет его на лету. Работает и так; здесь выбран
   * порядок без подмены — источник приходит уже готовым, и проигрыватель собирается сразу
   * вокруг него, а не проходит через состояние «есть, но играть нечего».
   *
   * Настоящее лекарство — частичные запросы в `services/llm` (`/api/speech/audio/*`). Это чужая
   * зона, см. AGENTS.md. Когда они появятся, всё это можно снять, и звук пойдёт, не дожидаясь
   * конца файла. Своей записи это не касается: она и так на диске.
   */
  const remote = /^https?:/i.test(source);
  const [cached, setCached] = useState<string | null>(null);
  useEffect(() => {
    if (!remote) { setCached(null); return; }
    let alive = true;
    Asset.fromURI(source).downloadAsync()
      .then((a) => { if (alive) setCached(a.localUri || a.uri); })
      .catch(() => {});
    return () => { alive = false; };
  }, [remote, source]);

  const player = useAudioPlayer(remote ? cached : source, { updateInterval: 200 });
  const status = useAudioPlayerStatus(player);
  const [rate, setRate] = useState(1);
  /** Скорость появляется только после первого запуска: до него это лишняя кнопка в пузыре. */
  const [started, setStarted] = useState(false);
  const total = status.duration > 0 ? status.duration * 1000 : durationMs;
  const current = Math.min(total, status.currentTime * 1000);
  const progress = total > 0 ? Math.max(0, Math.min(1, current / total)) : 0;

  const press = useRef(new Animated.Value(1)).current;
  const playing = useRef(new Animated.Value(0)).current;
  const rateIn = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (status.didJustFinish) player.seekTo(0);
  }, [player, status.didJustFinish]);

  useEffect(() => {
    Animated.timing(playing, {
      toValue: status.playing ? 1 : 0, duration: 140, easing: Easing.out(Easing.quad), useNativeDriver: true,
    }).start();
  }, [playing, status.playing]);

  useEffect(() => {
    if (!started) return;
    Animated.timing(rateIn, { toValue: 1, duration: 180, easing: Easing.out(Easing.quad), useNativeDriver: true }).start();
  }, [rateIn, started]);

  /**
   * Нажал — и ничего. Файл может не загрузиться (нет сети, адрес не тот), и до сих пор это
   * выглядело ровно как исправное молчание: кнопка нажимается, ничего не происходит, и человеку
   * нечем отличить «не работает» от «не слышно». Четыре секунды — с запасом на медленную сеть.
   */
  const [stuck, setStuck] = useState(false);
  useEffect(() => {
    if (!started || status.isLoaded) { setStuck(false); return; }
    const t = setTimeout(() => setStuck(true), 4000);
    return () => clearTimeout(t);
  }, [started, status.isLoaded]);

  /**
   * Режим звука включается ПЕРЕД каждым запуском, и это не перестраховка.
   *
   * `playsInSilentMode` выставлялся только в конце записи. Своё, только что записанное, поэтому
   * слушалось, а входящее в свежеоткрытой переписке — нет: при поднятом беззвучном переключателе
   * iOS просто не выпускает звук. Снаружи это выглядит как «голосовое не проигрывается»: волна
   * ползёт, отсчёт идёт, тишина.
   *
   * Ждём применения, а не пускаем вдогонку: иначе первые доли секунды успевают уйти в старом
   * режиме — ровно то начало фразы, ради которого сообщение и открывают.
   */
  const toggle = async () => {
    if (status.playing) { player.pause(); return; }
    setStarted(true);
    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => {});
    player.play();
  };

  /**
   * Перемотка и смена темпа в expo-audio 1.1.1 ГЛУШАТ проигрывание. Проверено на iOS 12 августа:
   * после `seekTo` позиция встаёт ровно туда, куда ткнули, но кнопка возвращается в «играть» и
   * звук больше не идёт. Для человека это «перемотал — и всё выключилось», поэтому играем дальше
   * сами. Повторный `play` у уже играющего ничего не делает, так что проверка одна — до вызова.
   */
  const keepPlaying = (act: () => void) => {
    const was = status.playing;
    act();
    if (was) player.play();
  };

  const cycleRate = () => {
    const next = rate === 1 ? 1.5 : rate === 1.5 ? 2 : 1;
    setRate(next);
    keepPlaying(() => player.setPlaybackRate(next, 'high'));
    buzzTick();
  };

  const tint = mine ? color.onPrimary : color.primary;
  return (
    <View style={[s.playRow, grow && s.playRowGrow]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={status.playing ? T('Пауза', 'Pause', 'Pausa') : T('Воспроизвести', 'Play', 'Reproducir')}
        onPress={toggle}
        onPressIn={() => Animated.spring(press, { toValue: 0.86, friction: 7, tension: 220, useNativeDriver: true }).start()}
        onPressOut={() => Animated.spring(press, { toValue: 1, friction: 5, tension: 200, useNativeDriver: true }).start()}
        style={s.playButton}
        hitSlop={6}
      >
        <Animated.View style={[s.playInner, { transform: [{ scale: press }] }]}>
          {/* Две иконки внахлёст: перетекание мягче, чем подмена одной на другую. */}
          <Animated.View style={[s.playIcon, { opacity: playing.interpolate({ inputRange: [0, 1], outputRange: [1, 0] }) }]}>
            <IconPlay size={18} c={tint} />
          </Animated.View>
          <Animated.View style={[s.playIcon, { opacity: playing }]}>
            <View style={s.pause}>
              <View style={[s.pauseBar, { backgroundColor: tint }]} />
              <View style={[s.pauseBar, { backgroundColor: tint }]} />
            </View>
          </Animated.View>
        </Animated.View>
      </Pressable>

      <Waveform
        peaks={peaks}
        progress={progress}
        mine={mine}
        onSeek={(f) => { setStarted(true); keepPlaying(() => player.seekTo((total / 1000) * f)); }}
      />

      {/* До запуска — сколько сообщение длится, после — сколько уже прошло. */}
      <Text style={[s.duration, stuck && s.durationStuck, mine && { color: color.onPrimary }]} numberOfLines={1}>
        {stuck ? T('не загрузилось', 'failed', 'fallido') : formatDuration(started ? current : total || durationMs)}
      </Text>

      {started ? (
        <Animated.View style={{ opacity: rateIn, transform: [{ scale: rateIn }] }}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={T('Скорость воспроизведения', 'Playback speed', 'Velocidad de reproducción')}
            onPress={cycleRate}
            style={[s.rate, mine && s.rateMine]}
            hitSlop={6}
          >
            <Text style={[s.rateText, mine && { color: color.onPrimary }]}>
              {rate === 1 ? T('1×', '1×', '1×') : rate === 1.5 ? T('1,5×', '1.5×', '1,5×') : T('2×', '2×', '2×')}
            </Text>
          </Pressable>
        </Animated.View>
      ) : null}
    </View>
  );
}

// ======================================================================== запись

/**
 * ЗАПИСЬ УДЕРЖАНИЕМ — как в мессенджерах, к которым человек уже привык.
 *
 * Жест целиком:
 *   — прижал микрофон  → пошла запись;
 *   — отпустил         → запись ушла собеседнику, без промежуточного экрана;
 *   — потянул ВВЕРХ    → запись закрепилась, палец можно убрать и говорить дальше;
 *   — потянул ВЛЕВО    → отмена, ничего не отправляется.
 *
 * Что было раньше: тап «начать», тап «стоп», потом экран превью и ещё тап «отправить» — три
 * касания там, где привычка требует одного движения.
 *
 * Превью в обычном пути НЕ появляется — ни при отпускании, ни у закреплённой записи: «отправить»
 * там отправляет, а не показывает. Оно осталось на два случая, где послушать перед отправкой
 * действительно нужно: упёрлись в минутный предел и отправка не прошла. В обоих запись уже есть,
 * и терять её нельзя.
 *
 * Пороги в пунктах, а не в долях экрана: жест делается большим пальцем, и его ход одинаков на
 * телефоне любого размера. Отмена дальше закрепления (80 против 56) намеренно — промахнуться
 * в «отменить» должно быть труднее, чем в «закрепить».
 */
const LOCK_AT = -56;
const CANCEL_AT = -80;
/**
 * Насколько далеко жест утаскивает то, что за ним едет. Величины РАЗНЫЕ, и это не придирка:
 *   DRAG_TRAVEL — кнопка. Ей можно уехать далеко, вокруг неё пусто.
 *   HINT_TRAVEL — подсказка. Слева от неё стоит таймер, и на общем с кнопкой ходе она наезжала
 *                 прямо на него: две надписи одна поверх другой (снято 12 августа).
 *
 * Откуда 72. Замерено по кадру: «Отмена» стоит на 152,7 пункта, таймер кончается на 64 — значит
 * ход длиннее 79 их сталкивает; взято с запасом на более длинный перевод.
 *
 * ПОЧЕМУ ЭТОГО МАЛО и подсказку отмены не тащат вовсе. Строка подсказки центрируется, поэтому чем
 * она ШИРЕ, тем ЛЕВЕЕ начинается: «Отпусти — отмена» с корзиной начинается уже на ~105 пунктах, и
 * ей остаётся всего 31 пункт хода. Одного числа на обе надписи не бывает. Да и незачем: следовать
 * за пальцем — это приглашение тянуть дальше, а на пороге тянуть уже некуда, там сказано «отпусти».
 */
const DRAG_TRAVEL = -140;
const HINT_TRAVEL = -72;

/**
 * Кнопка микрофона и полоса записи поверх композера — одним компонентом.
 *
 * Почему вместе. Полоса перекрывает поле ввода целиком (так это и выглядит в мессенджерах), и
 * значит она должна лежать absolute внутри всего дока, а не внутри узкого слота кнопки: иначе на
 * Android касания за пределами слота просто не доходят до кнопок отмены и отправки. Компонент
 * возвращает ФРАГМЕНТ — полоса и слот становятся соседями внутри дока. Порядок важен: полоса
 * первая, поэтому кнопка рисуется поверх неё и может свободно вырастать за края слота.
 */
export function VoiceMessageControl({ voice }: { voice: VoiceMessage }) {
  const recording = voice.phase === 'recording';
  const busy = voice.phase !== 'idle';
  const [locked, setLocked] = useState(false);
  const [hint, setHint] = useState<'none' | 'lock' | 'cancel'>('none');

  // В обработчиках жеста нельзя читать состояние: они замыкаются на первое значение и остаются
  // с ним навсегда. Поэтому решение принимается по ссылкам, а состояние — только для показа.
  const lockedRef = useRef(false);
  const cancelRef = useRef(false);
  /** Жест выключен, когда запись закреплена или уже слушается: там работают обычные кнопки. */
  const gestureOff = useRef(false);
  gestureOff.current = locked || (busy && !recording);

  const grow = useRef(new Animated.Value(0)).current;      // кнопка выросла и покраснела
  const lvl = useRef(new Animated.Value(0)).current;       // громкость → ореол
  const dx = useRef(new Animated.Value(0)).current;        // палец влево
  const lift = useRef(new Animated.Value(0)).current;      // палец вверх → к замку
  const blink = useRef(new Animated.Value(1)).current;     // красная точка
  const arrow = useRef(new Animated.Value(0)).current;     // шеврон над замком
  const enter = useRef(new Animated.Value(0)).current;     // появление полосы

  const resetGesture = useCallback(() => {
    lockedRef.current = false;
    cancelRef.current = false;
    setLocked(false);
    setHint('none');
    dx.setValue(0);
    lift.setValue(0);
  }, [dx, lift]);

  // Обработчики жеста создаются ОДИН раз, а хук пересобирается на каждый кадр записи. Поэтому
  // они ходят к нему через ссылку: замыкание на первое значение оставило бы кнопку навсегда
  // подключённой к состоянию первого рендера.
  const voiceRef = useRef(voice);
  voiceRef.current = voice;

  const responder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => !gestureOff.current,
      onMoveShouldSetPanResponder: () => !gestureOff.current,
      onPanResponderGrant: () => {
        resetGesture();
        buzzStarted();
        voiceRef.current.start();
      },
      onPanResponderMove: (_e, g) => {
        if (lockedRef.current) return;              // закрепили — жест больше ничего не решает
        dx.setValue(Math.max(DRAG_TRAVEL, Math.min(0, g.dx)));
        lift.setValue(Math.max(0, Math.min(1, g.dy / LOCK_AT)));
        if (g.dx < CANCEL_AT) {
          if (!cancelRef.current) { cancelRef.current = true; setHint('cancel'); buzzEdge(); }
          return;
        }
        if (cancelRef.current) { cancelRef.current = false; setHint('none'); }
        if (g.dy < LOCK_AT) {
          lockedRef.current = true;
          setLocked(true);
          setHint('none');
          dx.setValue(0);
          lift.setValue(1);
          buzzLocked();
          return;
        }
        setHint(g.dy < LOCK_AT / 2 ? 'lock' : 'none');
      },
      onPanResponderRelease: () => {
        if (lockedRef.current) return;              // палец убран, запись продолжается
        if (cancelRef.current) { buzzLost(); voiceRef.current.cancel(); resetGesture(); return; }
        voiceRef.current.stopAndSend();
        resetGesture();
      },
      // Жест перехватила прокрутка или звонок — считаем это отменой, а не отправкой: отправлять
      // то, чего человек не заканчивал, нельзя.
      onPanResponderTerminate: () => {
        if (lockedRef.current) return;
        buzzLost();
        voiceRef.current.cancel();
        resetGesture();
      },
    })
  ).current;

  useEffect(() => {
    Animated.spring(grow, { toValue: recording ? 1 : 0, friction: 6, tension: 150, useNativeDriver: true }).start();
  }, [grow, recording]);

  // Ореол следует за голосом. Догоняем громкость за один шаг опроса — быстрее выглядит дрожью,
  // медленнее отстаёт от речи.
  useEffect(() => {
    Animated.timing(lvl, {
      toValue: recording ? voice.level : 0, duration: 110, easing: Easing.out(Easing.quad), useNativeDriver: true,
    }).start();
  }, [lvl, recording, voice.level]);

  useEffect(() => {
    if (!recording) { blink.setValue(1); return; }
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(blink, { toValue: 0.2, duration: 520, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
      Animated.timing(blink, { toValue: 1, duration: 520, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
    ]));
    loop.start();
    return () => loop.stop();
  }, [blink, recording]);

  useEffect(() => {
    if (!recording || locked) { arrow.setValue(0); return; }
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(arrow, { toValue: 1, duration: 720, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
      Animated.timing(arrow, { toValue: 0, duration: 720, easing: Easing.inOut(Easing.quad), useNativeDriver: true }),
    ]));
    loop.start();
    return () => loop.stop();
  }, [arrow, locked, recording]);

  // Появление полосы. Исчезновение доигрывать некому: строка размонтируется вместе с записью,
  // и держать её ради ста пятидесяти миллисекунд значит держать состояние, которое врёт.
  useEffect(() => {
    Animated.timing(enter, {
      toValue: busy ? 1 : 0, duration: busy ? 170 : 120,
      easing: busy ? Easing.out(Easing.cubic) : Easing.in(Easing.cubic), useNativeDriver: true,
    }).start();
  }, [busy, enter]);

  const haloScale = lvl.interpolate({ inputRange: [0, 1], outputRange: [1.1, 2.7] });
  const haloOpacity = Animated.multiply(grow, lvl.interpolate({ inputRange: [0, 1], outputRange: [0.08, 0.3] }));
  const ringScale = lvl.interpolate({ inputRange: [0, 1], outputRange: [1.0, 1.85] });
  const ringOpacity = Animated.multiply(grow, lvl.interpolate({ inputRange: [0, 1], outputRange: [0.14, 0.4] }));
  const micScale = grow.interpolate({ inputRange: [0, 1], outputRange: [1, 1.28] });
  const hintX = dx.interpolate({ inputRange: [HINT_TRAVEL, 0], outputRange: [HINT_TRAVEL, 0], extrapolate: 'clamp' });
  const barSlide = enter.interpolate({ inputRange: [0, 1], outputRange: [10, 0] });

  const cancelling = hint === 'cancel';
  const sendNow = () => { voice.stopAndSend(); resetGesture(); };
  const dropIt = () => { buzzLost(); voice.cancel(); resetGesture(); };

  const ready = voice.phase === 'preview' || voice.phase === 'uploading';

  /**
   * Полоса записи — ОДНА строка, которая сама растёт, а не накладка поверх композера.
   *
   * Так было не всегда: сперва она лежала absolute поверх дока, чтобы перекрыть поле ввода
   * целиком. На экране разговора это работало, а на экранах Бадди и группы — нет: там кнопка
   * стоит ВНУТРИ поля ввода и при записи заменяет его собой. Absolute отмеряется от родителя,
   * родителем оказывалось поле, и микрофон уезжал к левому краю (снято 12 августа).
   *
   * Самодостаточная строка не зависит от того, куда её поставили: кнопка всегда справа, всё
   * остальное набегает слева. Экран решает лишь одно — отдать ей всю ширину на время записи.
   */
  return (
    <View style={[s.hold, busy && s.holdBusy]} {...responder.panHandlers}>
      {busy ? (
        <Animated.View style={[s.barLeft, { opacity: enter, transform: [{ translateY: barSlide }] }]}>
          {ready ? (
            <>
              <Pressable accessibilityRole="button" accessibilityLabel={T('Удалить запись', 'Delete recording', 'Borrar grabación')}
                         onPress={dropIt} disabled={voice.disabled} style={s.barAction} hitSlop={6}>
                <IconTrash size={19} c={color.muted} />
              </Pressable>
              <AudioPlay source={voice.uri} durationMs={voice.durationMillis} peaks={voice.peaks} grow />
            </>
          ) : locked ? (
            <>
              <Pressable accessibilityRole="button" accessibilityLabel={T('Отменить запись', 'Cancel recording', 'Cancela la grabación')}
                         onPress={dropIt} style={s.barAction} hitSlop={6}>
                <IconTrash size={19} c={color.muted} />
              </Pressable>
              <Animated.View style={[s.dot, { opacity: blink }]} />
              <Text style={s.timer}>{formatDuration(voice.durationMillis)}</Text>
              <LiveWave levels={voice.liveBars} />
            </>
          ) : (
            <>
              <Animated.View style={[s.dot, { opacity: blink }]} />
              <Text style={s.timer}>{formatDuration(voice.durationMillis)}</Text>
              <Animated.View style={[s.hintRow, { transform: [{ translateX: cancelling ? 0 : hintX }] }]}>
                {cancelling ? <IconTrash size={15} c={color.primary} /> : <Text style={s.hintArrow}>◀</Text>}
                <Text style={[s.hint, cancelling && s.hintCancel]} numberOfLines={1}>
                  {cancelling
                    ? T('Отпусти — отмена', 'Release to cancel', 'Suelta para cancelar')
                    : T('Отмена', 'Slide to cancel', 'Desliza para cancelar')}
                </Text>
              </Animated.View>
            </>
          )}
        </Animated.View>
      ) : null}

      <View style={s.micSlot}>
        {locked || ready ? (
          <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send', 'Enviar')}
                     onPress={locked ? sendNow : voice.send} disabled={voice.disabled}
                     style={[s.send, voice.disabled && { opacity: 0.55 }]}>
            {voice.phase === 'uploading' ? <ActivityIndicator size="small" color={color.onPrimary} /> : <IconSend size={17} />}
          </Pressable>
        ) : (
          <>
            {/* Два ореола с разным ходом: ближний плотнее, дальний шире — так дыхание читается.
                Оба едут за пальцем вместе с кнопкой, иначе она уходит влево, а свечение остаётся. */}
            <Animated.View style={[s.halo, { opacity: haloOpacity, transform: [{ translateX: dx }, { scale: haloScale }] }]} pointerEvents="none" />
            <Animated.View style={[s.halo, { opacity: ringOpacity, transform: [{ translateX: dx }, { scale: ringScale }] }]} pointerEvents="none" />
            <Animated.View
              accessibilityRole="button"
              accessibilityLabel={T('Удерживай, чтобы записать голосовое', 'Hold to record a voice message', 'Pulsa y sostén para grabar un mensaje de voz')}
              style={[s.micDisc, {
                // К порогу отмены кнопка гаснет: видно, что отпускать уже нечего.
                opacity: dx.interpolate({ inputRange: [CANCEL_AT, CANCEL_AT / 2], outputRange: [0.25, 1], extrapolate: 'clamp' }),
                transform: [{ translateX: dx }, { scale: micScale }],
              }]}
            >
              <Animated.View style={[s.micFill, { opacity: grow }]} pointerEvents="none" />
              {/* Серый микрофон уступает белому — цвет обводки в SVG не анимируется, перетекают слои. */}
              <Animated.View style={[s.micIcon, { opacity: grow.interpolate({ inputRange: [0, 1], outputRange: [1, 0] }) }]}>
                <IconMic />
              </Animated.View>
              <Animated.View style={[s.micIcon, { opacity: grow }]}>
                <IconMic c={color.onPrimary} />
              </Animated.View>
            </Animated.View>
            {recording ? (
              <Animated.View
                style={[s.lockPill, {
                  opacity: enter,
                  transform: [{ translateY: lift.interpolate({ inputRange: [0, 1], outputRange: [0, -12] }) }],
                }]}
                pointerEvents="none"
              >
                <Animated.View style={[s.lockFill, { opacity: lift }]} />
                <Animated.View style={{
                  opacity: Animated.multiply(arrow, lift.interpolate({ inputRange: [0, 1], outputRange: [1, 0] })),
                  transform: [{ translateY: arrow.interpolate({ inputRange: [0, 1], outputRange: [2, -3] }) }],
                }}>
                  <IconChevronUp size={11} c={color.muted} />
                </Animated.View>
                <IconLock size={14} c={color.muted} />
              </Animated.View>
            ) : null}
          </>
        )}
      </View>
    </View>
  );
}

/** Живая полоска у закреплённой записи: последние секунды голоса, новое приходит справа. */
function LiveWave({ levels }: { levels: number[] }) {
  return (
    <View style={s.liveWave} pointerEvents="none">
      {Array.from({ length: LIVE_BARS }).map((_, i) => {
        const v = levels[levels.length - LIVE_BARS + i] ?? 0;
        return <View key={i} style={[s.liveBar, { height: 3 + Math.round(v * 15) }]} />;
      })}
    </View>
  );
}

// ======================================================================== пузырь в ленте

export function VoiceBubble({ voice, mine = false }: { voice: VoicePayload; mine?: boolean }) {
  const [showTranscript, setShowTranscript] = useState(false);
  const peaks = useMemo(() => peaksFor(String(voice.id || voice.url || '')), [voice.id, voice.url]);
  return (
    <View style={[s.bubble, mine && s.bubbleMine]}>
      <AudioPlay source={mediaUrl(voice.url)} durationMs={voice.duration_ms} peaks={peaks} mine={mine} />
      <Pressable accessibilityRole="button" onPress={() => setShowTranscript((v) => !v)} hitSlop={4}>
        <Text style={[s.transcriptLink, mine && { color: color.onPrimary }]}>
          {showTranscript ? T('Скрыть текст', 'Hide transcript', 'Ocultar transcripción') : T('Показать текст', 'Show transcript', 'Mostrar transcripción')}
        </Text>
      </Pressable>
      {showTranscript ? <Transcript text={voice.transcript} mine={mine} /> : null}
    </View>
  );
}

/** Текст не выскакивает, а проявляется: расшифровка появляется под уже прочитанной строкой. */
function Transcript({ text, mine }: { text: string; mine: boolean }) {
  const a = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(a, { toValue: 1, duration: 190, easing: Easing.out(Easing.quad), useNativeDriver: true }).start();
  }, [a]);
  return (
    <Animated.Text
      style={[s.transcript, mine && { color: color.onPrimary }, {
        opacity: a,
        transform: [{ translateY: a.interpolate({ inputRange: [0, 1], outputRange: [-5, 0] }) }],
      }]}
    >
      {text}
    </Animated.Text>
  );
}

// ===== вид

const s = StyleSheet.create({
  iconButton: { minWidth: 28, height: 34, alignItems: 'center', justifyContent: 'center' },
  recording: { minWidth: 76, flexDirection: 'row', gap: 7 },
  stop: { width: 11, height: 11, borderRadius: 2, backgroundColor: color.primary },
  timer: { width: 46, fontSize: 12, color: color.primary, fontVariant: ['tabular-nums'] },
  send: { width: 36, height: 36, borderRadius: 18, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },

  // --- проигрыватель
  playRow: { minWidth: 172, flexDirection: 'row', alignItems: 'center', gap: 9 },
  /** Только в композере: занять оставшуюся ШИРИНУ строки. В пузыре это растянуло бы высоту. */
  playRowGrow: { flex: 1 },
  playButton: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center' },
  playInner: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center' },
  playIcon: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center' },
  pause: { flexDirection: 'row', gap: 3 },
  pauseBar: { width: 3, height: 14, borderRadius: 1 },
  wave: { flex: 1, height: 24, justifyContent: 'center' },
  waveRow: { height: 24, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  waveMask: { position: 'absolute', left: 0, top: 0, height: 24, overflow: 'hidden' },
  waveBar: { width: 2, borderRadius: 1 },
  duration: { minWidth: 38, fontSize: 11, color: color.muted, fontVariant: ['tabular-nums'] },
  /** Место отсчёта занимает причина молчания: строка длиннее, цифровой моноширины ей не нужно. */
  durationStuck: { fontSize: 10, color: color.primary, fontVariant: undefined },
  rate: {
    paddingHorizontal: 6, height: 20, borderRadius: 10, alignItems: 'center', justifyContent: 'center',
    backgroundColor: color.neutral100,
  },
  rateMine: { backgroundColor: color.onCoverSoft },
  rateText: { fontSize: 10, fontWeight: '700', color: color.muted, fontVariant: ['tabular-nums'] },

  // --- кнопка удержания
  /**
   * В простое — тот же размер, что у прежнего микрофона: композер не должен прыгать.
   * В записи — вся доступная ширина, и кнопка прижата ВПРАВО. Прижата явно, а не по остаточному
   * принципу: строку ставят в три разных композера, и в двух из них она оказывается единственным
   * содержимым поля ввода — там без `flex-end` кнопка ушла бы к левому краю.
   */
  hold: { minWidth: 28, minHeight: 34, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 8 },
  holdBusy: { flex: 1, minHeight: 36 },
  /** Слева от кнопки: отсчёт, подсказка, волна — смотря что сейчас происходит. */
  barLeft: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8 },
  /** Гнездо кнопки: ореолы и замок кладутся относительно НЕГО, а не всей строки. */
  micSlot: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  halo: { position: 'absolute', width: 34, height: 34, borderRadius: 17, backgroundColor: color.primary },
  micDisc: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },
  micFill: { ...StyleSheet.absoluteFill, borderRadius: 17, backgroundColor: color.primary },
  micIcon: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center' },
  lockPill: {
    position: 'absolute', bottom: 44, width: 30, paddingVertical: 6, borderRadius: 15,
    alignItems: 'center', gap: 3, backgroundColor: color.card, borderWidth: 1, borderColor: color.border,
  },
  lockFill: { ...StyleSheet.absoluteFill, borderRadius: 15, backgroundColor: color.neutral100 },

  // --- полоса записи поверх композера
  barAction: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: color.primary },
  hintRow: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5 },
  hintArrow: { fontSize: 10, color: color.neutral400 },
  hint: { fontSize: 12, color: color.muted, flexShrink: 1 },
  hintCancel: { color: color.primary, fontWeight: '600' },
  liveWave: { flex: 1, height: 20, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 2 },
  liveBar: { width: 2, borderRadius: 1, backgroundColor: color.neutral300 },

  // --- пузырь
  bubble: { minWidth: 230, maxWidth: 286, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 16, backgroundColor: color.neutral100 },
  bubbleMine: { backgroundColor: color.primary },
  transcriptLink: { fontSize: 12, color: color.primary, marginTop: 4, fontWeight: '600' },
  transcript: { fontSize: 13, lineHeight: 18, color: color.fg, marginTop: 6 },
});
