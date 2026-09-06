import React, { useRef, useState } from 'react';
import {
  ActivityIndicator, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';
import { useKeyboardInset, dockBottom } from '../src/keyboard';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as DocumentPicker from 'expo-document-picker';
import { appendUploadFile } from '../src/upload-file';
import { group, newIdem, type GroupReportReason, type GroupReportResult,
  type ReportEvidence } from '../src/api';
import { useOnb } from '../src/state';
import { T, useLang } from '../src/i18n';
import { IconCheckCircle, IconChevronLeft, IconChevronRight, IconClip, IconTrash } from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { color, radius as rad, space, type } from '../src/theme';

type PickedEvidence = DocumentPicker.DocumentPickerAsset;

const REASONS: { key: GroupReportReason; label: () => string }[] = [
  { key: 'inappropriate_behaviour', label: () => T('Неприемлемое поведение', 'Inappropriate behaviour') },
  { key: 'insults_or_humiliation', label: () => T('Оскорбления или унижение', 'Insults or humiliation') },
  { key: 'harassment_or_threats', label: () => T('Преследование или угрозы', 'Harassment or threats') },
  { key: 'fake_profile', label: () => T('Поддельный профиль', 'Fake profile') },
  { key: 'rule_violation', label: () => T('Нарушение правил', 'Rule violation') },
];

export default function GroupReportScreen() {
  useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх экрана — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const st = useOnb();
  const params = useLocalSearchParams<{ gid?: string; title?: string }>();
  const gid = String(params.gid || '').trim();
  const groupTitle = String(params.title || '').trim();
  const me = String(st.profile.name || '').trim();

  const [reason, setReason] = useState<GroupReportReason | ''>('');
  const [details, setDetails] = useState('');
  const [attachment, setAttachment] = useState<PickedEvidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [sent, setSent] = useState<GroupReportResult | null>(null);
  const idem = useRef(newIdem('group-report'));

  const pickEvidence = async () => {
    if (busy) return;
    setError('');
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: [
          'image/*', 'video/*', 'application/pdf', 'text/plain', 'application/msword',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        ],
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (!result.canceled && result.assets[0]) setAttachment(result.assets[0]);
    } catch {
      setError(T('Не удалось открыть файл.', 'Could not open the file.'));
    }
  };

  const uploadEvidence = async (asset: PickedEvidence): Promise<ReportEvidence> => {
    const form = new FormData();
    if (Platform.OS === 'web' && asset.file) {
      form.append('file', asset.file, asset.name);
    } else {
      await appendUploadFile(form, asset.uri, asset.name || `evidence-${Date.now()}`,
        asset.mimeType || 'application/octet-stream');
    }
    const uploaded = await group.uploadReportEvidence(form);
    if (!uploaded?.ok || !uploaded.id || !uploaded.url || !uploaded.name || !uploaded.mime_type) {
      throw new Error(String(uploaded?.error || 'EVIDENCE_UPLOAD_FAILED'));
    }
    return uploaded as ReportEvidence;
  };

  const submit = async () => {
    if (!gid || !me || !reason || busy) return;
    setBusy(true);
    setError('');
    try {
      const evidence = attachment ? [await uploadEvidence(attachment)] : [];
      const result = await group.report(gid, me, reason, details.trim(), evidence, idem.current);
      if (!result?.ok) throw new Error(String(result?.error || 'REPORT_FAILED'));
      setSent(result);
    } catch (e) {
      const code = String((e as any)?.message || '');
      setError(code.includes('EVIDENCE_TOO_LARGE')
        ? T('Файл должен быть меньше 12 МБ.', 'The file must be smaller than 12 MB.')
        : T('Не удалось отправить жалобу. Попробуйте ещё раз.', 'Could not send the report. Try again.'));
    } finally {
      setBusy(false);
    }
  };

  if (sent) {
    return (
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <Header title="" onBack={() => router.dismissTo('/home')} />
        <ScrollView contentContainerStyle={s.successBody}>
          <IconCheckCircle size={48} />
          <Text style={s.successTitle}>{T('Мы получили вашу жалобу', 'We received your report')}</Text>
          <Text style={s.successText}>{T('Спасибо, что сообщили нам', 'Thank you for letting us know')}</Text>
          <View style={s.caseBand}>
            <Text style={s.caseLabel}>{T('Номер обращения', 'Case number')}</Text>
            <View style={s.caseRow}>
              <Text style={s.caseNumber}>{sent.case_no || sent.id || ''}</Text>
              <Text style={s.copyMark}>⧉</Text>
            </View>
          </View>
          <View style={s.statusHead}>
            <Text style={s.sectionTitle}>{T('Статус', 'Status')}</Text>
            <Text style={s.progressBadge}>{T('В работе', 'In progress')}</Text>
          </View>
          <View style={s.panel}>
            <Text style={s.panelTitle}>{T('Что дальше', "What's next")}</Text>
            <StatusRow state="done" title={T('Жалоба получена', 'Report received')}
                       note={reportReceivedAt(sent.at)} trailing={T('Готово', 'Done')} />
            <StatusRow state="active" title={T('Проверка командой безопасности', 'Under review by the safety team')}
                       note={T('1 ч', '1 h')} trailing={T('В работе', 'In progress')} />
            <StatusRow title={T('Действия и решение', 'Actions and decision')} trailing={T('Скоро', 'Soon')} />
            <StatusRow title={T('Ответ вам', 'Reply to you')} trailing={T('Скоро', 'Soon')} />
          </View>
          <View style={s.panel}>
            <Text style={s.sectionTitle}>{T('Применённые меры защиты', 'Applied protective measures')}</Text>
            <ProtectionRow text={T('Участники заблокированы', 'Members blocked')} />
            <ProtectionRow text={T('Ваш профиль скрыт от них', 'Your profile is hidden from them')} />
            <ProtectionRow text={T('Их сообщения заглушены', 'Their messages are muted')} />
          </View>
          <Text style={[s.sectionTitle, s.helpTitle]}>{T('Нужна срочная помощь?', 'Need urgent help?')}</Text>
          <View style={s.panel}>
            <HelpRow title={T('Экстренная помощь', 'Emergency Assistance')}
                     sub={T('Связаться с экстренными службами', 'Contact emergency services')}
                     onPress={() => Linking.openURL('tel:112')} />
            <View style={s.rule} />
            <HelpRow title={T('Центр поддержки', 'Support Center')}
                     sub={T('Связаться с нашей командой поддержки', 'Chat with our support team')}
                     onPress={() => router.navigate('/profile/safety')} />
          </View>
        </ScrollView>
        <BottomNav />
      </View>
    );
  }

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <Header title={T('Сообщить о проблеме', 'Report a problem')} onBack={() => router.back()} />
      <ScrollView contentContainerStyle={[s.body, { paddingBottom: kb }]} keyboardShouldPersistTaps="handled">
        {groupTitle ? <Text style={s.context} numberOfLines={2}>{groupTitle}</Text> : null}
        <Text style={s.sectionTitle}>{T('Что произошло?', 'What happened?')}</Text>
        <View style={s.reasons}>
          {REASONS.map((item) => {
            const selected = item.key === reason;
            return (
              <Pressable key={item.key} accessibilityRole="radio"
                         accessibilityState={{ selected }} style={s.reason}
                         onPress={() => setReason(item.key)}>
                <View style={[s.radio, selected && s.radioOn]}>
                  {selected ? <View style={s.radioDot} /> : null}
                </View>
                <Text style={s.reasonText}>{item.label()}</Text>
              </Pressable>
            );
          })}
        </View>

        <View style={s.inputHead}>
          <Text style={s.sectionTitle}>{T('Опишите ситуацию', 'Describe your situation')}</Text>
          <Text style={s.counter}>{details.length}/500</Text>
        </View>
        <TextInput value={details} onChangeText={setDetails} maxLength={500} multiline
                   textAlignVertical="top"
                   placeholder={T('Расскажите, что произошло. Добавьте важные детали: время, место и сообщения.',
                                  'Tell us what happened. Include important details such as time, location, and messages.')}
                   placeholderTextColor={color.neutral400} style={s.input} />

        <Text style={s.sectionTitle}>{T('Приложить доказательство (необязательно)', 'Attach evidence (optional)')}</Text>
        {attachment ? (
          <View style={s.fileRow}>
            <IconClip />
            <View style={{ flex: 1 }}>
              <Text style={s.fileName} numberOfLines={1}>{attachment.name}</Text>
              <Text style={s.fileMeta}>{formatBytes(attachment.size || 0)}</Text>
            </View>
            <Pressable accessibilityRole="button" accessibilityLabel={T('Удалить файл', 'Remove file')}
                       hitSlop={10} onPress={() => setAttachment(null)}>
              <IconTrash c={color.danger} />
            </Pressable>
          </View>
        ) : (
          <Pressable accessibilityRole="button" style={s.attach} onPress={pickEvidence}>
            <IconClip c={color.fg} />
            <Text style={s.attachText}>{T('Фото / Видео / Документы', 'Photo / Video / Docs')}</Text>
          </Pressable>
        )}

        <View style={s.safetyBand}>
          <Text style={s.sectionTitle}>{T('Немедленные меры безопасности', 'Immediate safety measures')}</Text>
          <Text style={s.safetyText}>
            {T('Эти меры будут применены сразу после отправки жалобы.',
               'These protections will be applied immediately after you submit your report.')}
          </Text>
          <ProtectionRow text={T('Контакт с участниками ограничен', 'Restricted contact from users')} />
          <ProtectionRow text={T('Усиленная приватность профиля', 'Enhanced profile privacy')} />
          <ProtectionRow text={T('Сообщения временно отключены', 'Messaging temporarily disabled')} />
        </View>
        {error ? <Text accessibilityRole="alert" style={s.error}>{error}</Text> : null}
      </ScrollView>
      <Pressable accessibilityRole="button" disabled={!reason || busy}
                 style={[s.submit, (!reason || busy) && s.disabled]} onPress={submit}>
        {busy ? <ActivityIndicator color={color.onPrimary} />
              : <Text style={s.submitText}>{T('Отправить жалобу', 'Send report')}</Text>}
      </Pressable>
      <BottomNav />
    </View>
  );
}

function Header({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <View style={s.head}>
      <Pressable accessibilityRole="button" accessibilityLabel={T('Назад', 'Back')} style={s.back} onPress={onBack}>
        <IconChevronLeft />
      </Pressable>
      <Text style={s.headTitle} numberOfLines={1}>{title}</Text>
      <View style={s.back} />
    </View>
  );
}

function StatusRow({ title, note, trailing, state = 'pending' }: {
  title: string; note?: string; trailing?: string; state?: 'done' | 'active' | 'pending';
}) {
  return (
    <View style={s.statusRow}>
      <View style={[s.statusDot, state === 'done' && s.statusDotDone, state === 'active' && s.statusDotActive]}>
        {state === 'done' ? <Text style={s.statusCheck}>✓</Text> : null}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[s.statusText, state !== 'pending' && s.statusTextOn]}>{title}</Text>
        {note ? <Text style={s.statusNote}>{note}</Text> : null}
      </View>
      {trailing ? <Text style={[s.statusTrailing, state === 'done' && s.statusTrailingDone,
                               state === 'active' && s.statusTrailingActive]}>{trailing}</Text> : null}
    </View>
  );
}

function ProtectionRow({ text }: { text: string }) {
  return (
    <View style={s.protectionRow}>
      <View style={s.protectionCheck}><Text style={s.protectionCheckText}>✓</Text></View>
      <Text style={s.measureText}>{text}</Text>
    </View>
  );
}

function HelpRow({ title, sub, onPress }: { title: string; sub: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" style={s.helpRow} onPress={onPress}>
      <View style={{ flex: 1 }}>
        <Text style={s.helpRowTitle}>{title}</Text>
        <Text style={s.helpRowSub}>{sub}</Text>
      </View>
      <IconChevronRight c={color.muted} />
    </Pressable>
  );
}

function reportReceivedAt(at?: number) {
  const date = at ? new Date(at * 1000) : new Date();
  const time = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  return T(`сегодня · ${time}`, `today · ${time}`);
}

function formatBytes(value: number) {
  if (!value) return '';
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.bg },
  head: { height: 56, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16 },
  back: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  headTitle: { flex: 1, ...type.title, color: color.fg, textAlign: 'center' } as any,
  body: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 24, gap: 14 },
  successBody: { paddingHorizontal: 20, paddingTop: 18, paddingBottom: 18, alignItems: 'center', gap: 12 },
  context: { ...type.bodySmall, color: color.muted } as any,
  sectionTitle: { ...type.title, color: color.fg } as any,
  reasons: { borderTopWidth: 1, borderTopColor: color.border },
  reason: { minHeight: 52, flexDirection: 'row', alignItems: 'center', gap: 12,
    borderBottomWidth: 1, borderBottomColor: color.border },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: color.neutral300,
    alignItems: 'center', justifyContent: 'center' },
  radioOn: { borderColor: color.primary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: color.primary },
  reasonText: { flex: 1, ...type.body, color: color.fg } as any,
  inputHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  counter: { ...type.caption, color: color.muted } as any,
  input: { minHeight: 120, borderWidth: 1, borderColor: color.neutral300, borderRadius: rad.md,
    backgroundColor: color.card, padding: 14, color: color.fg, ...type.body } as any,
  attach: { height: 54, borderWidth: 1, borderColor: color.neutral300, borderRadius: rad.md,
    backgroundColor: color.card, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10 },
  attachText: { ...type.button, color: color.fg } as any,
  fileRow: { minHeight: 64, borderWidth: 1, borderColor: color.border, borderRadius: rad.md,
    backgroundColor: color.card, paddingHorizontal: 14, flexDirection: 'row', alignItems: 'center', gap: 12 },
  fileName: { ...type.body, color: color.fg } as any,
  fileMeta: { ...type.caption, color: color.muted } as any,
  safetyBand: { backgroundColor: color.infoBg, borderRadius: rad.md, padding: 14, gap: 8 },
  safetyText: { ...type.bodySmall, color: color.infoText } as any,
  error: { ...type.bodySmall, color: color.danger } as any,
  submit: { height: 54, marginHorizontal: 20, marginBottom: 18, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center' },
  submitText: { ...type.button, color: color.onPrimary } as any,
  disabled: { opacity: 0.45 },
  successTitle: { ...type.h2, color: color.fg, textAlign: 'center' } as any,
  successText: { ...type.body, color: color.muted, textAlign: 'center' } as any,
  caseBand: { width: '100%', backgroundColor: color.card, borderRadius: rad.md, padding: 16, gap: 4 },
  caseRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  caseLabel: { ...type.caption, color: color.muted } as any,
  caseNumber: { ...type.title, color: color.fg } as any,
  copyMark: { ...type.body, color: color.primary } as any,
  statusHead: { width: '100%', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  progressBadge: { ...type.caption, color: color.warnText, backgroundColor: color.warnBg,
    borderRadius: rad.full, paddingHorizontal: 10, paddingVertical: 4 } as any,
  panel: { width: '100%', backgroundColor: color.card, borderRadius: rad.md, padding: 14, gap: 10 },
  panelTitle: { ...type.title, color: color.fg } as any,
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 34 },
  statusDot: { width: 20, height: 20, borderRadius: 10, borderWidth: 2, borderColor: color.neutral300,
    alignItems: 'center', justifyContent: 'center' },
  statusDotDone: { borderColor: color.successText, backgroundColor: color.successText },
  statusDotActive: { borderColor: color.primary, borderTopColor: color.border },
  statusCheck: { color: color.onPrimary, fontSize: 12, fontWeight: '700' },
  statusText: { ...type.body, color: color.muted } as any,
  statusTextOn: { color: color.fg, fontWeight: '600' },
  statusNote: { ...type.caption, color: color.muted, marginTop: 2 } as any,
  statusTrailing: { ...type.caption, color: color.neutral400 } as any,
  statusTrailingDone: { color: color.successText },
  statusTrailingActive: { color: color.warnText },
  protectionRow: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  protectionCheck: { width: 18, height: 18, borderRadius: 9, backgroundColor: color.successText,
    alignItems: 'center', justifyContent: 'center' },
  protectionCheckText: { color: color.onPrimary, fontSize: 11, fontWeight: '700' },
  measureText: { flex: 1, ...type.bodySmall, color: color.successText } as any,
  helpTitle: { width: '100%', marginTop: 2 },
  helpRow: { minHeight: 52, flexDirection: 'row', alignItems: 'center', gap: 10 },
  helpRowTitle: { ...type.body, color: color.fg, fontWeight: '600' } as any,
  helpRowSub: { ...type.caption, color: color.muted, marginTop: 2 } as any,
  rule: { height: 1, backgroundColor: color.border },
});
