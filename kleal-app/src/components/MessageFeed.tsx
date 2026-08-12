/**
 * Лента переписки — одна на личный чат и на комнату группы.
 *
 * Их было две, и разметка совпадала почти дословно. Мешало не оформление, а ДАННЫЕ: сервер зовёт
 * автора `from` в паре и `frm` в комнате, системную строку в паре узнают по полю `sys`, а в
 * комнате — по пустому автору. Из-за двух этих различий всё, что делалось для переписки —
 * серии, состояние отправки, реакции, цитата, свайп-ответ, — в комнате отсутствовало.
 *
 * Теперь форма приводится на входе (`roomMsg` в src/groups.ts), а показывает обе одна лента.
 * Что остаётся за экраном — только то, чем чаты действительно отличаются:
 *
 *   `showAuthor`  — имя над чужим пузырём. В комнате больше двух человек, и без подписи реплики
 *                   сливаются в один голос; в паре имя избыточно, собеседник и так один.
 *   `peerRead`    — момент, когда вторая сторона открывала переписку. Есть только у пары: в
 *                   комнате «прочитано» значило бы «все прочитали», а этого сервер не считает.
 *   `sysText`     — как превратить системную строку в текст. В паре это код события, в комнате
 *                   английская фраза от сервера.
 *
 * Всё остальное — общее, и переставать быть общим не должно: разъехавшиеся ленты мы уже видели.
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View, Linking } from 'react-native';
import { CHAT, Msg, msgTime, msgDayLabel, sameSeries, linkParts } from '../chat';
import { VoiceBubble } from '../voice';
import { VideoBubble } from '../videonote';
import { SwipeToReply } from './SwipeToReply';
import { color, radius as rad, space } from '../theme';

export function MessageFeed({
  msgs, me, ru, sysText, showAuthor = false, peerRead,
  onReply, onReact, onPick, onRetry,
}: {
  msgs: Msg[];
  me: string;
  ru: boolean;
  sysText: (m: Msg) => string;
  showAuthor?: boolean;
  peerRead?: number;
  onReply: (m: Msg) => void;
  onReact: (m: Msg, emoji: string) => void;
  onPick: (m: Msg) => void;
  onRetry: (m: Msg) => void;
}) {
  const norm = (v: unknown) => String(v || '').trim().toLowerCase();
  const mineName = norm(me);

  /**
   * Что реально попадёт на экран. Считается ЗАРАНЕЕ, потому что от соседей зависят и разделитель
   * дня, и серия — а системная строка с незнакомым кодом не рисуется вовсе. Раньше соседа брали
   * из полного списка: скрытая строка оставалась «предыдущей», и «Сегодня» исчезало вместе с ней.
   */
  const shown = msgs.filter((m) => !m.sys || !!sysText(m));

  return (
    <>
      {shown.map((m, i) => {
        const mine = norm(m.from) === mineName;
        const prev = shown[i - 1];
        const next = shown[i + 1];
        const newDay = !!m.t && (!prev
          || new Date((prev.t || 0) * 1000).toDateString() !== new Date(m.t * 1000).toDateString());

        /* События — не реплика: они не чьи-то слова, а факт, случившийся со встречей или с
           составом. Поэтому строкой по центру, без пузыря, автора и галочек. */
        if (m.sys) {
          return (
            <React.Fragment key={m.id || m.cid || i}>
              {newDay ? <Text style={s.day}>{msgDayLabel(m.t!, ru)}</Text> : null}
              <Text style={s.sys}>
                {sysText(m)}{m.t ? ` · ${msgTime(m.t, ru)}` : ''}
              </Text>
            </React.Fragment>
          );
        }

        const tail = !sameSeries(m, next);
        const head = !sameSeries(prev, m);
        const failed = m.state === 'failed';
        const read = peerRead !== undefined && peerRead >= (m.t || 0);

        return (
          <React.Fragment key={m.id || m.cid || i}>
            {newDay ? <Text style={s.day}>{msgDayLabel(m.t!, ru)}</Text> : null}
            <SwipeToReply enabled={!!m.id && !m.deleted} onReply={() => onReply(m)}>
              <View style={{ alignItems: mine ? 'flex-end' : 'flex-start', marginTop: head ? 8 : 2 }}>
                {/* Имя автора — только у чужих и только в начале серии: повторять его над каждой
                    репликой одного человека значит кричать его четыре раза подряд. */}
                {showAuthor && !mine && head ? <Text style={s.author}>{m.from}</Text> : null}

                {m.video && !m.deleted ? (
                  /* Кружок — не пузырь: у него нет ни фона, ни хвостика, он сам себе форма. */
                  <VideoBubble video={m.video} />
                ) : m.voice ? (
                  <VoiceBubble voice={m.voice} mine={mine} />
                ) : (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={failed ? CHAT.retry() : m.text}
                    onPress={failed ? () => onRetry(m) : undefined}
                    onLongPress={m.deleted || !m.id ? undefined : () => onPick(m)}
                    delayLongPress={350}
                    style={[s.bub, mine ? s.bubMe : s.bubThem,
                            !tail && (mine ? s.bubMeMid : s.bubThemMid), failed && s.bubFailed]}
                  >
                    {/* Цитата внутри пузыря, а не рядом: ответ и то, на что отвечают, — одно целое. */}
                    {m.rt ? (
                      <View style={[s.quote, mine && s.quoteMine]}>
                        <Text style={[s.quoteWho, mine && { color: color.onPrimary }]} numberOfLines={1}>
                          {m.rt.from}
                        </Text>
                        <Text style={[s.quoteText, mine && { color: color.onPrimary }]} numberOfLines={2}>
                          {m.rt.text || CHAT.deleted()}
                        </Text>
                      </View>
                    ) : null}
                    <Text style={[s.bubText, mine && { color: color.onPrimary }, m.deleted && s.bubGone]}>
                      {m.deleted ? CHAT.deleted() : linkParts(String(m.text || '')).map((part, k) => (
                        part.href ? (
                          /* Адрес показан ровно так, как его прислали: подменять его красивой
                             подписью нельзя — по нему и решают, идти ли. */
                          <Text
                            key={k}
                            style={[s.link, mine && s.linkMine]}
                            onPress={() => Linking.openURL(part.href!).catch(() => {})}
                          >
                            {part.text}
                          </Text>
                        ) : <Text key={k}>{part.text}</Text>
                      ))}
                    </Text>
                  </Pressable>
                )}

                {/* Реакции под пузырём: нажатие по своей снимает её, по чужой — присоединяет. */}
                {m.r && Object.keys(m.r).length ? (
                  <View style={[s.reactions, { alignSelf: mine ? 'flex-end' : 'flex-start' }]}>
                    {Object.entries(m.r).map(([e, who]) => (
                      <Pressable
                        key={e}
                        accessibilityRole="button"
                        accessibilityLabel={`${e} ${who.length}`}
                        onPress={() => onReact(m, e)}
                        style={[s.reaction, who.includes(mineName) && s.reactionMine]}
                      >
                        <Text style={s.reactionText}>{e}{who.length > 1 ? ` ${who.length}` : ''}</Text>
                      </Pressable>
                    ))}
                  </View>
                ) : null}

                {tail ? (
                  <Text style={s.time}>
                    {msgTime(m.t, ru)}
                    {/* Своё сообщение говорит о себе честно: часики — ушло не всё, восклицание —
                        не ушло вовсе и можно нажать, галочка — сервер принял, две — прочитано. */}
                    {mine ? (
                      m.state === 'sending' ? <Text style={s.tick}>  ⋯</Text>
                      : failed ? <Text style={s.tickFail}>  ! {CHAT.retry()}</Text>
                      : peerRead === undefined ? null
                      : <Text style={read ? s.tickRead : s.tick}>{read ? '  ✓✓' : '  ✓'}</Text>
                    ) : null}
                  </Text>
                ) : null}
              </View>
            </SwipeToReply>
          </React.Fragment>
        );
      })}
    </>
  );
}

// ===== вид

const s = StyleSheet.create({
  day: { alignSelf: 'center', fontSize: 12, color: color.neutral400, marginVertical: space.sm },
  sys: { alignSelf: 'center', textAlign: 'center', fontSize: 12, color: color.muted, marginVertical: 6 },
  author: { fontSize: 12, color: color.muted, marginBottom: 2, marginLeft: 4 },

  bub: { maxWidth: '80%', paddingVertical: 12, paddingHorizontal: 16, borderRadius: 18 },
  /** Хвостик — у ПОСЛЕДНЕГО пузыря серии: он и показывает, где реплики одного человека кончились. */
  bubMe: { alignSelf: 'flex-end', backgroundColor: color.primary, borderBottomRightRadius: 6 },
  bubThem: { alignSelf: 'flex-start', backgroundColor: color.neutral100, borderBottomLeftRadius: 6 },
  bubMeMid: { borderBottomRightRadius: 18 },
  bubThemMid: { borderBottomLeftRadius: 18 },
  bubText: { fontSize: 15, lineHeight: 21, color: color.fg },
  /** Не ушло — пузырь бледнее и нажимается. Цвет не меняем: это по-прежнему твои слова. */
  bubFailed: { opacity: 0.6 },
  /** Удалённое остаётся строкой: пропасть бесследно оно не может — второй его уже видел. */
  bubGone: { fontStyle: 'italic', opacity: 0.7 },

  quote: { borderLeftWidth: 2, borderLeftColor: color.primary, paddingLeft: space.sm, marginBottom: 6, gap: 1 },
  quoteMine: { borderLeftColor: color.onPrimary },
  quoteWho: { fontSize: 12, fontWeight: '700', color: color.primary } as any,
  quoteText: { fontSize: 12, color: color.muted } as any,

  link: { color: color.primary, textDecorationLine: 'underline' } as any,
  linkMine: { color: color.onPrimary } as any,

  reactions: { flexDirection: 'row', gap: 4, marginTop: 3 },
  reaction: {
    flexDirection: 'row', paddingHorizontal: 7, paddingVertical: 3,
    borderRadius: rad.full, backgroundColor: color.neutral100,
    borderWidth: 1, borderColor: 'transparent',
  },
  /** Своя реакция обведена: без этого нельзя понять, поставил ты её или просто видишь. */
  reactionMine: { borderColor: color.primary, backgroundColor: color.card },
  reactionText: { fontSize: 13, color: color.fg } as any,

  time: { fontSize: 11, color: color.neutral400, marginTop: 3, marginHorizontal: 4 },
  tick: { fontSize: 11, color: color.neutral400 } as any,
  tickRead: { fontSize: 11, color: color.primary, fontWeight: '700' } as any,
  tickFail: { fontSize: 11, color: color.primary, fontWeight: '600' } as any,
});
