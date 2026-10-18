import React, { useEffect, useRef, useState } from 'react';
import { Image, Linking, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useKeyboardInset } from '../src/keyboard';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as DocumentPicker from 'expo-document-picker';
import { appendUploadFile } from '../src/upload-file';
import { agent, group, newIdem, isMe, pidOf, mediaUrl, ensureMe, type GroupReportReason, type GroupReportResult,
  type ReportEvidence } from '../src/api';
import * as Clipboard from 'expo-clipboard';
import { useOnb } from '../src/state';
import { T, useLang, dateLocale, use12h, getLang } from '../src/i18n';
import {
  IconCaseTray, IconLoader, IconCopy, IconPhone, IconHeadset, IconLifeBuoy, IconChevronRight, IconClip, IconTrash, IconAlertTriangle, IconChatWarning, IconShieldAlert, IconUserX, IconShield, IconFilePlus, IconPerson, IconBan, IconCheck, IconClock,
} from '../src/components/icons';
import { BottomNav } from '../src/components/BottomNav';
import { color, font, heading, radius as rad, type } from '../src/theme';
import { GlassPill } from '../src/components/Glass';
import { GlassBack, GlassSurface } from '../src/components/LiquidGlass';
import { useNavCollapse } from '../src/navScroll';

type PickedEvidence = DocumentPicker.DocumentPickerAsset;

/** Причины — ровно пять с кадра GR.55, каждая со своим знаком. */
const REASONS: { key: GroupReportReason; label: () => string; icon: (c: string) => React.ReactNode }[] = [
  { key: 'insults_or_humiliation', label: () => T('Оскорбления или унижение', 'Insults or humiliation', 'Insultos o humillaciones'),
    icon: (c) => <IconAlertTriangle size={18} c={c} /> },
  { key: 'harassment_or_threats', label: () => T('Преследование или угрозы', 'Harassment or threats', 'Acoso o amenazas'),
    icon: (c) => <IconChatWarning size={18} c={c} /> },
  { key: 'unsafe_behaviour' as GroupReportReason, label: () => T('Опасное поведение на встрече', 'Unsafe behaviour at the meetup', 'Comportamiento peligroso en la quedada'),
    icon: (c) => <IconShieldAlert size={18} c={c} /> },
  { key: 'fake_profile', label: () => T('Поддельный профиль', 'Fake profile', 'Perfil falso'),
    icon: (c) => <IconUserX size={18} c={c} /> },
  { key: 'something_else' as GroupReportReason, label: () => T('Другое', 'Something else', 'Otra cosa'),
    icon: (c) => <IconBan size={18} c={c} /> },
];

/**
 * OF.26 — тот же экран для встречи один на один. У сервера там свой, более короткий словарь причин
 * (`REPORT_REASONS` в matching/app.py), поэтому пять причин с кадра сводятся к его ключам, а точная
 * причина с кадра уходит в начале текста — модератор видит её дословно.
 */
const SOLO_REASON: Record<string, string> = {
  insults_or_humiliation: 'harassment',
  harassment_or_threats: 'harassment',
  unsafe_behaviour: 'unsafe',
  fake_profile: 'fake',
  something_else: 'other',
};

/** Меры, которые включаются сразу (GR.55 «When you send this», GR.55a «Already in place»). */
const measures = (who: string) => [
  T(`${who} не сможет тебе писать`, `${who} can’t message you`, `${who} no puede escribirte`),
  T(`${who} не увидит твой профиль`, `${who} can’t see your profile`, `${who} no puede ver tu perfil`),
  T(`Вас с ${who} больше не подберут`, `You won’t be matched with ${who} again`, `No volverás a coincidir con ${who}`),
];

export default function GroupReportScreen() {
  /** Navigation V2: панель сворачивается при прокрутке вниз (NAV.S2). */
  const navCollapse = useNavCollapse();
  const lang = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  /** Android: клавиатура ложится поверх экрана — окно под неё не ужимается. См. src/keyboard.ts. */
  const kb = useKeyboardInset();
  const st = useOnb();
  const params = useLocalSearchParams<{
    gid?: string; title?: string; who?: string; who_id?: string; photo?: string; age?: string; call?: string;
    about?: string; about_id?: string; quote?: string; quote_at?: string;
  }>();
  /** MSG.13b «Report a message»: жалоба на реплику — автор уже известен, сама реплика едет в текст. */
  const quote = String(params.quote || '').trim();
  const quoteAt = Number(params.quote_at || 0);
  const quoteWho = String(params.about || '').trim();
  const gid = String(params.gid || '').trim();
  /** OF.26: без группы, с одним человеком — жалоба после встречи один на один. */
  const soloName = String(params.who || '').trim();
  const soloId = String(params.who_id || '').trim();
  const solo = !gid && !!soloName;
  const me = String(st.profile.name || '').trim();

  const [reason, setReason] = useState<GroupReportReason | ''>('');
  /** GR.55 «Who is this about?» — участники группы, кроме себя; вышедшие тоже (после встречи). */
  const [people, setPeople] = useState<{ name: string; id: string; age?: number; photo?: string }[]>(
    () => (solo ? [{ name: soloName, id: soloId, age: Number(params.age) || undefined,
                     photo: String(params.photo || '') || undefined }] : []));
  /** OF.26: человек один, и он уже отмечен — выбирать не из кого. */
  const [about, setAbout] = useState<{ name: string; id: string } | null>(
    () => (solo ? { name: soloName, id: soloId }
      : quoteWho ? { name: quoteWho, id: String(params.about_id || '').trim() } : null));
  const quoteLine = quote
    ? `[message ${quoteWho}${quoteAt ? ' ' + new Date(quoteAt * 1000).toISOString() : ''}] «${quote}»` : '';
  useEffect(() => {
    if (!gid || !me) return;
    ensureMe().then(() => group.get(gid, me)).then((r: any) => {
      const g = r?.group || {};
      const all = [...(g.members || []), ...(g.departed || [])] as any[];
      setPeople(all.filter((m) => String(m?.name || '') && !isMe(m.name, pidOf(m, 'name'), me))
        .map((m) => ({ name: String(m.name), id: pidOf(m, 'name'), age: m.age, photo: m.photo })));
    }).catch(() => {});
  }, [gid, me]);
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
      setError(T('Не удалось открыть файл.', 'Could not open the file.', 'No se pudo abrir el archivo.'));
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
    if ((!gid && !solo) || !me || !reason || !about || busy) return;
    setBusy(true);
    setError('');
    try {
      const evidence = attachment ? [await uploadEvidence(attachment)] : [];
      if (solo) {
        // Жалоба 1:1 на сервере файлов не принимает и номера обращения не выдаёт. Файл грузится тем
        // же вызовом, что у группы, а его id уходит в тексте — по нему модератор файл и откроет.
        // Номер собирается так же, как сервер собирает его группе: «KLEAL-» + хвост id жалобы.
        const text = [`[${reason}]`, details.trim(),
          evidence[0] ? `[evidence ${evidence[0].id} ${evidence[0].name}]` : ''].filter(Boolean).join(' ');
        const r: any = await agent.report(me, about, SOLO_REASON[reason] || 'other', text, idem.current);
        if (!r?.ok) throw new Error(String(r?.error || 'REPORT_FAILED'));
        const id = String(r.id || '');
        setSent({ ok: true, id, case_no: id ? `KLEAL-${id.slice(-6).toUpperCase()}` : '',
                  at: Date.now() / 1000, about: about.name });
        return;
      }
      const result = await group.report(gid, me, reason, [quoteLine, details.trim()].filter(Boolean).join('\n'),
                                        evidence, idem.current, about);
      if (!result?.ok) throw new Error(String(result?.error || 'REPORT_FAILED'));
      setSent(result);
    } catch (e) {
      const code = String((e as any)?.message || '');
      setError(code.includes('EVIDENCE_TOO_LARGE')
        ? T('Файл должен быть меньше 12 МБ.', 'The file must be smaller than 12 MB.', 'El archivo debe ser menor de 12 MB.')
        : T('Не удалось отправить жалобу. Попробуйте ещё раз.', 'Could not send the report. Try again.', 'No se pudo enviar el informe. Inténtalo de nuevo.'));
    } finally {
      setBusy(false);
    }
  };

  if (sent) {
    const who = about?.name || String(sent.about || '');
    const reasonLabel = REASONS.find((r) => r.key === reason)?.label() || '';
    return (
      <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
        <Header title="" onBack={() => router.dismissTo('/home')} />
        {/* Свой ключ: иначе React переиспользует прокрутку формы, и подтверждение открывается внизу. */}
        <ScrollView key="receipt" contentContainerStyle={s.successBody}>
          {/* GR.55a: зелёный круг 104 с картотекой, заголовок TASA 18 и срок проверки. */}
          <View style={s.okCircle}><IconCaseTray /></View>
          <View style={s.successHead}>
            <Text style={[s.successTitle, heading(lang, { fontSize: 18, lineHeight: 24, letterSpacing: 0 })]}>
              {T('Мы получили твою жалобу', 'We received your report', 'Hemos recibido tu denuncia')}
            </Text>
            <Text style={s.successText}>{T('Команда безопасности проверит её в течение 24 часов',
              'Our safety team will review it within 24 hours', 'Nuestro equipo de seguridad la revisará en 24 horas')}</Text>
          </View>

          <View style={[s.card, s.caseRow]}>
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={s.caseLabel}>{T('Номер обращения', 'Case number', 'Número de caso')}</Text>
              <Text style={s.caseNumber}>{sent.case_no || sent.id || ''}</Text>
              <View style={s.caseAboutRow}>
                {who ? <Text style={s.caseAbout}>{T(`О ${who}`, `About ${who}`, `Sobre ${who}`)}</Text> : null}
                {reasonLabel ? <IconShieldAlert size={14} c={color.muted} /> : null}
                {reasonLabel ? <Text style={s.caseAbout}>{reasonLabel}</Text> : null}
              </View>
            </View>
            <Pressable accessibilityRole="button" accessibilityLabel={T('Скопировать', 'Copy', 'Copiar')} hitSlop={10}
                       onPress={() => Clipboard.setStringAsync(String(sent.case_no || sent.id || '')).catch(() => {})}>
              <IconCopy />
            </Pressable>
          </View>

          <View style={s.block}>
            <Text style={s.sectionTitle}>{T('Статус', 'Status', 'Estado')}</Text>
            <View style={[s.card, s.statusCard]}>
              <StatusRow state="done" title={T('Получено', 'Received', 'Recibido')} note={reportReceivedAt(sent.at)}
                         trailing={T('готово', 'done', 'hecho')} />
              <StatusRow state="active" title={T('На проверке', 'Under review', 'En revisión')}
                         trailing={T('в работе', 'in progress', 'en curso')} />
              <StatusRow title={T('Решение', 'Decision', 'Decisión')}
                         trailing={T('придёт уведомлением', 'you’ll get a notification', 'te llegará un aviso')} />
            </View>
          </View>

          {who ? (
            <GlassSurface tone="info" radius={16} style={s.panel}>
              <Text style={s.infoTitle}>{T('Уже действует', 'Already in place', 'Ya en vigor')}</Text>
              {measures(who).map((m) => <MeasureRow key={m} text={m} />)}
            </GlassSurface>
          ) : null}

          <View style={s.block}>
            <Text style={s.sectionTitle}>{T('Нужна срочная помощь?', 'Need urgent help?', '¿Necesitas ayuda urgente?')}</Text>
            <View style={s.helpList}>
            <HelpRow icon={<IconPhone />} title={T('Экстренная помощь', 'Emergency', 'Emergencia')}
                     sub={T('Позвонить 112', 'Call 112', 'Llamar al 112')} onPress={() => Linking.openURL('tel:112')} />
            <HelpRow icon={<IconHeadset />} more title={T('Написать в поддержку', 'Contact support', 'Contactar con soporte')}
                     sub={T('Чат с командой поддержки', 'Chat with our support team', 'Chat con nuestro equipo')}
                     onPress={() => router.navigate('/profile/safety')} />
            <HelpRow icon={<IconLifeBuoy />} more title={T('Советы по безопасности', 'Safety tips', 'Consejos de seguridad')}
                     sub={T('Полезная информация и контакты', 'Helpful information and contacts', 'Información útil y contactos')}
                     onPress={() => router.navigate('/profile/safety')} />
            </View>
          </View>
          <GlassPill tone="brand" label={T('Готово', 'Done', 'Hecho')} style={s.doneBtn}
                     onPress={() => (router.canGoBack() ? router.back() : router.dismissTo('/home'))} />
        </ScrollView>
        <BottomNav active="intents" />
      </View>
    );
  }

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]}>
      <Header title={quote ? T('Жалоба на сообщение', 'Report a message', 'Reportar un mensaje')
                           : T('Сообщить о проблеме', 'Report a problem', 'Reportar un problema')} onBack={() => router.back()} />
      <ScrollView onScroll={navCollapse} scrollEventThrottle={16} contentContainerStyle={[s.body, { paddingBottom: kb + 24 }]} keyboardShouldPersistTaps="handled">
        {/* MSG.13b — «The message»: автор, текст и время вместо выбора человека. */}
        {quote ? (
          <>
            <Text style={s.sectionTitle}>{T('Сообщение', 'The message', 'El mensaje')}</Text>
            <View style={s.quoteBox}>
              <Text style={s.rowText}>{quoteWho}</Text>
              <Text style={s.quoteText}>{quote}</Text>
              {quoteAt ? (
                <Text style={s.quoteAt}>{new Date(quoteAt * 1000).toLocaleTimeString(dateLocale(getLang() === 'ru'),
                  { hour: '2-digit', minute: '2-digit', hour12: use12h(getLang() === 'ru') })}</Text>
              ) : null}
            </View>
          </>
        ) : null}
        {/* GR.55 «Who is this about?» — участники группы строками с лицом и возрастом. */}
        {!quote ? <Text style={s.sectionTitle}>{T('На кого жалоба?', 'Who is this about?', '¿Sobre quién es?')}</Text> : null}
        <View style={[s.list, quote ? { display: 'none' } : null]}>
          {people.map((m) => {
            const on = about?.id ? about.id === m.id : about?.name === m.name;
            return (
              <Pressable key={m.id || m.name} accessibilityRole="radio" accessibilityState={{ selected: on }}
                         style={[s.row, on && s.rowOn]} onPress={() => setAbout({ name: m.name, id: m.id })}>
                <View style={s.av}>
                  <IconPerson size={16} />
                  {m.photo ? <Image source={{ uri: mediaUrl(String(m.photo)) }} style={[s.av, StyleSheet.absoluteFill]} /> : null}
                </View>
                <Text style={s.rowText}>{m.age ? `${m.name}, ${m.age}` : m.name}</Text>
                {on ? <IconCheck /> : null}
              </Pressable>
            );
          })}
        </View>

        <Text style={s.sectionTitle}>{T('Что случилось?', 'What happened?', '¿Qué pasó?')}</Text>
        <View style={s.list}>
          {REASONS.map((item) => {
            const on = item.key === reason;
            return (
              <Pressable key={item.key} accessibilityRole="radio" accessibilityState={{ selected: on }}
                         style={[s.row, s.rowSlim, on && s.rowOn]} onPress={() => setReason(item.key)}>
                {item.icon('#FF385C')}
                {/* O.26: после звонка третья причина — «на звонке», а не «на встрече». */}
                <Text style={s.reasonText}>
                  {item.key === 'unsafe_behaviour' && String(params.call || '') === '1'
                    ? T('Опасное поведение на звонке', 'Unsafe behaviour on the call', 'Comportamiento peligroso en la llamada')
                    : item.key === 'unsafe_behaviour' && String(params.call || '') === 'hy'
                    ? T('Опасное поведение на встрече или в звонке', 'Unsafe behaviour at the meetup or on the call', 'Comportamiento peligroso en la quedada o en la llamada')
                    : item.label()}
                </Text>
                {on ? <IconCheck /> : null}
              </Pressable>
            );
          })}
        </View>

        <Text style={s.sectionTitle}>{T('Расскажи подробнее (необязательно)', 'Tell us more (optional)', 'Cuéntanos más (opcional)')}</Text>
        <View>
          <TextInput value={details} onChangeText={setDetails} maxLength={500} multiline textAlignVertical="top"
                     placeholder={T('Расскажи, что произошло. Добавь важные детали: время, место и сообщения.',
                                    'Tell us what happened. Include important details such as time, location, and messages.',
                                    'Cuéntanos qué pasó. Incluye detalles como la hora, el lugar y los mensajes.')}
                     placeholderTextColor={color.neutral400} style={s.input} />
          <Text style={s.counter}>{details.length}/500</Text>
        </View>

        <Text style={s.sectionTitle}>{T('Приложить доказательство (необязательно)', 'Attach evidence (optional)', 'Adjuntar prueba (opcional)')}</Text>
        {attachment ? (
          <View style={s.fileRow}>
            <IconClip />
            <View style={{ flex: 1 }}>
              <Text style={s.fileName} numberOfLines={1}>{attachment.name}</Text>
              <Text style={s.fileMeta}>{formatBytes(attachment.size || 0)}</Text>
            </View>
            <Pressable accessibilityRole="button" accessibilityLabel={T('Удалить файл', 'Remove file', 'Eliminar archivo')}
                       hitSlop={10} onPress={() => setAttachment(null)}>
              <IconTrash c={color.danger} />
            </Pressable>
          </View>
        ) : (
          <Pressable accessibilityRole="button" style={s.attach} onPress={pickEvidence}>
            <IconFilePlus size={24} c="#B4ABA0" />
            <Text style={s.attachText}>{T('Фото / Видео / Документы', 'Photo / Video / Docs', 'Foto / Vídeo / Documentos')}</Text>
          </Pressable>
        )}

        {/* GR.55 «When you send this» — что включится сразу, по имени выбранного человека. */}
        {about ? (
          <GlassSurface tone="info" radius={16} style={s.panel}>
            <Text style={s.infoTitle}>{T('Когда отправишь', 'When you send this', 'Cuando lo envíes')}</Text>
            {measures(about.name).map((m) => <MeasureRow key={m} text={m} shield />)}
          </GlassSurface>
        ) : null}
        {error ? <Text accessibilityRole="alert" style={s.error}>{error}</Text> : null}
        <GlassPill tone="brand" disabled={!reason || !about} busy={busy} onPress={submit}
                   label={T('Отправить жалобу', 'Send report', 'Enviar denuncia')} style={{ height: 48 }} />
      </ScrollView>
      <BottomNav active="intents" />
    </View>
  );
}

/** Шапка F10.3: стеклянная «назад» и название слева гарнитурой шапок — как у плана группы. */
function Header({ title, onBack }: { title: string; onBack: () => void }) {
  const lang = useLang();
  return (
    <View style={s.head}>
      <GlassBack label={T('Назад', 'Back', 'Atrás')} onPress={onBack} />
      <Text style={[s.headTitle, heading(lang, type.headingSm)]} numberOfLines={1}>{title}</Text>
    </View>
  );
}

/** Строка статуса GR.55a: знак 16, подпись 13/22, справа пилюля 11. Время «Received» — в той же строке. */
function StatusRow({ title, note, trailing, state = 'pending' }: {
  title: string; note?: string; trailing?: string; state?: 'done' | 'active' | 'pending';
}) {
  return (
    <View style={s.statusRow}>
      {state === 'done' ? (
        <View style={s.statusDone}><IconCheck size={12} c={color.onPrimary} /></View>
      ) : state === 'active' ? <IconLoader /> : <View style={s.statusIdle} />}
      <Text style={s.statusText}>{title}</Text>
      {note ? (
        <View style={s.statusWhen}>
          <IconClock size={14} c={color.fg} />
          <Text style={s.statusText}>{note}</Text>
        </View>
      ) : null}
      <View style={{ flex: 1 }} />
      {trailing ? <Text style={[s.statusTrailing, state === 'done' && s.statusTrailingDone,
                               state === 'active' && s.statusTrailingActive]}>{trailing}</Text> : null}
    </View>
  );
}

/** Мера защиты голубым: пустой щит до отправки (GR.55), галочка после (GR.55a). */
function MeasureRow({ text, shield }: { text: string; shield?: boolean }) {
  return (
    <View style={s.protectionRow}>
      {shield ? <IconShield size={16} c={color.infoText} /> : <IconCheck size={16} c={color.infoText} />}
      <Text style={s.infoText}>{text}</Text>
    </View>
  );
}

/** GR.55a «Need urgent help?»: отдельная карточка, знак кораллом 24, стрелка — где ведёт дальше. */
function HelpRow({ icon, title, sub, more, onPress }: {
  icon: React.ReactNode; title: string; sub: string; more?: boolean; onPress: () => void;
}) {
  return (
    <Pressable accessibilityRole="button" style={[s.card, s.helpRow]} onPress={onPress}>
      {icon}
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={s.helpRowTitle}>{title}</Text>
        <Text style={s.helpRowSub}>{sub}</Text>
      </View>
      {more ? <IconChevronRight c={color.fg} /> : null}
    </Pressable>
  );
}

function reportReceivedAt(at?: number) {
  const date = at ? new Date(at * 1000) : new Date();
  const time = date.toLocaleTimeString(dateLocale(), { hour: '2-digit', minute: '2-digit', hour12: use12h() });
  return T(`Сегодня ${time}`, `Today ${time}`, `Hoy ${time}`);
}

function formatBytes(value: number) {
  if (!value) return '';
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  const mb = (value / 1024 / 1024).toFixed(1);
  return `${getLang() === 'en' ? mb : mb.replace('.', ',')} MB`;
}

const s = StyleSheet.create({
  successHead: { width: '100%', alignItems: 'center', gap: 12, marginBottom: 4 },
  card: { width: '100%', backgroundColor: '#F9F6F3', borderRadius: 16, padding: 16 },
  caseAboutRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 },
  block: { width: '100%', gap: 16 },
  statusCard: { gap: 12 },
  statusDone: { width: 16, height: 16, borderRadius: 8, backgroundColor: '#1FAE5E', alignItems: 'center', justifyContent: 'center' },
  statusIdle: { width: 13.5, height: 13.5, marginHorizontal: 1.25, borderRadius: 7, borderWidth: 1, borderColor: '#DDDDDD' },
  statusWhen: { flexDirection: 'row', alignItems: 'center', gap: 4, marginLeft: 4 },
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  head: { height: 56, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 20 },
  headTitle: { flex: 1, color: color.fg } as any,
  body: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 24, gap: 14 },
  successBody: { paddingHorizontal: 16, paddingTop: 0, paddingBottom: 24, alignItems: 'center', gap: 20 },
  context: { ...type.bodySmall, color: color.muted } as any,
  sectionTitle: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 20, color: color.fg } as any,
  quoteBox: { gap: 4, padding: 12, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.62)' },
  quoteText: { fontFamily: font.text, fontSize: 14, lineHeight: 20, color: color.fg } as any,
  quoteAt: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: color.muted, textAlign: 'right' } as any,
  /** Причины — отдельные стеклянные строки (F10.3); выбранная обведена кораллом. */
  reasons: { gap: 8 },
  reason: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14,
    borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.62)', borderWidth: 1, borderColor: '#FFFFFF' },
  reasonOn: { borderColor: '#FF385C' },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: color.neutral300,
    alignItems: 'center', justifyContent: 'center' },
  radioOn: { borderColor: color.primary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: color.primary },
  reasonText: { flex: 1, fontFamily: font.textSemibold, fontSize: 13, lineHeight: 20, color: color.fg } as any,
  inputHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  counter: { position: 'absolute', right: 14, bottom: 10, fontFamily: font.text, fontSize: 10, lineHeight: 16, color: color.muted } as any,
  input: { minHeight: 140, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.56)', padding: 14, paddingBottom: 28,
    color: color.fg, fontFamily: font.text, fontSize: 13, lineHeight: 18 } as any,
  /** Борд GR.55: пунктир #E5DED4 по стеклу, «файл с плюсом» серым. */
  attach: { height: 80, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.56)', alignItems: 'center',
    justifyContent: 'center', gap: 6, borderWidth: 1, borderStyle: 'dashed', borderColor: '#E5DED4' },
  attachText: { fontFamily: font.text, fontSize: 12, lineHeight: 16, color: color.muted } as any,
  fileRow: { minHeight: 64, borderWidth: 1, borderColor: '#FFFFFF', borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.62)', paddingHorizontal: 14, flexDirection: 'row', alignItems: 'center', gap: 12 },
  fileName: { ...type.body, color: color.fg } as any,
  fileMeta: { ...type.caption, color: color.muted } as any,
  safetyBand: { padding: 16, gap: 8 },
  safetyText: { ...type.bodySmall, color: color.infoText } as any,
  error: { ...type.bodySmall, color: color.danger } as any,
  submit: { marginHorizontal: 20, marginBottom: 12 },
  successTitle: { color: color.fg, textAlign: 'center' } as any,
  successText: { fontFamily: font.text, fontSize: 13, lineHeight: 18, color: '#5A616E', textAlign: 'center' } as any,
  caseRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  caseLabel: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 14, color: '#5A616E' } as any,
  caseNumber: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 20, color: color.fg } as any,
  statusHead: { width: '100%', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  progressBadge: { ...type.caption, color: color.warnText, backgroundColor: color.warnBg,
    borderRadius: rad.full, paddingHorizontal: 10, paddingVertical: 4 } as any,
  panel: { width: '100%', padding: 14, gap: 10 },
  panelTitle: { ...type.title, color: color.fg } as any,
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 20 },
  statusText: { fontFamily: font.text, fontSize: 13, lineHeight: 20, color: color.fg } as any,
  /** Метки статуса — пилюли 16 (GR.55a): done зелёная, in progress янтарная, уведомление серая. */
  statusTrailing: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 16, color: '#A6ADBB', overflow: 'hidden',
                    backgroundColor: '#E9EAEC', borderRadius: 99, paddingHorizontal: 8 } as any,
  statusTrailingDone: { color: '#0F7340', backgroundColor: '#D4F0DF' },
  statusTrailingActive: { color: '#FC8F00', backgroundColor: '#FFE396' },
  protectionRow: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  protectionCheck: { width: 18, height: 18, borderRadius: 9, backgroundColor: color.successText,
    alignItems: 'center', justifyContent: 'center' },
  protectionCheckText: { color: color.onPrimary, fontSize: 11, fontWeight: '700' },
  measureText: { flex: 1, ...type.bodySmall, color: color.successText } as any,
  helpTitle: { width: '100%', marginTop: 2 },
  helpList: { gap: 8 },
  helpRow: { flexDirection: 'row', alignItems: 'center', gap: 16, paddingVertical: 14 },
  helpRowTitle: { fontFamily: font.textMedium, fontSize: 13, lineHeight: 18, color: color.fg } as any,
  helpRowSub: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 14, color: '#5A616E' } as any,
  rule: { height: 1, backgroundColor: color.border },
  fullW: { width: '100%' },
  list: { gap: 4 },
  /** Строки выбора — белое стекло 16%, выбранная 36%, галочка кораллом (GR.55). */
  row: { minHeight: 56, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 12, borderRadius: 16,
         backgroundColor: 'rgba(255,255,255,0.16)' },
  rowSlim: { minHeight: 48, paddingHorizontal: 16 },
  rowOn: { backgroundColor: 'rgba(255,255,255,0.56)' },
  rowText: { flex: 1, fontFamily: font.textSemibold, fontSize: 14, lineHeight: 20, color: color.fg } as any,
  av: { width: 40, height: 40, borderRadius: 20, overflow: 'hidden', backgroundColor: color.neutral100,
        alignItems: 'center', justifyContent: 'center' },
  infoTitle: { fontFamily: font.textSemibold, fontSize: 15, lineHeight: 20, color: color.infoText } as any,
  infoText: { flex: 1, fontFamily: font.text, fontSize: 13, lineHeight: 18, color: color.infoText } as any,
  okCircle: { width: 104, height: 104, borderRadius: 52, backgroundColor: '#D4F0DF', alignItems: 'center', justifyContent: 'center' },
  caseAbout: { fontFamily: font.textMedium, fontSize: 11, lineHeight: 14, color: '#5A616E' } as any,
  doneBtn: { height: 48, width: '100%', marginTop: 4 },
});
