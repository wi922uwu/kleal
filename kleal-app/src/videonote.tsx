/**
 * КРУЖОК — короткое видео вместо реплики.
 *
 * Устроен ровно как голосовое, и это не совпадение, а условие: жест «прижал — говоришь, отпустил
 * — ушло, потянул влево — отмена» человек в этом приложении уже выучил на микрофоне. Дать
 * соседней кнопке другую грамматику значит заставить учить её заново.
 *
 * Чем кружок отличается от голосового:
 *   — во время записи видно себя. Круглое окошко над композером — это и есть кадр, который
 *     уйдёт; снимать вслепую то, где показывают лицо, нельзя;
 *   — минута против минуты, но вес другой: видео тяжелее на порядок, поэтому берётся низкое
 *     разрешение (`480p`). Кружок смотрят в кружке — большего разрешения там просто не видно;
 *   — расшифровки нет. В списке «Сообщений» под именем сервер ставит подпись, иначе там зияла
 *     бы пустота.
 *
 * ЗАПИСЬ ТОЛЬКО С ФРОНТАЛЬНОЙ КАМЕРЫ и без переключения: кружок — это лицо, и выбор камеры
 * здесь лишний вопрос. Кому нужна задняя камера, тому нужно не сообщение, а видеофайл.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, Alert, Animated, Easing, PanResponder, Platform, Pressable,
  StyleSheet, Text, View,
} from 'react-native';
import * as Haptics from 'expo-haptics';
import { CameraView, useCameraPermissions, useMicrophonePermissions } from 'expo-camera';
import { useVideoPlayer, VideoView } from 'expo-video';
import { mediaUrl, video as videoApi, VideoPayload } from './api';
import { T } from './i18n';
import { color } from './theme';
import { IconVideo } from './components/icons';

const MAX_MS = 60_000;
/** Короче — не сообщение, а промах пальцем: отпускание отправляет сразу. */
const MIN_MS = 700;
/** Потянул влево — отмена. Порог тот же, что у голосового: рука уже знает это расстояние. */
const CANCEL_AT = -80;
/** Размер круга: и превью при записи, и пузыря в ленте. Один размер — одна вещь. */
export const CIRCLE = 168;

const canBuzz = Platform.OS !== 'web';
const buzz = (s: Haptics.ImpactFeedbackStyle) => { if (canBuzz) Haptics.impactAsync(s).catch(() => {}); };
const buzzLost = () => {
  if (canBuzz) Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
};

const clock = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};

/**
 * `arming` — камера уже на экране, но ещё не готова снимать.
 *
 * Без этого состояния кружок не записывался вовсе: камера монтируется только на время записи, а
 * `recordAsync` вызывался сразу после `setPhase` — ссылки на камеру в этот момент ещё нет, вызов
 * уходил в никуда и запись молча не начиналась. На устройстве к тому же камера просыпается не
 * мгновенно, так что ждать её надо в любом случае — сигнал даёт сама камера (`onCameraReady`).
 */
type Phase = 'idle' | 'arming' | 'recording' | 'uploading';

export function useVideoNote(onSend: (v: VideoPayload) => void, disabled = false) {
  const cam = useRef<CameraView>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [ms, setMs] = useState(0);
  const [cameraOk, askCamera] = useCameraPermissions();
  const [micOk, askMic] = useMicrophonePermissions();
  const cancelled = useRef(false);
  const started = useRef(0);
  /** Палец отпустили раньше, чем камера проснулась: записывать уже нечего. */
  const letGo = useRef(false);

  useEffect(() => {
    if (phase !== 'recording') return;
    const id = setInterval(() => setMs(Date.now() - started.current), 100);
    return () => clearInterval(id);
  }, [phase]);

  // Минутный предел: дальше камера останавливается сама, и это отпускание руки не требует.
  useEffect(() => {
    if (phase === 'recording' && ms >= MAX_MS) cam.current?.stopRecording();
  }, [phase, ms]);

  /** Записывать начинает КАМЕРА, когда проснулась, — см. `arming`. */
  const begin = useCallback(async () => {
    if (!cam.current) return;
    started.current = Date.now();
    setMs(0);
    setPhase('recording');
    buzz(Haptics.ImpactFeedbackStyle.Light);
    try {
      // Разрешается ТОЛЬКО когда запись остановлена — отпусканием пальца или пределом.
      const r = await cam.current.recordAsync({ maxDuration: MAX_MS / 1000 });
      const took = Date.now() - started.current;
      setPhase('idle');
      if (cancelled.current || !r?.uri) return;
      if (took < MIN_MS) { buzzLost(); return; }
      setPhase('uploading');
      const form = new FormData();
      form.append('file', { uri: r.uri, name: `circle-${Date.now()}.mp4`, type: 'video/mp4' } as any);
      const up: any = await videoApi.upload(form, took);
      if (!up?.ok || !up?.id) throw new Error(String(up?.error || 'UPLOAD_FAILED'));
      onSend({ id: up.id, url: up.url, duration_ms: up.duration_ms, mime_type: up.mime_type });
      buzz(Haptics.ImpactFeedbackStyle.Light);
    } catch {
      Alert.alert(T('Кружок не ушёл', 'The circle didn’t send'),
                  T('Проверь связь и попробуй ещё раз.', 'Check your connection and try again.'));
    } finally {
      setPhase('idle');
    }
  }, [onSend]);

  const start = useCallback(async () => {
    if (disabled || phase !== 'idle') return;
    const c = cameraOk?.granted ? cameraOk : await askCamera();
    const m = micOk?.granted ? micOk : await askMic();
    if (!c?.granted || !m?.granted) {
      return Alert.alert(
        T('Нужен доступ к камере и микрофону', 'Camera and microphone access needed'),
        T('Разрешите их в настройках устройства — без звука кружок был бы немым.',
          'Allow both in device settings — without sound the circle would be mute.')
      );
    }
    cancelled.current = false;
    letGo.current = false;
    setMs(0);
    setPhase('arming');            // камера появляется на экране; снимать начнёт, когда проснётся
  }, [askCamera, askMic, cameraOk, disabled, micOk, phase]);

  const ready = useCallback(() => {
    if (letGo.current) { setPhase('idle'); return; }
    begin();
  }, [begin]);

  const stop = useCallback((cancel = false) => {
    cancelled.current = cancel;
    letGo.current = true;
    if (cancel) buzzLost();
    cam.current?.stopRecording();
  }, []);

  return { cam, phase, ms, start, stop, ready, disabled: disabled || phase === 'uploading' };
}

export type VideoNote = ReturnType<typeof useVideoNote>;

/**
 * Кнопка в композере и круглое окошко над ним.
 *
 * Окошко живёт absolute поверх ленты, а не в потоке: композер не должен прыгать, а кадр обязан
 * быть крупным. Камера смонтирована ТОЛЬКО во время записи — держать её включённой ради кнопки
 * значит жечь батарею и держать зажжённым индикатор камеры без причины.
 */
export function VideoNoteControl({ note }: { note: VideoNote }) {
  const recording = note.phase === 'recording' || note.phase === 'arming';
  const [cancelling, setCancelling] = useState(false);
  const dx = useRef(new Animated.Value(0)).current;
  const grow = useRef(new Animated.Value(0)).current;
  const noteRef = useRef(note);
  noteRef.current = note;
  const cancelRef = useRef(false);

  useEffect(() => {
    Animated.timing(grow, {
      toValue: recording ? 1 : 0, duration: 180, easing: Easing.out(Easing.cubic), useNativeDriver: true,
    }).start();
    if (!recording) { setCancelling(false); cancelRef.current = false; dx.setValue(0); }
  }, [dx, grow, recording]);

  const responder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: () => { cancelRef.current = false; noteRef.current.start(); },
      onPanResponderMove: (_e, g) => {
        dx.setValue(Math.max(-140, Math.min(0, g.dx)));
        const over = g.dx < CANCEL_AT;
        if (over !== cancelRef.current) {
          cancelRef.current = over;
          setCancelling(over);
          if (over) buzz(Haptics.ImpactFeedbackStyle.Light);
        }
      },
      onPanResponderRelease: () => noteRef.current.stop(cancelRef.current),
      // Жест перехватила прокрутка или звонок — это отмена: отправлять то, чего человек не
      // заканчивал, нельзя.
      onPanResponderTerminate: () => noteRef.current.stop(true),
    })
  ).current;

  return (
    <>
      {recording ? (
        <Animated.View
          style={[s.stage, { opacity: grow, transform: [{ scale: grow.interpolate({ inputRange: [0, 1], outputRange: [0.85, 1] }) }] }]}
          pointerEvents="none"
        >
          <View style={[s.circle, cancelling && s.circleCancel]}>
            <CameraView
              ref={note.cam}
              style={StyleSheet.absoluteFill}
              facing="front"
              mode="video"
              videoQuality="480p"
              onCameraReady={note.ready}
            />
          </View>
          <View style={s.hud}>
            <View style={s.dot} />
            <Text style={s.timer}>{clock(note.ms)}</Text>
            <Text style={[s.hint, cancelling && s.hintCancel]}>
              {cancelling ? T('Отпусти — отмена', 'Release to cancel') : T('◀ влево — отмена', '◀ slide to cancel')}
            </Text>
          </View>
        </Animated.View>
      ) : null}

      <View style={s.slot} {...responder.panHandlers}>
        {note.phase === 'uploading'
          ? <ActivityIndicator size="small" color={color.primary} />
          : (
            <Animated.View style={{ transform: [{ translateX: dx }, { scale: grow.interpolate({ inputRange: [0, 1], outputRange: [1, 1.25] }) }] }}>
              <IconVideo size={22} c={recording ? color.primary : color.muted} />
            </Animated.View>
          )}
      </View>
    </>
  );
}

/**
 * Кружок в ленте.
 *
 * Круглым его делает обрезка квадратного кадра: `borderRadius` в половину стороны и
 * `overflow: hidden`. Растягивать видео в круг нельзя — лицо поедет; поэтому `contentFit="cover"`,
 * то есть кадр обрезается по краям, а не сжимается.
 *
 * Играет по нажатию, а не сам: кружок со звуком, который заиграл, пока человек листает ленту в
 * тихом месте, — это не оживление, а неприятность.
 */
export function VideoBubble({ video }: { video: VideoPayload }) {
  const player = useVideoPlayer(mediaUrl(video.url), (p) => { p.loop = false; });
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    const sub = player.addListener('playingChange', ({ isPlaying }) => setPlaying(isPlaying));
    return () => sub.remove();
  }, [player]);

  const toggle = () => {
    if (playing) { player.pause(); return; }
    player.currentTime = 0;
    player.play();
  };

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={playing ? T('Пауза', 'Pause') : T('Смотреть кружок', 'Play the circle')}
      onPress={toggle}
      style={s.bubble}
    >
      <VideoView style={StyleSheet.absoluteFill} player={player} contentFit="cover" nativeControls={false} />
      {!playing ? (
        <View style={s.veil}>
          <Text style={s.play}>▶</Text>
        </View>
      ) : null}
      <View style={s.length}><Text style={s.lengthText}>{clock(video.duration_ms)}</Text></View>
    </Pressable>
  );
}

// ===== вид

const s = StyleSheet.create({
  slot: { minWidth: 28, minHeight: 34, alignItems: 'center', justifyContent: 'center' },

  /** Окошко записи — над композером, поверх ленты: композер от него не сдвигается. */
  stage: { position: 'absolute', right: 8, bottom: 56, alignItems: 'center', gap: 8 },
  circle: {
    width: CIRCLE, height: CIRCLE, borderRadius: CIRCLE / 2, overflow: 'hidden',
    borderWidth: 3, borderColor: color.primary, backgroundColor: color.ink,
  },
  circleCancel: { borderColor: color.neutral400, opacity: 0.5 },
  hud: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: color.card,
  },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: color.primary },
  timer: { fontSize: 12, color: color.primary, fontVariant: ['tabular-nums'] },
  hint: { fontSize: 11, color: color.muted },
  hintCancel: { color: color.primary, fontWeight: '600' },

  bubble: {
    width: CIRCLE, height: CIRCLE, borderRadius: CIRCLE / 2,
    overflow: 'hidden', backgroundColor: color.ink,
  },
  veil: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center', backgroundColor: '#00000033' },
  play: { fontSize: 34, color: color.onPrimary },
  length: {
    position: 'absolute', bottom: 8, alignSelf: 'center',
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, backgroundColor: '#00000066',
  },
  lengthText: { fontSize: 11, color: color.onPrimary, fontVariant: ['tabular-nums'] },
});
