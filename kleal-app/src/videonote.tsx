/**
 * КРУЖОК — короткое видео вместо реплики.
 *
 * ПОЧЕМУ ЗДЕСЬ НЕТ УДЕРЖАНИЯ. Первая попытка повторяла микрофон: прижал кнопку в композере —
 * пишется, отпустил — ушло. Она не заработала ни разу, и не из-за отдельных ошибок, а из-за самого
 * устройства. Камера в нём поднималась ПОСЛЕ нажатия, и между «палец лёг» и «камера пишет»
 * оставался промежуток в сотни миллисекунд, куда проваливалось всё: отпускание стиралось
 * запоздавшим стартом, просьба остановиться уходила в пустоту, потерянный жест оставлял запись без
 * единого способа её кончить. Каждую дыру латали отдельно — отметкой, сторожем, повторной
 * просьбой раз в четверть секунды, — и на каждую заплату находилась следующая.
 *
 * Устройство теперь другое, и держится на трёх опорах:
 *
 *   1. КАМЕРА ГОТОВА ДО ТОГО, как запись можно начать. Окно открывается заранее, камера в нём
 *      просыпается, и кнопка «записать» до её сигнала попросту не нажимается. Промежутка, в
 *      который проваливались команды, больше нет — не потому что он обработан, а потому что его
 *      неоткуда взять.
 *   2. НАЧАЛО И КОНЕЦ — ЯВНЫЕ НАЖАТИЯ. Жеста нет вовсе, а значит его нельзя потерять: ни
 *      прокруткой, ни звонком, ни соскочившим за край пальцем.
 *   3. ОТМЕНА — ЭТО ЗАКРЫТЬ ОКНО. Она не просит камеру остановиться и не ждёт её согласия: камера
 *      уходит с экрана вместе с окном, а съёмка обрывается вместе с камерой. Выход, который не
 *      зависит ни от чего.
 *
 * И следствие, ради которого всё и затевалось: ВСЁ ОКНО ЦЕЛИКОМ живёт в модальном экране. Кнопки
 * больше не висят поверх композера — а именно там они и не нажимались: на iOS касание за
 * пределами родительского view до ребёнка не доходит, кнопка видна и мертва.
 *
 * Чем кружок отличается от голосового:
 *   — во время записи видно себя: снимать вслепую то, где показывают лицо, нельзя;
 *   — вес другой, видео тяжелее на порядок, поэтому низкое разрешение (`480p`). Кружок смотрят в
 *     кружке — большего там просто не видно;
 *   — расшифровки нет: в списке «Сообщений» подпись под именем ставит сервер.
 *
 * ЗАПИСЬ ТОЛЬКО С ФРОНТАЛЬНОЙ КАМЕРЫ и без переключения: кружок — это лицо. Кому нужна задняя
 * камера, тому нужно не сообщение, а видеофайл.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, Alert, Linking, Modal, Platform, Pressable, StyleSheet, Text, View,
} from 'react-native';
import * as Haptics from 'expo-haptics';
import { CameraView, useCameraPermissions, useMicrophonePermissions } from 'expo-camera';
import { setAudioModeAsync } from 'expo-audio';
import { useVideoPlayer, VideoView } from 'expo-video';
import { mediaUrl, video as videoApi, VideoPayload } from './api';
import { T } from './i18n';
import { color } from './theme';
import { IconSend, IconVideo } from './components/icons';

const MAX_MS = 60_000;
/**
 * Раньше этого кнопка «готово» не нажимается.
 *
 * Смысл двойной. Первый — сообщением полусекундный обрывок всё равно не будет. Второй важнее:
 * это единственное место, где съёмку могли остановить раньше, чем камера успела её начать, — а
 * остановка, попавшая в этот промежуток, уходит в пустоту и запись становится неостановимой.
 * Полсекунды с лишним — на порядок больше, чем нужно камере, чтобы начать.
 */
const MIN_MS = 700;
/** Сколько ждать пробуждения камеры, прежде чем признать, что она не отзовётся. */
const WARM_MS = 6000;
/** Размер кружка в ленте. */
export const CIRCLE = 168;
/** Размер кадра в окне съёмки: тут смотрят на себя, и мелкий кружок для этого не годится. */
const PREVIEW = 280;

const buzz = (s: Haptics.ImpactFeedbackStyle) => { Haptics.impactAsync(s).catch(() => {}); };
const buzzLost = () => {
  Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
};

const clock = (ms: number) => {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};

/**
 * Одно состояние на всю съёмку — и никаких отметок рядом с ним.
 *
 * В прошлом устройстве состояний было три, а вокруг них жили шесть булевых ссылок: «палец на
 * кнопке», «съёмка идёт», «просили остановить», «предел уже сработал», «отменено», сторожевой
 * таймер. Разъехаться они могли восемью способами, и половина отказов была именно этим.
 *
 *   off      окна нет
 *   warming  окно открыто, камера просыпается — записывать ещё нечем
 *   ready    камера готова, ждём нажатия
 *   recording  пишем
 *   sending  запись кончилась, файл уезжает
 *   failed   не уехало (или не записалось) — снятое цело, повтор одним нажатием
 */
type Stage = 'off' | 'warming' | 'ready' | 'recording' | 'sending' | 'failed';

export function VideoNoteButton({
  onSend, disabled = false,
}: {
  onSend: (v: VideoPayload) => void;
  disabled?: boolean;
}) {
  const cam = useRef<CameraView>(null);
  const [stage, setStage] = useState<Stage>('off');
  const [ms, setMs] = useState(0);
  /**
   * Почему не вышло — СЛОВАМИ от устройства, а не молчанием. Съёмка срывается по причинам, о
   * которых знает только оно: занятая звуковая сессия, отказ системы, нет места. Пустой `catch`
   * оставлял человека с одним наблюдением — «появилось и пропало», — и отлаживать это нечем.
   */
  const [err, setErr] = useState('');
  const [cameraOk, askCamera] = useCameraPermissions();
  const [micOk, askMic] = useMicrophonePermissions();
  const startedAt = useRef(0);
  /**
   * Снятое, но не уехавшее. Кружок весит мегабайты, отправка по плохой связи срывается легко —
   * выбрасывать при этом запись нельзя: переснять момент человек не может, он прошёл.
   */
  const clip = useRef<{ uri: string; ms: number } | null>(null);
  /**
   * Окно закрыли, пока камера или сеть ещё чем-то заняты. Их ответ придёт — и трогать состояние
   * им уже нельзя: человек ушёл, и вернуть его в окно, которое он закрыл, было бы захватом экрана.
   */
  const gone = useRef(false);

  const on = stage !== 'off';

  /**
   * Звуковая сессия у камеры и у голосовых ОДНА на приложение, и голосовой модуль оставляет её в
   * режиме «только воспроизведение» (`allowsRecording: false`). Камера в нём звук не захватывает,
   * и съёмка не начинается вовсе — снаружи это ровно «кружок появился и пропал».
   *
   * Переключение привязано к самому окну, а не к записи: открылось — взяли, закрылось — вернули.
   * Возврат в уборке эффекта, поэтому он случится на ЛЮБОМ исходе, включая отмену, слишком
   * короткое нажатие и уход с экрана вместе с чатом. Иначе следующее голосовое осталось бы в
   * режиме записи и звучало бы в тишину.
   */
  useEffect(() => {
    if (!on) return;
    setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true }).catch(() => {});
    return () => { setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true }).catch(() => {}); };
  }, [on]);

  useEffect(() => {
    if (stage !== 'recording') return;
    const id = setInterval(() => setMs(Date.now() - startedAt.current), 100);
    return () => clearInterval(id);
  }, [stage]);

  /**
   * Камера может не отозваться ВОВСЕ — и тогда ждать её нечего.
   *
   * На симуляторе камеры нет физически, и `onCameraReady` не придёт никогда: без этого срока окно
   * оставалось бы навсегда с крутящимся кружком и словом «просыпается…», а человек — без единого
   * объяснения. Проверено ровно так и было. На телефоне то же самое значит, что камеру держит
   * кто-то другой.
   *
   * Шесть секунд: столько камера не просыпается никогда — обычно ей хватает долей секунды.
   */
  useEffect(() => {
    if (stage !== 'warming') return;
    const id = setTimeout(() => {
      setErr(T('камера не отозвалась', 'the camera did not respond'));
      setStage('failed');
    }, WARM_MS);
    return () => clearTimeout(id);
  }, [stage]);

  /** Отправка отдельно от съёмки: её повторяют, и повтор не должен требовать переснять момент. */
  const send = useCallback(async () => {
    const c = clip.current;
    if (!c) return;
    setErr('');
    setStage('sending');
    try {
      // Расширение берётся из САМОГО файла, а запасное — по платформе: iOS пишет QuickTime всегда
      // (`generatePathInCache(…, extension: ".mov")` в CameraVideoRecording.swift), Android —
      // mp4. Назвать `.mov` мпэшкой значит отдать байты QuickTime под чужим именем, и
      // проигрыватель вправе не открыть их вовсе.
      const ext = (c.uri.split('?')[0].split('.').pop()
        || (Platform.OS === 'ios' ? 'mov' : 'mp4')).toLowerCase();
      const form = new FormData();
      form.append('file', {
        uri: c.uri,
        name: `circle-${Date.now()}.${ext}`,
        type: ext === 'mov' ? 'video/quicktime' : 'video/mp4',
      } as any);
      const up: any = await videoApi.upload(form, c.ms);
      if (!up?.ok || !up?.id) throw new Error(String(up?.error || 'UPLOAD_FAILED'));
      if (gone.current) return;
      onSend({ id: up.id, url: up.url, duration_ms: up.duration_ms, mime_type: up.mime_type });
      buzz(Haptics.ImpactFeedbackStyle.Light);
      clip.current = null;
      setStage('off');
    } catch (e) {
      if (gone.current) return;
      buzzLost();
      setErr(String((e as any)?.message || e || '').slice(0, 160));
      setStage('failed');
    }
  }, [onSend]);

  /**
   * Съёмка. Зовётся ТОЛЬКО из нажатия и ТОЛЬКО когда камера уже отозвалась готовой — потому и нет
   * ни ожидания камеры, ни отметок «уже пишем»: состояние `ready` бывает одно, и нажать в нём
   * можно один раз.
   */
  const record = useCallback(async () => {
    if (!cam.current) return;
    startedAt.current = Date.now();
    setMs(0);
    setErr('');
    setStage('recording');
    buzz(Haptics.ImpactFeedbackStyle.Medium);
    try {
      // Предел держит сама камера. Считать его по таймеру и звать остановку значит опять городить
      // отметки «остановили один раз, а не пачкой» — камера умеет это сама и без нас.
      const r = await cam.current.recordAsync({ maxDuration: MAX_MS / 1000 });
      if (gone.current) return;
      if (!r?.uri) { setStage('ready'); return; }
      clip.current = { uri: r.uri, ms: Math.min(Date.now() - startedAt.current, MAX_MS) };
      await send();
    } catch (e) {
      if (gone.current) return;
      // Текст от системы оставляем дословно: он не для красоты, а для ответа на вопрос «почему не
      // снялось», и другого источника этого ответа нет.
      setErr(String((e as any)?.message || e || '').slice(0, 160));
      buzzLost();
      setStage('failed');
    }
  }, [send]);

  const open = useCallback(async () => {
    if (disabled || stage !== 'off') return;
    const c = cameraOk?.granted ? cameraOk : await askCamera();
    const m = micOk?.granted ? micOk : await askMic();
    if (!c?.granted || !m?.granted) {
      // Второй раз система не спросит — она спрашивает один раз за установку. Поэтому не «сходи
      // куда-нибудь и разреши», а кнопка, которая открывает ровно ту страницу настроек.
      return Alert.alert(
        T('Нужен доступ к камере и микрофону', 'Camera and microphone access needed'),
        T('Без звука кружок был бы немым.', 'Without sound the circle would be mute.'),
        [
          { text: T('Не сейчас', 'Not now'), style: 'cancel' },
          { text: T('Настройки', 'Settings'), onPress: () => { Linking.openSettings().catch(() => {}); } },
        ]
      );
    }
    gone.current = false;
    clip.current = null;
    setErr('');
    setMs(0);
    setStage('warming');
  }, [askCamera, askMic, cameraOk, disabled, micOk, stage]);

  /**
   * Закрыть — и этим же оборвать съёмку.
   *
   * Камера уходит с экрана вместе с окном, а съёмка обрывается вместе с камерой: просить её об
   * остановке и ждать согласия не нужно. Это и есть выход, который работает всегда, — тот самый,
   * которого не было, когда запись «не завершалась ни отменой, ни отправкой».
   */
  const close = useCallback(() => {
    gone.current = true;
    clip.current = null;
    setStage('off');
  }, []);

  /**
   * «Готово»: камеру просят остановиться, и её ответ — это `recordAsync`, который дальше отправит.
   *
   * ПЕРЕХВАТИТЬ ОТКАЗ ЭТОГО ВЫЗОВА НЕЛЬЗЯ, и это не предположение. В expo-camera 17.0.10
   * (`build/CameraView.js`) метод написан так:
   *
   *     stopRecording() { this._cameraRef.current?.stopRecording(); }
   *
   * Нативное обещание он не возвращает — оно теряется у него внутри. Прежняя заплатка навешивала
   * `catch` на `undefined` и не делала ровно ничего: красная плашка «Uncaught (in promise)»
   * приходила мимо неё.
   *
   * Значит лекарство одно — НЕ ЗВАТЬ ТАМ, ГДЕ МОЖЕТ ОТКАЗАТЬ. Здесь это гарантировано устройством
   * окна: кнопка существует только в состоянии `recording`, а в него попадают лишь из готовой
   * камеры и не раньше, чем через MIN_MS после начала съёмки. Останавливать всегда есть что.
   */
  const finish = useCallback(() => {
    buzz(Haptics.ImpactFeedbackStyle.Light);
    setStage('sending');
    cam.current?.stopRecording();
  }, []);

  /** Камера может отозваться готовой не один раз — переход из `warming` просто нечему повторить. */
  const ready = useCallback(() => setStage((v) => (v === 'warming' ? 'ready' : v)), []);

  /** Поднять камеру заново после «не записалось»: окно уже открыто, закрывать его незачем. */
  const again = useCallback(() => { setErr(''); setMs(0); setStage('warming'); }, []);

  const live = stage === 'warming' || stage === 'ready' || stage === 'recording';

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={T('Записать кружок', 'Record a circle')}
        accessibilityState={{ disabled }}
        disabled={disabled}
        onPress={() => { open().catch(() => {}); }}
        style={s.slot}
        hitSlop={8}
      >
        <IconVideo size={22} c={disabled ? color.neutral300 : color.muted} />
      </Pressable>

      <Modal visible={on} animationType="fade" onRequestClose={close} statusBarTranslucent>
        <View style={s.screen}>
          <View style={[s.frame, stage === 'recording' && s.frameLive]}>
            {live ? (
              <CameraView
                ref={cam}
                style={StyleSheet.absoluteFill}
                facing="front"
                mode="video"
                videoQuality="480p"
                onCameraReady={ready}
              />
            ) : (
              /* Съёмка кончилась — камеру с экрана долой: батарея и индикатор камеры не должны
                 гореть, пока уезжает файл. */
              <View style={s.blank}>
                {stage === 'sending' ? <ActivityIndicator size="large" color={color.onPrimary} /> : null}
              </View>
            )}
          </View>

          {/* Отсчёт остаётся стоять и пока файл уезжает: видно, какой длины кружок отправляется. */}
          <Text style={s.timer}>
            {stage === 'recording' || stage === 'sending' ? clock(ms) : ''}
          </Text>

          <Text style={s.say} numberOfLines={3}>
            {stage === 'warming' ? T('Камера просыпается…', 'Waking the camera…')
              : stage === 'ready' ? T('Нажми, чтобы записать. До минуты.', 'Tap to record. Up to a minute.')
              : stage === 'recording' ? (ms < MIN_MS
                  ? T('Пишем…', 'Recording…')
                  : T('Нажми «готово», когда закончишь', 'Tap “done” when you’re finished'))
              : stage === 'sending' ? T('Отправляю кружок…', 'Sending the circle…')
              : err
                ? `${T('Не получилось', 'It didn’t work')}: ${err}`
                : T('Кружок не ушёл', 'The circle didn’t send')}
          </Text>

          {/* Ряд действий. Все они внутри окна, а значит внутри своих границ, — и нажимаются. */}
          <View style={s.actions}>
            {stage === 'failed' ? (
              /*
                Неудачи две, и путь из них разный. НЕ УЕХАЛО — файл цел, повторяем отправку и
                переснимать нечего. НЕ ЗАПИСАЛОСЬ — файла нет, и единственное осмысленное действие
                это попробовать поднять камеру заново. Одна кнопка, два смысла, оба честные;
                тупика — «не получилось, и всё» — нет ни в одном из них.
              */
              <>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={clip.current ? T('Удалить', 'Discard') : T('Закрыть', 'Close')}
                  onPress={close}
                  style={s.side}
                >
                  <Text style={s.sideText}>
                    {clip.current ? T('Удалить', 'Discard') : T('Закрыть', 'Close')}
                  </Text>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={clip.current ? T('Отправить ещё раз', 'Send again') : T('Ещё раз', 'Try again')}
                  onPress={clip.current ? () => { send().catch(() => {}); } : again}
                  style={[s.big, s.bigSend]}
                >
                  {clip.current ? <IconSend size={22} /> : <Text style={s.retry}>↻</Text>}
                </Pressable>
              </>
            ) : (
              <>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={T('Закрыть', 'Close')}
                  onPress={close}
                  style={s.side}
                >
                  <Text style={s.sideText}>{T('Закрыть', 'Close')}</Text>
                </Pressable>

                {stage === 'recording' ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={T('Готово', 'Done')}
                    accessibilityState={{ disabled: ms < MIN_MS }}
                    disabled={ms < MIN_MS}
                    onPress={finish}
                    style={[s.big, s.bigStop, ms < MIN_MS && s.off]}
                  >
                    <View style={s.square} />
                  </Pressable>
                ) : stage === 'sending' ? (
                  /* Пустое место вместо кнопки: погашенная кнопка записи здесь читалась бы как
                     «можно снять ещё раз», а снимать в этот момент нечего — файл уезжает. */
                  <View style={s.big} />
                ) : (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={T('Записать', 'Record')}
                    accessibilityState={{ disabled: stage !== 'ready' }}
                    disabled={stage !== 'ready'}
                    onPress={() => { record().catch(() => {}); }}
                    style={[s.big, s.bigRec, stage !== 'ready' && s.off]}
                  >
                    {stage === 'warming'
                      ? <ActivityIndicator size="small" color={color.onPrimary} />
                      : <View style={s.round} />}
                  </Pressable>
                )}
              </>
            )}
            {/* Место справа — чтобы главная кнопка стояла по центру, а не съезжала от соседей. */}
            <View style={s.side} pointerEvents="none" />
          </View>
        </View>
      </Modal>
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
 * Играет по нажатию, а не сам: кружок со звуком, заигравший, пока человек листает ленту в тихом
 * месте, — это не оживление, а неприятность.
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

  screen: {
    flex: 1, backgroundColor: color.ink,
    alignItems: 'center', justifyContent: 'center', gap: 18, paddingHorizontal: 24,
  },
  frame: {
    width: PREVIEW, height: PREVIEW, borderRadius: PREVIEW / 2, overflow: 'hidden',
    borderWidth: 3, borderColor: color.neutral400, backgroundColor: '#000',
  },
  /** Красный ободок — единственный признак, что идёт запись, и он должен читаться с одного взгляда. */
  frameLive: { borderColor: color.primary },
  blank: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center' },

  timer: { fontSize: 20, color: color.onPrimary, fontVariant: ['tabular-nums'], minHeight: 24 },
  say: { fontSize: 14, color: color.neutral300, textAlign: 'center', minHeight: 40 },

  actions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', alignSelf: 'stretch' },
  side: { width: 88 },
  sideText: { fontSize: 15, color: color.neutral300 },
  big: { width: 72, height: 72, borderRadius: 36, alignItems: 'center', justifyContent: 'center' },
  bigRec: { backgroundColor: color.primary },
  bigStop: { backgroundColor: color.onPrimary },
  bigSend: { backgroundColor: color.primary },
  /** Недоступная кнопка не исчезает, а гаснет: пропавшая кнопка читается как поломка. */
  off: { opacity: 0.4 },
  retry: { fontSize: 26, color: color.onPrimary },
  round: { width: 28, height: 28, borderRadius: 14, backgroundColor: color.onPrimary },
  square: { width: 24, height: 24, borderRadius: 4, backgroundColor: color.primary },

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
