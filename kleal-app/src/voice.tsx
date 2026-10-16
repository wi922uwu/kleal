import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator, Alert, PanResponder, Platform, Pressable, StyleSheet, Text, View,
} from 'react-native';
import Animated, {
  Easing, cancelAnimation, interpolate, useAnimatedStyle, useSharedValue,
  withRepeat, withSequence, withSpring, withTiming, Extrapolation,
} from 'react-native-reanimated';
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

/**
 * ГОЛОСОВЫЕ — КАК В МЕССЕНДЖЕРАХ, К КОТОРЫМ ЧЕЛОВЕК ПРИВЫК.
 *
 * Переработка 23.09.2026. Что было: вся анимация шла через старый `Animated` и `setValue` на
 * каждое движение пальца — то есть через JS-поток, который в момент записи занят ещё и опросом
 * микрофона десять раз в секунду. Отсюда дрожь ореола, отставание кнопки от пальца и рывок при
 * отпускании. Что стало: каждое движение живёт в `SharedValue` и считается на стороне UI —
 * жест только меняет числа, кадры рисует Reanimated. Пружины вместо линейных переходов: кнопка
 * «дышит» и возвращается на место с тем же характером, что в Телеграме.
 *
 * Второе — воспроизведение. Чужое голосовое раньше скачивалось ЦЕЛИКОМ и лишь потом играло:
 * сервер не умел частичных запросов. С 23.09.2026 умеет (`/api/agent/voice/*` отдаёт 206 с
 * `Range`), и проигрыватель берёт файл потоком — звук идёт, не дожидаясь конца. Скачивание
 * осталось запасным путём на случай, если поток не пошёл за четыре секунды.
 *
 * Третье — расшифровка стала необязательной там, где сообщение и есть звук (переписка, группа):
 * если под с моделью не ответил, голосовое всё равно уходит. В разговоре с Бадди текст обязателен —
 * агент читает буквы, а не слушает, — там правило прежнее.
 */

type DictationPhase = 'idle' | 'recording' | 'transcribing';
type MessagePhase = 'idle' | 'recording' | 'preview' | 'uploading';

const MAX_DURATION_MS = 60000;
/** Короче этого — не сообщение, а случайное касание микрофона. */
const MIN_DURATION_MS = 700;
const WAVE_BARS = 34;
const LIVE_BARS = 24;

// ---- тактильный отклик: пять разных, каждый несёт смысл (см. историю в предыдущей версии)
const canBuzz = Platform.OS !== 'web';
const buzz = (style: Haptics.ImpactFeedbackStyle) => { if (canBuzz) Haptics.impactAsync(style).catch(() => {}); };
const buzzStarted = () => buzz(Haptics.ImpactFeedbackStyle.Light);
const buzzEdge = () => buzz(Haptics.ImpactFeedbackStyle.Light);
const buzzLocked = () => buzz(Haptics.ImpactFeedbackStyle.Medium);
const buzzSent = () => buzz(Haptics.ImpactFeedbackStyle.Light);
const buzzLost = () => { if (canBuzz) Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {}); };
const buzzTick = () => { if (canBuzz) Haptics.selectionAsync().catch(() => {}); };

/** Уровень микрофона в дБ полной шкалы → 0…1; речь живёт в верхней трети, окно −50…0. */
const LEVEL_FLOOR_DB = -50;
const levelOf = (db?: number | null) => {
  if (typeof db !== 'number' || !isFinite(db)) return 0;
  return Math.max(0, Math.min(1, (db - LEVEL_FLOOR_DB) / -LEVEL_FLOOR_DB));
};

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

// ---- огибающая: настоящая у своей записи, устойчивая псевдоформа у остальных
const PEAKS = new Map<string, number[]>();

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
  const top = Math.max(...out);
  return out.map((v) => (top > 0 ? Math.max(0.1, v / top) : 0.1));
};

export const pseudoPeaks = (seed: string, n = WAVE_BARS) => {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) { h ^= seed.charCodeAt(i); h = Math.imul(h, 16777619); }
  const phase = ((h >>> 0) % 628) / 100;
  const rand = () => { h ^= h << 13; h ^= h >>> 17; h ^= h << 5; return ((h >>> 0) % 1000) / 1000; };
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const syllable = 0.55 + 0.45 * Math.sin(i * 0.9 + phase);
    out.push(Math.max(0.14, Math.min(1, syllable * (0.5 + 0.5 * rand()))));
  }
  return out;
};

const peaksFor = (id: string) => PEAKS.get(id) || pseudoPeaks(id || 'voice');

export const appendTranscript = (draft: string, transcript: string) =>
  draft.trim() ? `${draft.trimEnd()} ${transcript}` : transcript;

// ======================================================================== надиктовка в поле

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

// ======================================================================== голосовое сообщение

export type VoiceMessageOptions = {
  /**
   * Нужна ли расшифровка, чтобы отправить. В разговоре с Бадди — да: агент читает текст. Между
   * людьми — нет: сообщение и есть звук, а текст лишь подсказка; терять голосовое из-за молчания
   * модели нельзя.
   */
  requireTranscript?: boolean;
};

export function useVoiceMessage(
  onSend: (voice: VoicePayload) => void | Promise<void>,
  disabled = false,
  options: VoiceMessageOptions = {},
) {
  const requireTranscript = options.requireTranscript !== false;
  const recorder = useAudioRecorder(RECORDING_OPTIONS);
  const recorderState = useAudioRecorderState(recorder, 100);
  const [phase, setPhase] = useState<MessagePhase>('idle');
  const [uri, setUri] = useState('');
  const [durationMillis, setDurationMillis] = useState(0);
  const [peaks, setPeaks] = useState<number[]>([]);
  const stopping = useRef(false);
  const samples = useRef<number[]>([]);

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
        return Alert.alert(
          T('Нет доступа к микрофону', 'Microphone access is disabled', 'El acceso al micrófono está deshabilitado'),
          T('Разрешите доступ к микрофону в настройках устройства.', 'Allow microphone access in device settings.', 'Permite el acceso al micrófono en los ajustes del dispositivo.'),
        );
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

  /** Отправка. `from` — чтобы слать СРАЗУ после остановки, не дожидаясь состояния (см. историю). */
  const upload = useCallback(async (from?: { uri: string; ms: number; peaks: number[] }) => {
    const src = from?.uri || uri;
    const ms = from?.ms ?? durationMillis;
    const bars = from?.peaks || peaks;
    if (!src) return;
    setPhase('uploading');
    try {
      const result = await speech.uploadVoice(await audioForm(src), ms);
      const transcript = String(result?.transcript || result?.text || '').trim();
      if (!result?.id || !result?.url) throw new Error('INVALID_VOICE_RESPONSE');
      if (requireTranscript && !transcript) throw new Error('NO_SPEECH');
      if (bars.length) PEAKS.set(String(result.id), bars);
      await onSend({
        id: String(result.id), url: String(result.url), duration_ms: Number(result.duration_ms || ms),
        transcript, mime_type: String(result.mime_type || 'audio/mp4'), language: result.language,
      });
      buzzSent();
      reset();
    } catch (error) {
      // Возврат в превью, а не в пустоту: запись цела, её можно послушать и отправить снова.
      setUri(src);
      setDurationMillis(ms);
      setPeaks(bars);
      setPhase('preview');
      const code = String((error as any)?.body?.error || (error as any)?.message || '');
      Alert.alert(
        T('Не удалось отправить голосовое', 'Could not send voice message', 'No se pudo enviar el mensaje de voz'),
        code === 'NO_SPEECH'
          ? T('Речь не распознана. Скажите чуть громче и ближе к телефону.', 'No speech was recognized. Speak a little louder, closer to the phone.', 'No se reconoció la voz. Habla un poco más alto y cerca del teléfono.')
          : T('Проверьте соединение и повторите отправку.', 'Check your connection and try sending again.', 'Comprueba tu conexión y vuelve a enviar.'),
      );
    }
  }, [durationMillis, onSend, peaks, requireTranscript, reset, uri]);

  /** Отпустил палец — записать и отправить одним движением; слишком короткое — выбросить. */
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
      if (ms < MIN_DURATION_MS) { buzzLost(); reset(); return; }
      await upload({ uri: src, ms, peaks: bars });
    } catch {
      fail(T('Запись не сохранена', 'Recording was not saved', 'La grabación no se guardó'), T('Попробуйте записать ещё раз.', 'Try recording again.', 'Inténtalo de nuevo.'));
    } finally {
      stopping.current = false;
    }
  }, [fail, phase, recorder, recorderState.durationMillis, reset, upload]);

  const send = useCallback(async () => {
    if (phase !== 'preview' || !uri) return;
    await upload({ uri, ms: durationMillis, peaks });
  }, [durationMillis, peaks, phase, upload, uri]);

  useEffect(() => {
    if (phase === 'recording' && recorderState.isRecording && recorderState.durationMillis >= MAX_DURATION_MS) stop();
  }, [phase, recorderState.isRecording, recorderState.durationMillis, stop]);

  return {
    phase, uri, peaks,
    durationMillis: phase === 'recording' ? recorderState.durationMillis : durationMillis,
    level: phase === 'recording' ? levelOf(recorderState.metering) : 0,
    liveBars: samples.current.slice(-LIVE_BARS),
    start, stop, stopAndSend, cancel: reset, send, disabled: disabled || phase === 'uploading',
  };
}

export type VoiceMessage = ReturnType<typeof useVoiceMessage>;

// ======================================================================== проигрывание

/**
 * Столбики вместо полоски: два одинаковых ряда, нижний приглушённый, верхний цветной в окне, которое
 * растёт по мере проигрывания. Окно — две встречные трансформации на стороне UI: столбики стоят,
 * ползёт только заливка. Пока палец ведёт, заливка слушается его, а не плеера.
 */
function Waveform({
  peaks, progress, mine, onSeek, scrubbing,
}: {
  peaks: number[]; progress: number; mine: boolean; onSeek: (fraction: number) => void;
  scrubbing?: (on: boolean) => void;
}) {
  const [width, setWidth] = useState(0);
  const p = useSharedValue(0);
  const w = useSharedValue(0);
  const hold = useRef(false);
  const widthRef = useRef(0);
  widthRef.current = width;
  const seekRef = useRef(onSeek);
  seekRef.current = onSeek;

  useEffect(() => { w.value = width; }, [w, width]);

  useEffect(() => {
    if (hold.current) return;
    // Плеер отчитывается раз в 200 мс; догоняем ровно за этот шаг — движение непрерывное.
    p.value = withTiming(progress, { duration: 220, easing: Easing.linear });
  }, [p, progress]);

  const responder = useRef(PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderGrant: (e) => { hold.current = true; scrubbing?.(true); grab(e.nativeEvent.locationX); },
    onPanResponderMove: (e) => grab(e.nativeEvent.locationX),
    onPanResponderRelease: () => release(),
    onPanResponderTerminate: () => release(),
  })).current;

  function grab(x: number) {
    if (widthRef.current <= 0) return;
    const f = Math.max(0, Math.min(1, x / widthRef.current));
    p.value = f;
    seekRef.current(f);
  }
  function release() {
    // Четверть секунды держим своё значение — до первого отчёта плеера с новой позиции.
    setTimeout(() => { hold.current = false; scrubbing?.(false); }, 260);
  }

  const maskStyle = useAnimatedStyle(() => ({ transform: [{ translateX: (p.value - 1) * w.value }] }));
  const innerStyle = useAnimatedStyle(() => ({ transform: [{ translateX: (1 - p.value) * w.value }] }));
  const bars = peaks.length ? peaks : pseudoPeaks('empty');

  const row = (tint: string) => (
    <View style={[s.waveRow, width > 0 && { width }]} pointerEvents="none">
      {bars.map((v, i) => (
        <View key={i} style={[s.waveBar, { height: 3 + Math.round(v * 17), backgroundColor: tint }]} />
      ))}
    </View>
  );

  return (
    <View style={s.wave} onLayout={(e) => setWidth(e.nativeEvent.layout.width)} {...responder.panHandlers}>
      {row(mine ? color.onCoverSoft : color.neutral300)}
      <Animated.View style={[s.waveMask, { width }, maskStyle]} pointerEvents="none">
        <Animated.View style={[{ width }, innerStyle]}>
          {row(mine ? color.onPrimary : color.primary)}
        </Animated.View>
      </Animated.View>
    </View>
  );
}

/**
 * Проигрыватель — в пузыре и в композере перед отправкой. `grow` разделяет два случая: в строке
 * композера `flex: 1` значит «займи ширину», в колонке пузыря — «займи высоту» (см. историю).
 *
 * ПОТОК, А НЕ СКАЧИВАНИЕ. Сервер с 23.09.2026 отдаёт голосовые частями (206 + Range), и iOS
 * открывает удалённый файл сразу. Если за четыре секунды после запуска звук так и не пошёл —
 * скачиваем целиком, как раньше: медленная сеть не должна выглядеть как сломанная кнопка.
 */
function AudioPlay({
  source, durationMs, peaks, mine = false, grow = false,
}: { source: string; durationMs: number; peaks: number[]; mine?: boolean; grow?: boolean }) {
  const remote = /^https?:/i.test(source);
  const [fallback, setFallback] = useState<string | null>(null);
  const player = useAudioPlayer(fallback || source, { updateInterval: 200 });
  const status = useAudioPlayerStatus(player);
  const [rate, setRate] = useState(1);
  const [started, setStarted] = useState(false);
  const [stuck, setStuck] = useState(false);
  const total = status.duration > 0 ? status.duration * 1000 : durationMs;
  const current = Math.min(total, status.currentTime * 1000);
  const progress = total > 0 ? Math.max(0, Math.min(1, current / total)) : 0;

  const press = useSharedValue(1);
  const playing = useSharedValue(0);
  const rateIn = useSharedValue(0);

  useEffect(() => { if (status.didJustFinish) player.seekTo(0); }, [player, status.didJustFinish]);
  useEffect(() => { playing.value = withTiming(status.playing ? 1 : 0, { duration: 140 }); }, [playing, status.playing]);
  useEffect(() => { if (started) rateIn.value = withSpring(1, { damping: 14, stiffness: 220 }); }, [rateIn, started]);

  // Нажал — и тишина. Четыре секунды ждём поток; не пошёл — качаем целиком и говорим об этом.
  useEffect(() => {
    if (!started || status.isLoaded) { setStuck(false); return; }
    const t = setTimeout(() => {
      if (remote && !fallback) {
        Asset.fromURI(source).downloadAsync()
          .then((a) => setFallback(a.localUri || a.uri))
          .catch(() => setStuck(true));
      } else {
        setStuck(true);
      }
    }, 4000);
    return () => clearTimeout(t);
  }, [fallback, remote, source, started, status.isLoaded]);

  // Скачанный запасной файл подхватываем и играем сразу — человек уже нажал.
  useEffect(() => {
    if (fallback && started && !status.playing) player.play();
  }, [fallback]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = async () => {
    if (status.playing) { player.pause(); return; }
    setStarted(true);
    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => {});
    player.play();
  };

  /** Перемотка и темп в expo-audio глушат проигрывание — играем дальше сами (см. историю). */
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

  const pressStyle = useAnimatedStyle(() => ({ transform: [{ scale: press.value }] }));
  const playIconStyle = useAnimatedStyle(() => ({ opacity: 1 - playing.value }));
  const pauseIconStyle = useAnimatedStyle(() => ({ opacity: playing.value }));
  const rateStyle = useAnimatedStyle(() => ({ opacity: rateIn.value, transform: [{ scale: rateIn.value }] }));

  return (
    <View style={[s.playRow, grow && s.playRowGrow]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={status.playing ? T('Пауза', 'Pause', 'Pausa') : T('Воспроизвести', 'Play', 'Reproducir')}
        onPress={toggle}
        onPressIn={() => { press.value = withSpring(0.86, { damping: 12, stiffness: 320 }); }}
        onPressOut={() => { press.value = withSpring(1, { damping: 10, stiffness: 260 }); }}
        style={[s.playButton, mine ? s.playButtonMine : s.playButtonTheirs]}
        hitSlop={6}
      >
        <Animated.View style={[s.playInner, pressStyle]}>
          <Animated.View style={[s.playIcon, playIconStyle]}>
            <IconPlay size={18} c={mine ? color.primary : color.onPrimary} />
          </Animated.View>
          <Animated.View style={[s.playIcon, pauseIconStyle]}>
            <View style={s.pause}>
              <View style={[s.pauseBar, { backgroundColor: mine ? color.primary : color.onPrimary }]} />
              <View style={[s.pauseBar, { backgroundColor: mine ? color.primary : color.onPrimary }]} />
            </View>
          </Animated.View>
        </Animated.View>
      </Pressable>

      <View style={s.playBody}>
        <Waveform
          peaks={peaks}
          progress={progress}
          mine={mine}
          onSeek={(f) => { setStarted(true); keepPlaying(() => player.seekTo((total / 1000) * f)); }}
        />
        <View style={s.playMeta}>
          <Text style={[s.duration, stuck && s.durationStuck, mine && { color: color.onPrimary }]} numberOfLines={1}>
            {stuck ? T('не загрузилось', 'failed', 'fallido') : formatDuration(started ? current : total || durationMs)}
          </Text>
          {started ? (
            <Animated.View style={rateStyle}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={T('Скорость воспроизведения', 'Playback speed', 'Velocidad de reproducción')}
                onPress={cycleRate}
                style={[s.rate, mine && s.rateMine]}
                hitSlop={6}
              >
                <Text style={[s.rateText, mine && { color: color.onPrimary }]}>
                  {rate === 1 ? '1×' : rate === 1.5 ? T('1,5×', '1.5×', '1,5×') : '2×'}
                </Text>
              </Pressable>
            </Animated.View>
          ) : null}
        </View>
      </View>
    </View>
  );
}

// ======================================================================== запись удержанием

/**
 * Жест целиком: прижал — запись; отпустил — ушло; вверх — закрепил; влево — отмена.
 * Пороги в пунктах: жест делается большим пальцем и одинаков на любом экране. Отмена дальше
 * закрепления намеренно — промахнуться в «отменить» должно быть труднее.
 */
const LOCK_AT = -56;
const CANCEL_AT = -84;
const DRAG_TRAVEL = -150;
const HINT_TRAVEL = -72;

const SPRING_SOFT = { damping: 16, stiffness: 180 };
const SPRING_SNAP = { damping: 14, stiffness: 260 };

export function VoiceMessageControl({ voice }: { voice: VoiceMessage }) {
  const recording = voice.phase === 'recording';
  const busy = voice.phase !== 'idle';
  const [locked, setLocked] = useState(false);
  const [hint, setHint] = useState<'none' | 'lock' | 'cancel'>('none');

  // Решение принимается по ссылкам (обработчики жеста замыкаются на первый рендер), а состояние —
  // только для того, что нужно ПЕРЕРИСОВАТЬ (замок, текст подсказки). Всё движение — в shared values.
  const lockedRef = useRef(false);
  const cancelRef = useRef(false);
  const gestureOff = useRef(false);
  gestureOff.current = locked || (busy && !recording);

  const grow = useSharedValue(0);     // кнопка выросла и покраснела
  const lvl = useSharedValue(0);      // громкость → ореол
  const dx = useSharedValue(0);       // палец влево
  const lift = useSharedValue(0);     // палец вверх → к замку
  const blink = useSharedValue(1);    // красная точка
  const arrow = useSharedValue(0);    // шеврон над замком
  const enter = useSharedValue(0);    // появление полосы
  const cancelHint = useSharedValue(0); // подсказка «отпусти — отмена»
  const sendPop = useSharedValue(0);  // кнопка «отправить» выпрыгивает

  const resetGesture = useCallback(() => {
    lockedRef.current = false;
    cancelRef.current = false;
    setLocked(false);
    setHint('none');
    dx.value = withSpring(0, SPRING_SNAP);
    lift.value = withSpring(0, SPRING_SOFT);
    cancelHint.value = withTiming(0, { duration: 120 });
  }, [cancelHint, dx, lift]);

  const voiceRef = useRef(voice);
  voiceRef.current = voice;

  const responder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => !gestureOff.current,
      onMoveShouldSetPanResponder: () => !gestureOff.current,
      onPanResponderGrant: () => {
        lockedRef.current = false;
        cancelRef.current = false;
        dx.value = 0;
        lift.value = 0;
        cancelHint.value = 0;
        buzzStarted();
        voiceRef.current.start();
      },
      onPanResponderMove: (_e, g) => {
        if (lockedRef.current) return;
        // Сопротивление за порогом: дальше тянуть можно, но всё труднее — как резинка.
        const x = Math.min(0, g.dx);
        dx.value = x > CANCEL_AT ? x : CANCEL_AT + (x - CANCEL_AT) * 0.35;
        lift.value = Math.max(0, Math.min(1, g.dy / LOCK_AT));
        if (g.dx < CANCEL_AT) {
          if (!cancelRef.current) { cancelRef.current = true; setHint('cancel'); cancelHint.value = withTiming(1, { duration: 120 }); buzzEdge(); }
          return;
        }
        if (cancelRef.current) { cancelRef.current = false; setHint('none'); cancelHint.value = withTiming(0, { duration: 120 }); }
        if (g.dy < LOCK_AT) {
          lockedRef.current = true;
          setLocked(true);
          setHint('none');
          dx.value = withSpring(0, SPRING_SNAP);
          lift.value = withSpring(1, SPRING_SNAP);
          sendPop.value = 0;
          sendPop.value = withSpring(1, { damping: 11, stiffness: 300 });
          buzzLocked();
          return;
        }
        setHint(g.dy < LOCK_AT / 2 ? 'lock' : 'none');
      },
      onPanResponderRelease: () => {
        if (lockedRef.current) return;
        if (cancelRef.current) { buzzLost(); voiceRef.current.cancel(); resetGesture(); return; }
        voiceRef.current.stopAndSend();
        resetGesture();
      },
      onPanResponderTerminate: () => {
        if (lockedRef.current) return;
        buzzLost();
        voiceRef.current.cancel();
        resetGesture();
      },
    })
  ).current;

  useEffect(() => { grow.value = withSpring(recording ? 1 : 0, { damping: 13, stiffness: 240 }); }, [grow, recording]);
  useEffect(() => { lvl.value = withTiming(recording ? voice.level : 0, { duration: 110, easing: Easing.out(Easing.quad) }); }, [lvl, recording, voice.level]);
  useEffect(() => {
    if (!recording) { cancelAnimation(blink); blink.value = 1; return; }
    blink.value = withRepeat(withSequence(
      withTiming(0.2, { duration: 520, easing: Easing.inOut(Easing.quad) }),
      withTiming(1, { duration: 520, easing: Easing.inOut(Easing.quad) }),
    ), -1, false);
    return () => cancelAnimation(blink);
  }, [blink, recording]);
  useEffect(() => {
    if (!recording || locked) { cancelAnimation(arrow); arrow.value = 0; return; }
    arrow.value = withRepeat(withSequence(
      withTiming(1, { duration: 720, easing: Easing.inOut(Easing.quad) }),
      withTiming(0, { duration: 720, easing: Easing.inOut(Easing.quad) }),
    ), -1, false);
    return () => cancelAnimation(arrow);
  }, [arrow, locked, recording]);
  useEffect(() => {
    enter.value = withTiming(busy ? 1 : 0, { duration: busy ? 170 : 120, easing: busy ? Easing.out(Easing.cubic) : Easing.in(Easing.cubic) });
  }, [busy, enter]);
  useEffect(() => {
    const ready = voice.phase === 'preview' || voice.phase === 'uploading';
    if (ready) { sendPop.value = 0; sendPop.value = withSpring(1, { damping: 11, stiffness: 300 }); }
  }, [sendPop, voice.phase]);

  // ---- стили на стороне UI: ни одного setValue на кадр
  const haloStyle = useAnimatedStyle(() => ({
    opacity: grow.value * interpolate(lvl.value, [0, 1], [0.08, 0.3]),
    transform: [{ translateX: dx.value }, { scale: interpolate(lvl.value, [0, 1], [1.1, 2.7]) }],
  }));
  const ringStyle = useAnimatedStyle(() => ({
    opacity: grow.value * interpolate(lvl.value, [0, 1], [0.14, 0.4]),
    transform: [{ translateX: dx.value }, { scale: interpolate(lvl.value, [0, 1], [1.0, 1.85]) }],
  }));
  const discStyle = useAnimatedStyle(() => ({
    opacity: interpolate(dx.value, [CANCEL_AT, CANCEL_AT / 2], [0.25, 1], Extrapolation.CLAMP),
    transform: [{ translateX: dx.value }, { scale: interpolate(grow.value, [0, 1], [1, 1.3]) }],
  }));
  const micFillStyle = useAnimatedStyle(() => ({ opacity: grow.value }));
  const micGreyStyle = useAnimatedStyle(() => ({ opacity: 1 - grow.value }));
  const micWhiteStyle = useAnimatedStyle(() => ({ opacity: grow.value }));
  const barStyle = useAnimatedStyle(() => ({
    opacity: enter.value,
    transform: [{ translateY: interpolate(enter.value, [0, 1], [10, 0]) }],
  }));
  const dotStyle = useAnimatedStyle(() => ({ opacity: blink.value }));
  const hintStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: interpolate(dx.value, [HINT_TRAVEL, 0], [HINT_TRAVEL, 0], Extrapolation.CLAMP) * (1 - cancelHint.value) }],
  }));
  const lockPillStyle = useAnimatedStyle(() => ({
    opacity: enter.value,
    transform: [{ translateY: interpolate(lift.value, [0, 1], [0, -14]) }, { scale: interpolate(lift.value, [0, 1], [1, 1.08]) }],
  }));
  const lockFillStyle = useAnimatedStyle(() => ({ opacity: lift.value }));
  const arrowStyle = useAnimatedStyle(() => ({
    opacity: arrow.value * (1 - lift.value),
    transform: [{ translateY: interpolate(arrow.value, [0, 1], [2, -3]) }],
  }));
  const sendStyle = useAnimatedStyle(() => ({ transform: [{ scale: interpolate(sendPop.value, [0, 1], [0.6, 1]) }], opacity: sendPop.value }));

  const cancelling = hint === 'cancel';
  const sendNow = () => { voice.stopAndSend(); resetGesture(); };
  const dropIt = () => { buzzLost(); voice.cancel(); resetGesture(); };
  const ready = voice.phase === 'preview' || voice.phase === 'uploading';

  return (
    <View style={[s.hold, busy && s.holdBusy]} {...responder.panHandlers}>
      {busy ? (
        <Animated.View style={[s.barLeft, barStyle]}>
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
              <Animated.View style={[s.dot, dotStyle]} />
              <Text style={s.timer}>{formatDuration(voice.durationMillis)}</Text>
              <LiveWave levels={voice.liveBars} />
            </>
          ) : (
            <>
              <Animated.View style={[s.dot, dotStyle]} />
              <Text style={s.timer}>{formatDuration(voice.durationMillis)}</Text>
              <Animated.View style={[s.hintRow, hintStyle]}>
                {cancelling ? <IconTrash size={15} c={color.primary} /> : <Text style={s.hintArrow}>◀</Text>}
                <Text style={[s.hint, cancelling && s.hintCancel]} numberOfLines={1}>
                  {cancelling
                    ? T('Отпусти — отмена', 'Release to cancel', 'Suelta para cancelar')
                    : T('Влево — отмена', 'Slide to cancel', 'Desliza para cancelar')}
                </Text>
              </Animated.View>
            </>
          )}
        </Animated.View>
      ) : null}

      <View style={s.micSlot}>
        {locked || ready ? (
          <Animated.View style={sendStyle}>
            <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send', 'Enviar')}
                       onPress={locked ? sendNow : voice.send} disabled={voice.disabled}
                       style={[s.send, voice.disabled && { opacity: 0.55 }]}>
              {voice.phase === 'uploading' ? <ActivityIndicator size="small" color={color.onPrimary} /> : <IconSend size={17} />}
            </Pressable>
          </Animated.View>
        ) : (
          <>
            <Animated.View style={[s.halo, haloStyle]} pointerEvents="none" />
            <Animated.View style={[s.halo, ringStyle]} pointerEvents="none" />
            <Animated.View
              accessibilityRole="button"
              accessibilityLabel={T('Удерживай, чтобы записать голосовое', 'Hold to record a voice message', 'Pulsa y sostén para grabar un mensaje de voz')}
              style={[s.micDisc, discStyle]}
            >
              <Animated.View style={[s.micFill, micFillStyle]} pointerEvents="none" />
              <Animated.View style={[s.micIcon, micGreyStyle]}><IconMic /></Animated.View>
              <Animated.View style={[s.micIcon, micWhiteStyle]}><IconMic c={color.onPrimary} /></Animated.View>
            </Animated.View>
            {recording ? (
              <Animated.View style={[s.lockPill, lockPillStyle]} pointerEvents="none">
                <Animated.View style={[s.lockFill, lockFillStyle]} />
                <Animated.View style={arrowStyle}><IconChevronUp size={11} c={color.muted} /></Animated.View>
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
  const hasText = Boolean(String(voice.transcript || '').trim());
  return (
    <View style={[s.bubble, mine && s.bubbleMine]}>
      <AudioPlay source={mediaUrl(voice.url)} durationMs={voice.duration_ms} peaks={peaks} mine={mine} />
      {hasText ? (
        <Pressable accessibilityRole="button" onPress={() => setShowTranscript((v) => !v)} hitSlop={4}>
          <Text style={[s.transcriptLink, mine && { color: color.onPrimary }]}>
            {showTranscript ? T('Скрыть текст', 'Hide transcript', 'Ocultar transcripción') : T('Показать текст', 'Show transcript', 'Mostrar transcripción')}
          </Text>
        </Pressable>
      ) : null}
      {showTranscript && hasText ? <Transcript text={voice.transcript} mine={mine} /> : null}
    </View>
  );
}

function Transcript({ text, mine }: { text: string; mine: boolean }) {
  const a = useSharedValue(0);
  useEffect(() => { a.value = withTiming(1, { duration: 190, easing: Easing.out(Easing.quad) }); }, [a]);
  const style = useAnimatedStyle(() => ({ opacity: a.value, transform: [{ translateY: interpolate(a.value, [0, 1], [-5, 0]) }] }));
  return <Animated.Text style={[s.transcript, mine && { color: color.onPrimary }, style]}>{text}</Animated.Text>;
}

// ===== вид

const s = StyleSheet.create({
  iconButton: { minWidth: 28, height: 34, alignItems: 'center', justifyContent: 'center' },
  recording: { minWidth: 76, flexDirection: 'row', gap: 7 },
  stop: { width: 11, height: 11, borderRadius: 2, backgroundColor: color.primary },
  timer: { width: 46, fontSize: 12, color: color.primary, fontVariant: ['tabular-nums'] },
  send: { width: 36, height: 36, borderRadius: 18, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },

  // --- проигрыватель: круглая кнопка слева, волна и отсчёт столбиком справа — как в мессенджерах
  playRow: { minWidth: 196, flexDirection: 'row', alignItems: 'center', gap: 10 },
  playRowGrow: { flex: 1 },
  playButton: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center' },
  playButtonTheirs: { backgroundColor: color.primary },
  playButtonMine: { backgroundColor: color.onPrimary },
  playInner: { width: 38, height: 38, alignItems: 'center', justifyContent: 'center' },
  playIcon: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center' },
  pause: { flexDirection: 'row', gap: 3 },
  pauseBar: { width: 3, height: 14, borderRadius: 1 },
  playBody: { flex: 1, gap: 3 },
  playMeta: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  wave: { height: 26, justifyContent: 'center' },
  waveRow: { height: 26, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  waveMask: { position: 'absolute', left: 0, top: 0, height: 26, overflow: 'hidden' },
  waveBar: { width: 2.5, borderRadius: 1.5 },
  duration: { fontSize: 11, color: color.muted, fontVariant: ['tabular-nums'] },
  durationStuck: { fontSize: 10, color: color.primary, fontVariant: undefined },
  rate: { paddingHorizontal: 6, height: 18, borderRadius: 9, alignItems: 'center', justifyContent: 'center', backgroundColor: color.neutral100 },
  rateMine: { backgroundColor: color.onCoverSoft },
  rateText: { fontSize: 10, fontWeight: '700', color: color.muted, fontVariant: ['tabular-nums'] },

  // --- кнопка удержания
  hold: { minWidth: 28, minHeight: 34, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 8 },
  holdBusy: { flex: 1, minHeight: 36 },
  barLeft: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8 },
  micSlot: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  halo: { position: 'absolute', width: 34, height: 34, borderRadius: 17, backgroundColor: color.primary },
  micDisc: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },
  micFill: { ...StyleSheet.absoluteFill, borderRadius: 17, backgroundColor: color.primary },
  micIcon: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center' },
  lockPill: {
    position: 'absolute', bottom: 46, width: 30, paddingVertical: 6, borderRadius: 15,
    alignItems: 'center', gap: 3, backgroundColor: color.card, borderWidth: 1, borderColor: color.border,
  },
  lockFill: { ...StyleSheet.absoluteFill, borderRadius: 15, backgroundColor: color.neutral100 },

  // --- полоса записи
  barAction: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: color.primary },
  hintRow: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5 },
  hintArrow: { fontSize: 10, color: color.neutral400 },
  hint: { fontSize: 12, color: color.muted, flexShrink: 1 },
  hintCancel: { color: color.primary, fontWeight: '600' },
  liveWave: { flex: 1, height: 20, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 2 },
  liveBar: { width: 2, borderRadius: 1, backgroundColor: color.neutral300 },

  // --- пузырь
  bubble: { minWidth: 236, maxWidth: 290, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 16, backgroundColor: color.neutral100 },
  bubbleMine: { backgroundColor: color.primary },
  transcriptLink: { fontSize: 12, color: color.primary, marginTop: 4, fontWeight: '600' },
  transcript: { fontSize: 13, lineHeight: 18, color: color.fg, marginTop: 6 },
});
