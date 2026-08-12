import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioPlayer,
  useAudioPlayerStatus,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { mediaUrl, speech, VoicePayload } from './api';
import { T } from './i18n';
import { color } from './theme';
import { IconMic, IconPlay, IconSend } from './components/icons';

type DictationPhase = 'idle' | 'recording' | 'transcribing';
type MessagePhase = 'idle' | 'recording' | 'preview' | 'uploading';

const MAX_DURATION_MS = 60000;

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
    form.append('file', { uri, name: `voice-${Date.now()}.m4a`, type: 'audio/mp4' } as any);
  }
  return form;
};

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
    Alert.alert(T('Не удалось распознать речь', 'Could not transcribe speech'), message);
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
        ? T('Речь не обнаружена. Попробуйте ещё раз.', 'No speech was detected. Try again.')
        : T('Проверьте соединение и повторите запись.', 'Check your connection and record again.'));
    } finally {
      stopping.current = false;
    }
  }, [fail, onTranscript, phase, recorder]);

  const start = useCallback(async () => {
    if (disabled || phase !== 'idle') return;
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted) {
        return fail(T('Разрешите доступ к микрофону в настройках устройства.', 'Allow microphone access in device settings.'));
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setPhase('recording');
    } catch {
      fail(T('Не удалось начать запись.', 'Could not start recording.'));
    }
  }, [disabled, fail, phase, recorder]);

  useEffect(() => {
    if (phase === 'recording' && recorderState.durationMillis >= MAX_DURATION_MS) stop();
  }, [phase, recorderState.durationMillis, stop]);

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
      accessibilityLabel={recording ? T('Остановить запись', 'Stop recording') : T('Голосовой ввод', 'Voice input')}
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
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder, 100);
  const [phase, setPhase] = useState<MessagePhase>('idle');
  const [uri, setUri] = useState('');
  const [durationMillis, setDurationMillis] = useState(0);
  const stopping = useRef(false);

  const reset = useCallback(() => {
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
      setPhase('preview');
    } catch {
      fail(T('Запись не сохранена', 'Recording was not saved'), T('Попробуйте записать ещё раз.', 'Try recording again.'));
    } finally {
      stopping.current = false;
    }
  }, [fail, phase, recorder, recorderState.durationMillis]);

  const start = useCallback(async () => {
    if (disabled || phase !== 'idle') return;
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted) {
        return Alert.alert(T('Нет доступа к микрофону', 'Microphone access is disabled'), T(
          'Разрешите доступ к микрофону в настройках устройства.', 'Allow microphone access in device settings.'
        ));
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
      setPhase('recording');
    } catch {
      fail(T('Не удалось начать запись', 'Could not start recording'), T('Попробуйте ещё раз.', 'Try again.'));
    }
  }, [disabled, fail, phase, recorder]);

  const send = useCallback(async () => {
    if (phase !== 'preview' || !uri) return;
    setPhase('uploading');
    try {
      const result = await speech.uploadVoice(await audioForm(uri), durationMillis);
      const transcript = String(result?.transcript || result?.text || '').trim();
      if (!result?.id || !result?.url || !transcript) throw new Error('INVALID_VOICE_RESPONSE');
      await onSend({
        id: String(result.id), url: String(result.url), duration_ms: Number(result.duration_ms),
        transcript, mime_type: String(result.mime_type || 'audio/mp4'), language: result.language,
      });
      reset();
    } catch (error) {
      setPhase('preview');
      const code = String((error as any)?.body?.error || (error as any)?.message || '');
      Alert.alert(
        T('Не удалось отправить голосовое', 'Could not send voice message'),
        code === 'NO_SPEECH'
          ? T('Речь не обнаружена. Запишите сообщение ещё раз.', 'No speech was detected. Record the message again.')
          : T('Проверьте соединение и повторите отправку.', 'Check your connection and try sending again.')
      );
    }
  }, [durationMillis, onSend, phase, reset, uri]);

  useEffect(() => {
    if (phase === 'recording' && recorderState.durationMillis >= MAX_DURATION_MS) stop();
  }, [phase, recorderState.durationMillis, stop]);

  return {
    phase, uri, durationMillis: phase === 'recording' ? recorderState.durationMillis : durationMillis,
    start, stop, cancel: reset, send, disabled: disabled || phase === 'uploading',
  };
}

export type VoiceMessage = ReturnType<typeof useVoiceMessage>;

/**
 * Проигрыватель — и в пузыре сообщения, и в композере перед отправкой.
 *
 * `grow` РАЗДЕЛЯЕТ эти два случая, и разделять их обязательно. В композере проигрыватель стоит в
 * СТРОКЕ рядом с «удалить» и «отправить», и там `flex: 1` значит «займи оставшуюся ШИРИНУ». В
 * пузыре он стоит в КОЛОНКЕ над ссылкой «Показать текст», и тот же `flex: 1` значит «займи
 * оставшуюся ВЫСОТУ» — из-за чего шестисекундное голосовое разворачивалось красным полотном почти
 * на весь экран (снято 12 августа). Одного стиля на оба случая не бывает.
 */
function AudioPlay({ source, durationMs, mine = false, grow = false }: { source: string; durationMs: number; mine?: boolean; grow?: boolean }) {
  const player = useAudioPlayer(source, { updateInterval: 200 });
  const status = useAudioPlayerStatus(player);
  const total = status.duration > 0 ? status.duration * 1000 : durationMs;
  const current = Math.min(total, status.currentTime * 1000);
  const progress = total > 0 ? Math.max(0, Math.min(1, current / total)) : 0;

  useEffect(() => {
    if (status.didJustFinish) player.seekTo(0);
  }, [player, status.didJustFinish]);

  const toggle = () => {
    if (status.playing) player.pause();
    else player.play();
  };
  return (
    <View style={[s.playRow, grow && s.playRowGrow]}>
      <Pressable accessibilityRole="button" accessibilityLabel={status.playing ? T('Пауза', 'Pause') : T('Воспроизвести', 'Play')} onPress={toggle} style={s.playButton}>
        {status.playing ? <View style={s.pause}><View style={s.pauseBar} /><View style={s.pauseBar} /></View> : <IconPlay size={18} c={mine ? color.onPrimary : color.primary} />}
      </Pressable>
      <View style={s.track}><View style={[s.trackFill, mine && s.trackFillMine, { width: `${progress * 100}%` }]} /></View>
      <Text style={[s.duration, mine && { color: color.onPrimary }]}>{formatDuration(total || durationMs)}</Text>
    </View>
  );
}

export function VoiceMessageControl({ voice }: { voice: VoiceMessage }) {
  if (voice.phase === 'preview' || voice.phase === 'uploading') {
    return (
      <View style={s.preview}>
        <AudioPlay source={voice.uri} durationMs={voice.durationMillis} grow />
        <Pressable accessibilityRole="button" accessibilityLabel={T('Удалить запись', 'Delete recording')} onPress={voice.cancel} disabled={voice.disabled} style={s.previewAction}>
          <Text style={s.delete}>✕</Text>
        </Pressable>
        <Pressable accessibilityRole="button" accessibilityLabel={T('Отправить', 'Send')} onPress={voice.send} disabled={voice.disabled} style={[s.send, voice.disabled && { opacity: 0.55 }]}>
          {voice.phase === 'uploading' ? <ActivityIndicator size="small" color={color.onPrimary} /> : <IconSend size={17} />}
        </Pressable>
      </View>
    );
  }
  const recording = voice.phase === 'recording';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={recording ? T('Остановить запись', 'Stop recording') : T('Записать голосовое', 'Record voice message')}
      onPress={recording ? voice.stop : voice.start}
      disabled={voice.disabled}
      style={[s.iconButton, recording && s.recording]}
      hitSlop={8}
    >
      {recording ? <><View style={s.stop} /><Text style={s.timer}>{formatDuration(voice.durationMillis)}</Text></> : <IconMic />}
    </Pressable>
  );
}

export function VoiceBubble({ voice, mine = false }: { voice: VoicePayload; mine?: boolean }) {
  const [showTranscript, setShowTranscript] = useState(false);
  return (
    <View style={[s.bubble, mine && s.bubbleMine]}>
      <AudioPlay source={mediaUrl(voice.url)} durationMs={voice.duration_ms} mine={mine} />
      <Pressable accessibilityRole="button" onPress={() => setShowTranscript((v) => !v)}>
        <Text style={[s.transcriptLink, mine && { color: color.onPrimary }]}>
          {showTranscript ? T('Скрыть текст', 'Hide transcript') : T('Показать текст', 'Show transcript')}
        </Text>
      </Pressable>
      {showTranscript ? <Text style={[s.transcript, mine && { color: color.onPrimary }]}>{voice.transcript}</Text> : null}
    </View>
  );
}

const s = StyleSheet.create({
  iconButton: { minWidth: 28, height: 34, alignItems: 'center', justifyContent: 'center' },
  recording: { minWidth: 76, flexDirection: 'row', gap: 7 },
  stop: { width: 11, height: 11, borderRadius: 2, backgroundColor: color.primary },
  timer: { width: 46, fontSize: 12, color: color.primary, fontVariant: ['tabular-nums'] },
  preview: { flex: 1, height: 46, flexDirection: 'row', alignItems: 'center', gap: 8 },
  previewAction: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  delete: { fontSize: 18, color: color.muted },
  send: { width: 36, height: 36, borderRadius: 18, backgroundColor: color.primary, alignItems: 'center', justifyContent: 'center' },
  playRow: { minWidth: 172, flexDirection: 'row', alignItems: 'center', gap: 9 },
  /** Только в композере: занять оставшуюся ШИРИНУ строки. В пузыре это растянуло бы высоту. */
  playRowGrow: { flex: 1 },
  playButton: { width: 30, height: 30, alignItems: 'center', justifyContent: 'center' },
  pause: { flexDirection: 'row', gap: 3 },
  pauseBar: { width: 3, height: 14, borderRadius: 1, backgroundColor: color.primary },
  track: { flex: 1, height: 3, borderRadius: 2, backgroundColor: color.neutral300, overflow: 'hidden' },
  trackFill: { height: 3, borderRadius: 2, backgroundColor: color.primary },
  trackFillMine: { backgroundColor: color.onPrimary },
  duration: { width: 38, fontSize: 11, color: color.muted, fontVariant: ['tabular-nums'] },
  bubble: { minWidth: 230, maxWidth: 286, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 16, backgroundColor: color.neutral100 },
  bubbleMine: { backgroundColor: color.primary },
  transcriptLink: { fontSize: 12, color: color.primary, marginTop: 4, fontWeight: '600' },
  transcript: { fontSize: 13, lineHeight: 18, color: color.fg, marginTop: 6 },
});
