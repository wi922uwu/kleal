import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { agent, newIdem } from '../api';
import { T } from '../i18n';
import { color, radius as rad, space, type } from '../theme';
import { Sheet } from './Sheet';

export type ReportTarget = {
  about: string;
  messageId: string;
  text?: string;
  threadType: 'direct' | 'group';
  threadId: string;
};

const REASONS = [
  ['harassment', () => T('Домогательства или оскорбления', 'Harassment or abuse'),
    () => T('Угрозы, оскорбления, нежелательные предложения', 'Threats, insults, unwanted advances')],
  ['spam', () => T('Спам или мошенничество', 'Spam or a scam'),
    () => T('Продажи, ссылки, просьбы о деньгах', 'Selling, links, asking for money')],
  ['fake', () => T('Поддельный профиль', 'Fake profile'),
    () => T('Это не тот человек, что на фотографиях', 'Not the person in the photos')],
  ['other', () => T('Другое', 'Something else'),
    () => T('Расскажите своими словами', 'Tell us in your own words')],
] as const;

export function ReportMessageSheet({
  visible, me, target, onClose, onSent,
}: {
  visible: boolean;
  me: string;
  target: ReportTarget | null;
  onClose: () => void;
  onSent: () => void;
}) {
  const [reason, setReason] = useState('');
  const [details, setDetails] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!visible) return;
    setReason('');
    setDetails('');
    setError('');
    setBusy(false);
  }, [visible, target?.messageId]);

  const submit = async () => {
    if (!target || !reason || busy) return;
    setBusy(true);
    setError('');
    try {
      const r: any = await agent.report(
        me, target.about, reason, details, newIdem('report'), target.messageId,
        target.threadType, target.threadId,
      );
      if (!r?.ok) throw new Error(String(r?.error || 'REPORT_FAILED'));
      onClose();
      onSent();
    } catch {
      setError(T('Не удалось отправить жалобу. Попробуйте ещё раз.', 'Could not send the report. Try again.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet visible={visible} onClose={busy ? () => {} : onClose} title={T('Пожаловаться на сообщение', 'Report this message')}>
      {REASONS.map(([key, label, note]) => (
        <Pressable
          key={key}
          accessibilityRole="radio"
          accessibilityState={{ selected: reason === key }}
          style={[s.reason, reason === key && s.reasonSelected]}
          onPress={() => setReason(key)}
        >
          <View style={[s.radio, reason === key && s.radioSelected]}>
            {reason === key ? <View style={s.radioDot} /> : null}
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.reasonLabel}>{label()}</Text>
            <Text style={s.reasonNote}>{note()}</Text>
          </View>
        </Pressable>
      ))}

      {reason === 'other' ? (
        <TextInput
          value={details}
          onChangeText={setDetails}
          placeholder={T('Что произошло?', 'What happened?')}
          placeholderTextColor={color.neutral400}
          multiline
          maxLength={1000}
          style={s.input}
        />
      ) : null}

      {error ? <Text style={s.error}>{error}</Text> : null}
      <Pressable
        accessibilityRole="button"
        disabled={!reason || busy}
        style={[s.submit, (!reason || busy) && s.disabled]}
        onPress={submit}
      >
        {busy ? <ActivityIndicator color={color.onPrimary} />
              : <Text style={s.submitText}>{T('Отправить жалобу', 'Send report')}</Text>}
      </Pressable>
    </Sheet>
  );
}

export function ReportSentBanner({ about }: { about: string }) {
  return (
    <View style={s.notice} accessibilityRole="alert">
      <Text style={s.noticeTitle}>{T('Жалоба отправлена', 'Report sent')}</Text>
      <Text style={s.noticeText}>
        {T('Её проверит человек в течение 24 часов. Пользователь не узнает, кто пожаловался.',
           'A person reads it within 24 hours. The person is not told who reported them.')}
      </Text>
      <Text style={s.noticeHint}>
        {T(`Вы можете продолжить общение или отдельно заблокировать ${about}. Жалоба сама этого не делает.`,
           `You can keep chatting or block ${about} separately. Reporting does not do that on its own.`)}
      </Text>
    </View>
  );
}

export function BlockConfirmSheet({
  visible, name, busy, onClose, onConfirm,
}: {
  visible: boolean;
  name: string;
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <Sheet visible={visible} onClose={busy ? () => {} : onClose} title={T(`Заблокировать ${name}?`, `Block ${name}?`)}>
      <Text style={s.blockNote}>
        {T(
          'Этот человек не сможет писать вам и видеть ваши интенты, а вы исчезнете из его выдачи. Общий план будет отменён для вас обоих.',
          'They cannot message you or see your intents, and you disappear from theirs. Any plan you share is cancelled for both of you.',
        )}
      </Text>
      <Pressable accessibilityRole="button" style={s.notNow} onPress={onClose} disabled={busy}>
        <Text style={s.notNowText}>{T('Не сейчас', 'Not now')}</Text>
      </Pressable>
      <Pressable accessibilityRole="button" style={s.block} onPress={onConfirm} disabled={busy}>
        {busy ? <ActivityIndicator color={color.primary} />
              : <Text style={s.blockText}>{T(`Заблокировать ${name}`, `Block ${name}`)}</Text>}
      </Pressable>
    </Sheet>
  );
}

export function ReadOnlyNotice({ text }: { text: string }) {
  return (
    <View style={s.readOnly} accessibilityRole="alert">
      <Text style={s.readOnlyText}>{text}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  reason: { flexDirection: 'row', gap: 12, paddingVertical: 10, paddingHorizontal: 8,
    borderRadius: rad.md, borderWidth: 1, borderColor: 'transparent' },
  reasonSelected: { borderColor: color.primary, backgroundColor: color.neutral100 },
  radio: { width: 20, height: 20, borderRadius: 10, borderWidth: 1.5, borderColor: color.neutral400,
    alignItems: 'center', justifyContent: 'center', marginTop: 2 },
  radioSelected: { borderColor: color.primary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: color.primary },
  reasonLabel: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  reasonNote: { ...type.caption, color: color.muted, marginTop: 2 } as any,
  input: { minHeight: 92, borderWidth: 1, borderColor: color.neutral300, borderRadius: rad.md,
    padding: 12, color: color.fg, textAlignVertical: 'top', ...type.body } as any,
  submit: { height: 52, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: space.sm },
  disabled: { opacity: 0.45 },
  submitText: { ...type.labelMedium, color: color.onPrimary, fontWeight: '700' } as any,
  error: { ...type.caption, color: color.primary } as any,
  notice: { marginHorizontal: 16, marginVertical: 8, padding: 14, borderRadius: rad.md,
    backgroundColor: color.card, borderWidth: 1, borderColor: color.border },
  noticeTitle: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  noticeText: { ...type.caption, color: color.muted, marginTop: 3 } as any,
  noticeHint: { ...type.caption, color: color.fg, marginTop: 10 } as any,
  blockNote: { ...type.body, color: color.muted, marginBottom: space.sm } as any,
  notNow: { height: 48, borderRadius: rad.full, backgroundColor: color.fg,
    alignItems: 'center', justifyContent: 'center' },
  notNowText: { ...type.labelMedium, color: color.card, fontWeight: '700' } as any,
  block: { height: 48, borderRadius: rad.full, backgroundColor: color.neutral100,
    alignItems: 'center', justifyContent: 'center' },
  blockText: { ...type.labelMedium, color: color.primary, fontWeight: '700' } as any,
  readOnly: { marginHorizontal: 16, marginVertical: 8, padding: 12, borderRadius: rad.md,
    backgroundColor: color.warnBg },
  readOnlyText: { ...type.caption, color: color.fg, textAlign: 'center' } as any,
});
