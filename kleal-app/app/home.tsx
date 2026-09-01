/**
 * Главный экран.
 *
 * Порт Agent Home из веба. Обе ленты приходят с сервера:
 *
 *  — групповые мероприятия (/api/agent/groups) — то, к чему можно присоединиться;
 *  — адресованные пользователю 1:1 и групповые приглашения (/api/agent/home-invites).
 *
 * Придуманных карточек здесь нет: по каждой человек нажимает и попадает к живому человеку. Когда
 * сервер ничего не вернул, показывается пустое состояние, а не заглушка, похожая на данные.
 *
 * Фон. На кадре Figma это фотография неба; в вебе она подключена как assets/clouds.jpg, но такого
 * файла на сервере нет — он отдаёт 404, и живой веб показывает голубую заливку. Здесь градиент по
 * тем же цветам: рисовать фотографию, которой нет, не из чего.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Animated, View, Text, StyleSheet, ScrollView, Pressable, Image,
  ActivityIndicator, RefreshControl, KeyboardAvoidingView, Platform, Keyboard,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { BottomNav } from '../src/components/BottomNav';
import { CardStack } from '../src/components/CardStack';
import { ArcCarousel, ARC_COPIES, ARC_PITCH } from '../src/components/ArcCarousel';
import { NotifyBubble } from '../src/components/NotifyBubble';
import { hCommit } from '../src/haptics';
import { Ambient, GLOW_SIGNIN } from '../src/components/Ambient';
import { WHEEL } from '../src/wheel';
import {
  IconBell, IconCalendar, IconClock, IconPin, IconBookmark, IconMic,
  IconChat, IconGroups, IconImagePlaceholder,
} from '../src/components/icons';
import { useLang, T } from '../src/i18n';
import { useOnb } from '../src/state';
import { mediaUrl, warmPhotos, agent } from '../src/api';
import {
  HOME, splitWhen, planWhere, joinableGroups, homeInvites,
  Group, HomeInvite,
} from '../src/home';
import { color, displayFamily, radius as rad, space, type } from '../src/theme';

export default function Home() {
  const lang = useLang();
  const router = useRouter();
  const st = useOnb();
  const insets = useSafeAreaInsets();
  const me = st.profile.name || '';

  const [groups, setGroups] = useState<Group[]>([]);
  const [invites, setInvites] = useState<HomeInvite[]>([]);
  const [nextPlan, setNextPlan] = useState<any>(null);
  const [inviteError, setInviteError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  /**
   * Высота нижней панели. Меряется, а не задаётся числом: она складывается из своей полосы и
   * безопасной зоны, которая на разных телефонах разная.
   */
  const [navH, setNavH] = useState(96);
  /**
   * Сдвиг колеса. Живёт ЗДЕСЬ, а не внутри карусели, потому что от него зависит и фон: подложка
   * меняется вместе с картинкой, и оба читают одно значение на стороне UI.
   */
  const wheelAt = useRef(new Animated.Value(0)).current;
  /**
   * СКОЛЬКО МЕСТА ОСТАЛОСЬ КОЛЕСУ — ЗАМЕР, А НЕ ПОДБОР.
   *
   * Колесо и карточка приглашений делят пустую главную. Пока размер колеса стоял числом, всё
   * держалось на том, что подобрано оно было под ЭТОТ телефон: на другом сумма переставала
   * помещаться, лента становилась прокручиваемой, и кнопка «Найти людей» уезжала под строку ввода
   * — карточка западала.
   *
   * Теперь меряются оба: видимая высота ленты и высота карточки. Колесу отдаётся ровно остаток, и
   * прокручиваться становится нечему.
   */
  const [viewH, setViewH] = useState(0);
  /** Какое приглашение сверху стопки. Живёт в экране: он знает, какие уже разобрали. */
  const [invIdx, setInvIdx] = useState(0);
  /**
   * Открыта ли клавиатура.
   *
   * Док отступает снизу на высоту панели, чтобы не налезать на неё. Но когда клавиатура поднимает
   * док, панель уже под клавиатурой — и этот отступ становится пустым зазором, на который ввод
   * улетает выше клавиатуры. Пока клавиатура открыта, отступа нет.
   */
  const [kb, setKb] = useState(false);
  useEffect(() => {
    const ios = Platform.OS === 'ios';
    const show = Keyboard.addListener(ios ? 'keyboardWillShow' : 'keyboardDidShow', () => setKb(true));
    const hide = Keyboard.addListener(ios ? 'keyboardWillHide' : 'keyboardDidHide', () => setKb(false));
    return () => { show.remove(); hide.remove(); };
  }, []);

  /** Открытые группы и личные приглашения грузятся независимо друг от друга. */
  const load = useCallback(async () => {
    if (!me) { setLoading(false); return; }
    const [g, i, pl] = await Promise.all([
      agent.groups(me).catch(() => null),
      agent.homeInvites(me).catch(() => null),
      agent.plans(me).catch(() => null),
    ]);
    // Ближайшая ЖИВАЯ встреча: назначенная и ещё не прошедшая, самая ранняя из них. Отменённые и
    // прошедшие сюда не попадают — главная показывает то, к чему человек собирается, а не архив.
    const live = ((pl as any)?.plans || [])
      .filter((p: any) => (p.state === 'confirmed' || p.state === 'proposed') && p.starts_at)
      .sort((a: any, b: any) => (a.starts_at || 0) - (b.starts_at || 0));
    setNextPlan(live[0] || null);
    setGroups(joinableGroups((g as any)?.groups || []));
    if (i) {
      const next = homeInvites((i as any)?.invites || []);
      /*
        Лица греем СРАЗУ, как только пришёл список, — до того, как стопку нарисуют. Без этого
        карточка появлялась пустой и лицо проявлялось через паузу: файл начинали качать только в
        тот момент, когда `<Image>` впервые оказывался на экране.

        Греем всю стопку, а не первое приглашение: их пролистывают подряд, и второе лицо нужно
        через секунду после первого.
      */
      warmPhotos(next.map((x: any) => x?.from?.photo));
      setInvites((prev) => {
        // Индекс стопки только РОС и не сбрасывался никогда. `load()` дёргается при каждом
        // возвращении на экран, и после ответа на приглашение список приходит короче — а индекс
        // остаётся прежним: человек видел пустое место там, где лежало новое приглашение.
        // Сбрасываем, когда СОСТАВ изменился; при том же составе позиция сохраняется — иначе
        // возврат с экрана приглашения отбрасывал бы стопку в начало.
        const same = prev.length === next.length
          && prev.every((p, k) => String(p.id) === String(next[k]?.id));
        if (!same) setInvIdx(0);
        return next;
      });
      setInviteError(false);
    } else {
      setInviteError(true);
    }
    setLoading(false);
  }, [me]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const refresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  /**
   * Поле на главной — не поле, а кнопка.
   *
   * Печатать тут негде: разговор идёт в чате с Бадди, и набирать первую фразу на одном экране,
   * чтобы дочитать ответ на другом, незачем. Нажатие сразу открывает чат, клавиатура поднимается
   * уже там — под лентой, в которую человек и смотрит.
   */
  const toBuddy = () => router.navigate('/buddy');

  const myArea = st.profile.city || '';


  /*
    РАЗМЕР КОЛЕСА НЕ ЗАВИСИТ ОТ ТОГО, ЧТО ПОД НИМ.

    Раньше он был остатком: `viewH - belowH`. Замысел понятен — чтобы ни внизу не зияла пустота,
    ни колесо не вылезало за экран. Но следствие оказалось хуже причины: стоило появиться плану,
    и нижний блок вырастал (колода вместо одинокой карточки — соседняя карточка выглядывает, под
    ней точки, да и сама карточка встречи выше пустой), а колесо на ту же величину СЖИМАЛОСЬ.
    Кроссовок на главной становился меньше просто потому, что вечером назначена встреча. Сообщено
    с телефона; со стороны это читается как поломка, а не как вёрстка, — размер одного и того же
    предмета не должен зависеть от чужих новостей.

    Теперь колесо считается от видимой области и только от неё: доля даёт стабильную высоту на
    любом экране, нижняя граница спасает короткие, верхняя оставляет место, чтобы из-под колеса
    выглядывала первая карточка и было видно, что там что-то есть. Не поместилось — лента честно
    прокручивается: она и так ScrollView, ради этого сжимать картинку не нужно.
  */
  const wheelH = viewH ? Math.max(220, Math.min(Math.round(viewH * 0.62), viewH - 160)) : undefined;

  return (
    <View style={s.wrap}>
      {/*
        ФОН ТОТ ЖЕ, ЧТО НА ВХОДНЫХ ЭКРАНАХ. До этого главная была единственным местом с голубым
        небом: человек проходил четыре кремовых экрана подряд и попадал на пятый, будто из другого
        приложения. Пятна тут те же, что на экране входа, — и кремовая бумага под ними.
      */}
      <Ambient glows={GLOW_SIGNIN} />
      {/*
        ПОДЛОЖКА ПЕРЕТЕКАЕТ ВМЕСТЕ С КОЛЕСОМ.

        Слоёв столько же, сколько предметов; каждый нарисован один раз и больше не перерисовывается,
        меняется только его непрозрачность — и та считается интерполяцией сдвига ленты на нативном
        драйвере. Отсюда и плавность на любой скорости: JS в этом не участвует вовсе, а значит
        резкий бросок пальца не может «перескочить» цвет.

        Пик у каждого слоя повторяется ТРИЖДЫ — по разу на копию ленты (колесо бесконечное и
        выложено тремя копиями). Между пиками слой стоит на нуле, так что суммарно на экране всегда
        один слой или плавная смесь двух соседних.

        Кремовая подложка одинаковая во всех слоях и вдобавок залита в самом экране, поэтому в
        момент пересменки фон не может провалиться в белое.
      */}
      {WHEEL().map((it, i) =>
        it.glows ? (
          <Animated.View
            key={it.key}
            pointerEvents="none"
            style={[
              StyleSheet.absoluteFill,
              {
                opacity: wheelAt.interpolate({
                  inputRange: Array.from({ length: ARC_COPIES }, (_, k) => (k * WHEEL().length + i) * ARC_PITCH)
                    .flatMap((p) => [p - ARC_PITCH, p, p + ARC_PITCH]),
                  outputRange: Array.from({ length: ARC_COPIES }).flatMap(() => [0, 1, 0]),
                  extrapolate: 'clamp',
                }),
              },
            ]}
          >
            <Ambient glows={it.glows} />
          </Animated.View>
        ) : null
      )}
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={[s.head, { paddingTop: insets.top + 6 }]}>
          {/* Гарнитура зависит от языка — см. displayFamily: в шрифте борда нет кириллицы. */}
          <Text style={[s.hello, { fontFamily: displayFamily(lang) }]}>{HOME.hello()}</Text>
          {/*
            Колокольчик больше не молчит: под ним разворачивается пузырь с приглашениями — см.
            src/components/NotifyBubble.tsx. Точка «есть новое» осталась там же, внутри него.
          */}
          <NotifyBubble
            invites={invites}
            onPick={(inv) => router.navigate({ pathname: '/invite', params: { id: inv.id } })}
          />
        </View>

        <ScrollView
          onLayout={(e) => setViewH(e.nativeEvent.layout.height)}
          contentContainerStyle={s.scroll}
          keyboardShouldPersistTaps="handled"
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={color.primary} />}
        >
          {loading ? (
            <ActivityIndicator style={{ marginTop: 40 }} color={color.primary} />
          ) : (
            <>
              {/*
                КОЛЕСО СТОИТ ВСЕГДА, А НЕ ТОЛЬКО НА ПУСТОЙ ГЛАВНОЙ.
                Одна картинка крупно, соседние выглядывают из-за краёв — это не заглушка «тут
                ничего нет», а первое, что показывает, о чём вообще приложение, и единственное
                место, где на главной есть что делать руками.
                Раньше оно уходило, как только появлялась хоть одна секция: считалось, что
                настоящее содержимое займёт экран. НЕ ЗАНИМАЕТ. Ни приглашение, ни ближайшая
                встреча — это одна карточка в сотню точек, и главная от неё превращалась в
                карточку посреди двух третей пустоты. Поймано дважды, на снимках с телефона.
                Теперь всё, что есть, стоит ПОД колесом — там же, где стояло, — его высота
                измеряется, а колесо занимает ровно остаток: прокручивать ни до чего не надо.
                Секций много и остатка не хватило — колесо ужимается до предела, а лента честно
                прокручивается.
              */}
              <View style={s.wheel}>
                  {/*
                    Нажатие по центральному предмету открывает создание интента с уже сказанной
                    фразой: `seed` в app/create.tsx кладёт её в ленту как реплику человека и сразу
                    отдаёт агенту. Поэтому колесо — не витрина: оно начинает разговор, а не
                    показывает, что бывает.
                  */}
                  <ArcCarousel
                    items={WHEEL()}
                    progress={wheelAt}
                    // Остаток: видимая часть ленты минус то, что стоит над колесом и под ним.
                    height={wheelH}
                    onPick={(it) => router.navigate({ pathname: '/create', params: { seed: it.query } })}
                  />
              </View>

              {/*
                ВСЁ ОСТАЛЬНОЕ — ОДНИМ БЛОКОМ, И МЕРЯЕМ ЕГО ВЫСОТУ. Колесо забирает то, что от неё
                осталось. Мерить каждую секцию отдельно значило бы держать три состояния вместо
                одного и заводить четвёртое на каждой новой секции.
              */}
              <View style={s.below}>
              {/*
                ВСТРЕЧА И ПРИГЛАШЕНИЯ — ОДНА КАРТОЧКА, А НЕ ДВЕ ПЛАШКИ ПОДРЯД. Здесь стояла своя
                плашка со своим заголовком-секцией, своим радиусом (16 против 20) и своей вёрсткой
                — три отличия от карточки ниже на расстоянии двенадцати пикселей. Рядом это
                читалось как два разных приложения.
                Обе строки живут внутри `EmptyInviteCard` и разделены волосяной линией; когда
                приглашения настоящие, они идут каруселью, и встреча остаётся отдельной карточкой
                в том же оформлении — стопка складывается только там, где ей есть с чем сложиться.
              */}

              {groups.length ? (
                <>
                  <Section icon={<IconGroups />} title={HOME.groups()} />
                  <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={s.carousel}
                    snapToInterval={CARD_W + space.md}
                    decelerationRate="fast"
                  >
                    {groups.map((g) => <GroupCard key={g.gid} g={g} myArea={myArea} />)}
                  </ScrollView>
                </>
              ) : null}
              {/*
                ВСТРЕЧА И ПРИГЛАШЕНИЯ — ОДНА КОЛОДА, а не две плашки подряд.

                Здесь стояли две карточки одна под другой, и обе видно целиком. На экране это
                читается как два не связанных блока: сначала «что у меня назначено», потом
                «кто ко мне просится». Колода говорит иначе — вот верхнее, а за ним есть ещё, — и
                это ровно тот приём, который продукт уже применяет к приглашениям: показать ОДНО и
                сказать, сколько за ним. Геометрия краёв взята оттуда же, с борда (Invite Stack).

                Встреча идёт первой: она про назначенное время, и её нельзя задвинуть за
                приглашение, которого может и не быть. «Дальше ›» под колодой переводит к
                следующей — ничего не становится недоступным.
              */}
              {nextPlan || invites.length || inviteError ? (
                <View style={s.stack}>
                  {/*
                    ЗАГОЛОВКА У СМЕШАННОЙ КОЛОДЫ НЕТ, и это не экономия места. Он обязан называть
                    то, что под ним, а под ним лежат разные вещи и меняются по «Дальше»: встреча,
                    потом приглашение. Любая одна подпись врала бы в половине состояний — и
                    «Приглашения» над карточкой встречи, и «Ближайшая встреча» над приглашением.
                    Карточки называют себя сами: у встречи подпись над названием, у приглашений —
                    имя человека. Заголовок остаётся там, где он честен: когда в колоде одни
                    приглашения.
                  */}
                  {nextPlan ? null : <Section icon={<IconBell size={18} />} title={HOME.invites()} />}
                  {inviteError ? (
                    <View style={s.inviteError}>
                      <Text style={s.empty}>{HOME.inviteLoadFailed()}</Text>
                      <Pressable accessibilityRole="button" onPress={load} style={s.retryBtn}>
                        <Text style={s.retryText}>{HOME.retry()}</Text>
                      </Pressable>
                    </View>
                  ) : (
                    /*
                      Стопка, а не список — компонент борда «Invite Stack» (GR.01, 350×131 при
                      карточке 350×110). Сверху одно приглашение, за ним видны края остальных.
                      Так и задумано продуктом: 2–4 объяснённых варианта, а не лента, по которой
                      скроллят. Разбирать приглашения по одному — ещё и честнее: решение по
                      каждому человеку принимается отдельно, а не сравнением витрины.
                    */
                    <CardStack
                      items={[
                        // Встреча — такой же житель колоды, как приглашение. `kind` отличает её
                        // при отрисовке: у стопки один список, а карточки в нём разные.
                        ...(nextPlan ? [{ key: 'plan', kind: 'plan', plan: nextPlan } as any] : []),
                        ...(invites.length
                          ? invites.map((inv) => ({ ...inv, kind: 'invite', key: String(inv.id) } as any))
                          // Пустая карточка приглашений — тоже житель: без неё колода из одной
                          // встречи не сказала бы человеку, что приглашений просто нет.
                          : [{ key: 'empty', kind: 'empty' } as any]),
                      ]}
                      index={invIdx}
                      onIndex={setInvIdx}
                      emptyHint={invites.length ? HOME.invitesAllSeen() : ''}
                      render={(it: any) => (
                        it.kind === 'plan' ? <View style={s.meet}><NextMeetRow plan={it.plan} /></View>
                        : it.kind === 'empty' ? <EmptyInviteCard />
                        : it.type === 'group' ? <GroupInviteCard inv={it} />
                        : <DirectInviteCard inv={it} />
                      )}
                    />
                  )}
                </View>
              ) : (
                /*
                  Ни встречи, ни приглашений — колоду разворачивать не из чего, показываем ту же
                  пустую карточку саму по себе. Кадр «Home Card · Empty»: колесо говорит, чем
                  заняться самому, а она отвечает на невысказанный вопрос «а мне-то кто-нибудь
                  написал».
                */
                <EmptyInviteCard />
              )}
              </View>
            </>
          )}
        </ScrollView>

        {/*
          ДОК ПОДНЯТ НАД ПАНЕЛЬЮ НА ЗАМЕТНЫЙ ЗАЗОР, А НЕ НА ШЕСТЬ ТОЧЕК.

          Шести хватало, чтобы не наезжать, но не хватало, чтобы читаться отдельно: строка ввода,
          «история разговоров» и панель слипались в одну кучу у нижнего края, а карточка
          приглашений прижималась к ним сверху. Теперь между доком и панелью настоящий промежуток —
          и карточка вместе с ним уезжает выше, потому что лента занимает то, что осталось.

          С поднятой клавиатурой зазор снова маленький: там панели нет вовсе, а место дорого.
        */}
        <View style={[s.dock, { paddingBottom: kb ? 6 : navH + space.lg }]}>
          <View style={s.askRow}>
            <View style={s.askAvatar}>
              <IconImagePlaceholder size={22} />
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={HOME.ask()}
              style={({ pressed }) => [s.askField, pressed && { opacity: 0.85 }]}
              onPress={toBuddy}
            >
              <Text style={s.askText}>{HOME.ask()}</Text>
              <IconMic />
            </Pressable>
          </View>
          {/*
            Кнопка обещает историю РАЗГОВОРОВ — теперь она её и открывает.

            До этого она вела в сегмент прошедших ЗАТЕЙ во вкладке «Интенты»: планы, а не
            разговоры. Ещё раньше — в чат с Бадди: это разговор, но не история. Оба раза подпись
            обещала одно, а кнопка делала другое, и второе было записано прямо здесь как
            компромисс. Экран истории теперь есть — модальным окном, см. app/history.tsx.
          */}
          <Pressable accessibilityRole="button" style={s.hist} onPress={() => router.navigate('/history')}>
            <IconChat />
            <Text style={s.histText}>{HOME.history()}</Text>
            <Text style={s.histArrow}>›</Text>
          </Pressable>
        </View>

      </KeyboardAvoidingView>

      {/*
        Панель ВНЕ KeyboardAvoidingView и прибита к низу экрана. Пока она была внутри, клавиатура
        поднимала её вместе с полем ввода — а ей место внизу, под клавиатурой: наверх едет только то,
        что человек в этот момент заполняет.
      */}
      <View
        style={s.navFloat}
        onLayout={(e) => setNavH(e.nativeEvent.layout.height)}
        pointerEvents="box-none"
      >
        <BottomNav />
      </View>
    </View>
  );
}

/** Небо за экраном. Заливка снизу вверх по тем же цветам, что в вебе. */
function Section({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <View style={s.sec}>
      {icon}
      <Text style={s.secText}>{title}</Text>
    </View>
  );
}

const CARD_W = 300;

function GroupCard({ g, myArea }: { g: Group; myArea: string }) {
  const w = splitWhen(g.when);
  const where = planWhere(g.area, '', myArea);
  return (
    <Pressable accessibilityRole="button" style={s.card}>
      {/* Обложка. Фотографий у планов нет, поэтому цветное поле, а не серый прямоугольник. */}
      <View style={s.cover}>
        <IconImagePlaceholder size={44} c="#ffffff88" />
        <View style={s.bm}><IconBookmark size={18} c={color.fg} /></View>
      </View>
      <View style={s.cardBody}>
        <Text style={s.cardTitle} numberOfLines={1}>{g.title}</Text>
        <View style={s.metaRow}>
          <IconCalendar />
          <Text style={s.meta}>{w.date}</Text>
          {w.time ? <><IconClock /><Text style={s.meta}>{w.time}</Text></> : null}
        </View>
        <View style={s.metaRow}>
          <IconPin size={16} c={color.muted} />
          <Text style={s.meta} numberOfLines={1}>{where}</Text>
        </View>
        <View style={s.foot}>
          {g.size > 0 ? (
            <Text style={s.footText}>{HOME.going(g.size)}</Text>
          ) : (
            <Text style={s.footText}>{HOME.hosting(g.host)}</Text>
          )}
        </View>
      </View>
    </Pressable>
  );
}

/**
 * Ближайшая встреча СТРОКОЙ, в том же сложении, что и приглашение: круглый значок слева, справа
 * подпись, название, время с местом и переход.
 *
 * Раньше это была отдельная плашка с другим радиусом и другой вёрсткой, стоявшая прямо над
 * карточкой приглашений. Два разных оформления в двенадцати пикселях друг от друга читаются
 * как случайность, а не как замысел.
 */
function NextMeetRow({ plan }: { plan: any }) {
  const router = useRouter();
  const when = [String(plan.when || '').trim(),
                plan.mode === 'online' ? HOME.onCall()
                  : String(plan.venue || plan.district || '').trim()].filter(Boolean).join(' · ');
  return (
    <Pressable
      accessibilityRole="button"
      style={({ pressed }) => [s.nextRow, pressed && { opacity: 0.7 }]}
      onPress={() => router.navigate({ pathname: '/plan', params: { id: String(plan.id || '') } })}
    >
      <View style={[s.meetAva, s.meetAvaEmpty]}>
        <IconCalendar size={26} c={color.muted} />
      </View>
      <View style={{ flex: 1 }}>
        {/* Подпись над названием — иначе, потеряв заголовок секции, строка перестаёт называть себя. */}
        <Text style={s.stackCap}>{HOME.next()}</Text>
        <Text style={s.meetName} numberOfLines={1}>
          {String(plan.title || '').trim() || HOME.next()}
        </Text>
        {when ? (
          <View style={s.meetMeta}>
            <IconClock />
            <Text style={s.meta} numberOfLines={1}>{when}</Text>
          </View>
        ) : null}
        <Text style={s.nextGo}>{HOME.goToPlan()}  ›</Text>
      </View>
    </Pressable>
  );
}

/** «Home Card · Empty»: то же тело, что у приглашения, но вместо человека — заглушка. */
function EmptyInviteCard({ onHeight }: { onHeight?: (h: number) => void }) {
  const router = useRouter();
  return (
    <View style={[s.meet, s.emptyCard]} onLayout={(e) => onHeight?.(e.nativeEvent.layout.height)}>
      <View style={[s.meetAva, s.meetAvaEmpty]}>
        <IconImagePlaceholder size={30} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={s.meetName} numberOfLines={1}>{HOME.noInvites()}</Text>
        <View style={s.meetMeta}>
          <IconClock />
          <Text style={s.meta} numberOfLines={1}>{HOME.noInvitesNote()}</Text>
        </View>
        {/*
          КНОПКА ЗАВОДИТ ИНТЕНТ, А НЕ ОТКРЫВАЕТ СПИСОК. Сначала она вела во вкладку интентов — но
          приглашений нет ровно потому, что человеку пока не с чем к кому-то прийти. Показать ему
          в этот момент пустой список значит ответить «смотри, тут тоже ничего». Приглашения
          появляются в ответ на затею, поэтому кнопка ведёт туда, где затея заводится.
          Без `seed`: что именно человек хочет, он ещё не сказал — в отличие от нажатия по
          предмету в колесе, где фраза уже выбрана.
        */}
        <Pressable
          accessibilityRole="button"
          style={({ pressed }) => [s.meetBtn, pressed && { opacity: 0.9 }]}
          onPress={() => {
            hCommit();
            router.navigate('/create');
          }}
        >
          <Text style={s.meetBtnText}>{HOME.discover()}</Text>
        </Pressable>
      </View>
    </View>
  );
}

function DirectInviteCard({ inv }: { inv: HomeInvite }) {
  const router = useRouter();
  const w = splitWhen(inv.intent.when || '');
  const where = inv.intent.area || '';
  const open = () => router.navigate({ pathname: '/invite', params: { id: inv.id } });
  return (
    <Pressable accessibilityRole="button" onPress={open} style={s.meet}>
      {inv.from.photo ? (
        <Image source={{ uri: mediaUrl(String(inv.from.photo)) }} style={s.meetAva} />
      ) : (
        <View style={[s.meetAva, s.meetAvaEmpty]}>
          <Text style={s.meetInit}>{(inv.from.name || '?').slice(0, 1).toUpperCase()}</Text>
        </View>
      )}
      <View style={{ flex: 1 }}>
        <View style={s.meetTop}>
          <Text style={s.meetName} numberOfLines={1}>
            {inv.from.name}{inv.from.age ? `, ${inv.from.age}` : ''}
          </Text>
          <View style={s.badge}><Text style={s.badgeText}>{HOME.match()}</Text></View>
        </View>
        {inv.intent.title ? <Text style={s.meetIntent} numberOfLines={1}>{inv.intent.title}</Text> : null}
        <View style={s.meetMeta}>
          {w.date || where ? (
            <>
              <IconClock />
              <Text style={s.meta}>{w.date}{w.time ? ` · ${w.time}` : ''}</Text>
              {where ? <><IconPin size={16} c={color.muted} /><Text style={s.meta} numberOfLines={1}>{where}</Text></> : null}
            </>
          ) : (
            <Text style={s.meta} numberOfLines={1}>{inv.note || HOME.wantsToMeet()}</Text>
          )}
        </View>
        <View style={s.meetBtn}>
          <Text style={s.meetBtnText}>{HOME.review()}</Text>
        </View>
      </View>
    </Pressable>
  );
}

function GroupInviteCard({ inv }: { inv: HomeInvite }) {
  const router = useRouter();
  const group = inv.group;
  const w = splitWhen(inv.intent.when || '');
  // Маршрут называется /ginvite — файл app/ginvite.tsx. Стояло `/group-invite`, которого нет:
  // expo-router на несуществующий путь молча ничего не делает, и карточка приглашения не
  // открывалась вовсе. Заметить это было нельзя, пока лента приглашений сама отдавала 404.
  // gid рядом с id — правка соседней ветки: экран приглашения без него не находит группу.
  const open = () => router.navigate({
    pathname: '/ginvite',
    params: { id: inv.id, gid: String(group?.gid || inv.intent.id || '') },
  });
  const participants = (group?.participants || []).slice(0, 5);
  const hidden = Math.max(0, (group?.participant_count || 0) - participants.length);

  /*
    ТА ЖЕ «Home Card», что у приглашения один на один, — так на борде.
    GR.01, «Invite Stack» [350×131]: три слоя, верхний — «Home Card» [350×110], а внутри неё
    Photo [86×86] слева и колонка [224×86] справа: строка имени с бейджем [224×16], строка
    «время · место» ОДНОЙ строкой [193×14] и кнопка [224×32].

    Здесь стояла карточка другого рода: обложка во всю ширину плюс семь блоков столбиком —
    около четырёхсот пунктов, во весь экран. Групповое приглашение — такое же приглашение, и
    отдельного вида у него на борде нет: разница только в том, что слева не одно лицо, а
    несколько, и под именем стоит, кто зовёт.
  */
  const cover = participants[0];
  return (
    <Pressable accessibilityRole="button" onPress={open} style={s.meet}>
      {/* Слева — кто уже внутри: стопка лиц вместо одного. Это единственное, чем групповая
          карточка отличается от одиночной, и ровно так же выглядит на кадре. */}
      <View style={s.groupFaces}>
        {participants.slice(0, 3).map((person, index) => (
          <View
            key={`${person.name}-${index}`}
            style={[s.faceAva, s.faceAvaEmpty,
                    { marginLeft: index ? -14 : 0, zIndex: 3 - index }]}
          >
            <Text style={s.faceInit}>{(person.name || '?').slice(0, 1).toUpperCase()}</Text>
            {person.photo ? (
              <Image source={{ uri: mediaUrl(String(person.photo)) }}
                     style={[s.faceAva, StyleSheet.absoluteFillObject]} />
            ) : null}
          </View>
        ))}
        {hidden > 0 ? (
          <View style={[s.faceAva, s.faceMore, { marginLeft: participants.length ? -14 : 0 }]}>
            <Text style={s.faceMoreText}>+{hidden}</Text>
          </View>
        ) : null}
        {!participants.length ? (
          <View style={[s.faceAva, s.faceAvaEmpty]}><IconGroups size={20} c={color.muted} /></View>
        ) : null}
      </View>

      <View style={{ flex: 1 }}>
        <View style={s.meetTop}>
          <Text style={s.meetName} numberOfLines={1}>
            {inv.intent.title || inv.from.name}
          </Text>
          <View style={s.badge}><Text style={s.badgeText}>{HOME.inviteKindGroup()}</Text></View>
        </View>

        {/* Кто зовёт. Имя стояло лишь запасным вариантом заголовка — у группы с названием
            («Книжный клуб») не показывалось нигде, хотя зовёт человека человек. */}
        {inv.from?.name ? (
          <Text style={s.meetIntent} numberOfLines={1}>{HOME.hosting(String(inv.from.name))}</Text>
        ) : null}

        {/* Время и место — ОДНОЙ строкой, как на кадре [193×14], а не двумя блоками. */}
        <View style={s.meetMeta}>
          <IconClock />
          <Text style={s.meta} numberOfLines={1}>
            {w.date}{w.time ? ` · ${w.time}` : ''}
          </Text>
          {inv.intent.area ? (
            <>
              <IconPin size={16} c={color.muted} />
              <Text style={s.meta} numberOfLines={1}>{inv.intent.area}</Text>
            </>
          ) : null}
          <Text style={s.meta}>
            · {HOME.peopleCount(group?.participant_count || 0, group?.max_size)}
          </Text>
        </View>

        <View style={s.meetBtn}>
          <Text style={s.meetBtnText}>{HOME.review()}</Text>
        </View>
      </View>
    </Pressable>
  );
}

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, paddingBottom: space.md },
  /* Насыщенность задаётся ГАРНИТУРОЙ, а не `fontWeight`: на подключённом файле вес не работает. */
  hello: { flex: 1, fontSize: 26, lineHeight: 34, color: color.fg },

  /*
    `flexGrow` и центрирование нужны ради колеса: без них содержимое прижимается к шапке, и «по
    центру экрана» превращается в «сразу под ней». Центрируется именно СОДЕРЖИМОЕ, а не блок с
    колесом: когда колесо и карточка вместе выше экрана, лента должна прокручиваться, а не
    сжимать их — `flex: 1` на блоке в прокрутке как раз и приводит к сжатию.
  */
  scroll: { flexGrow: 1, justifyContent: 'center', paddingBottom: 20, gap: space.sm },
  /** Всё, что под колесом: своя отбивка, чтобы блок не липнул к картинке. */
  below: { gap: space.sm },
  wheel: { gap: space.lg },
  /** Секция приглашений внутри нижнего блока. */
  stack: { gap: space.sm },
  /** Пустая карточка стоит вплотную к колесу — она его продолжение, а не отдельная секция. */
  emptyCard: { marginTop: 0 },
  sec: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 20, marginTop: space.md },
  secText: { ...type.labelMedium, color: color.fg, fontWeight: '700' } as any,
  empty: { ...type.bodySmall, color: color.ink, opacity: 0.65, paddingHorizontal: 20 } as any,
  inviteError: { gap: space.sm, alignItems: 'flex-start' },
  retryBtn: { marginLeft: 20, paddingVertical: 8, paddingHorizontal: 14, borderRadius: rad.full, backgroundColor: color.card },
  retryText: { ...type.labelSmall, color: color.primary, fontWeight: '700' } as any,

  carousel: { paddingHorizontal: 20, gap: space.md, paddingVertical: 4 },
  card: {
    width: CARD_W, borderRadius: rad.xl, backgroundColor: color.card, overflow: 'hidden',
    shadowColor: '#000', shadowOpacity: 0.1, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 3,
  },
  cover: { height: 128, backgroundColor: color.coverFallback, alignItems: 'center', justifyContent: 'center' },
  bm: {
    position: 'absolute', top: 12, right: 12, width: 30, height: 30, borderRadius: 15,
    backgroundColor: '#ffffffe6', alignItems: 'center', justifyContent: 'center',
  },
  cardBody: { padding: 14, gap: 6 },
  cardTitle: { fontSize: 17, fontWeight: '700', color: color.fg },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  meta: { ...type.bodySmall, color: color.muted, flexShrink: 1 } as any,
  foot: { marginTop: 4, paddingTop: 10, borderTopWidth: 1, borderTopColor: color.neutral100 },
  footText: { ...type.bodySmall, color: color.muted } as any,

  meet: {
    flexDirection: 'row', gap: space.md, marginHorizontal: 20, padding: 14,
    borderRadius: rad.xl, backgroundColor: color.card,
    shadowColor: '#000', shadowOpacity: 0.09, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 3,
  },
  meetAva: { width: 62, height: 62, borderRadius: rad.full },
  meetAvaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  meetInit: { fontSize: 22, fontWeight: '700', color: color.muted },
  meetTop: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  meetName: { flex: 1, fontSize: 17, fontWeight: '700', color: color.fg },
  badge: { paddingHorizontal: 10, height: 24, borderRadius: rad.full, backgroundColor: color.successBg, justifyContent: 'center' },
  badgeText: { ...type.labelSmall, color: color.successText, fontWeight: '600' } as any,
  meetIntent: { ...type.bodySmall, color: color.fg, marginTop: 2 } as any,
  meetMeta: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6, flexWrap: 'wrap' },
  meetBtn: {
    height: 44, borderRadius: rad.full, backgroundColor: color.primary,
    alignItems: 'center', justifyContent: 'center', marginTop: 12,
    // Свечение фирменного цвета под кнопкой — как у всех главных кнопок приложения.
    shadowColor: color.primary, shadowOpacity: 0.3, shadowRadius: 14, shadowOffset: { width: 0, height: 6 },
    elevation: 6,
  },
  meetBtnText: { ...type.button, color: color.onPrimary } as any,

  /**
   * Лица группы слева — вместо одного фото на одиночной карточке. Кадр GR.01 отводит под
   * Photo 86×86; три лица внахлёст занимают ту же полосу.
   */
  groupFaces: { flexDirection: 'row', alignItems: 'center' },
  faceAva: { width: 44, height: 44, borderRadius: rad.full, borderWidth: 2, borderColor: color.card, overflow: 'hidden' },
  faceAvaEmpty: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  faceInit: { fontSize: 16, fontWeight: '700', color: color.muted },
  faceMore: { backgroundColor: color.neutral100, alignItems: 'center', justifyContent: 'center' },
  faceMoreText: { ...type.labelSmall, color: color.muted, fontWeight: '700' } as any,

  /*
    ОТБИВКА НАД ДОКОМ БОЛЬШЕ, ЧЕМ ЗАЗОР ВНУТРИ НЕГО. Было восемь точек и там, и там: карточка
    приглашений и строка ввода — оба белые прямоугольника — почти касались друг друга и читались
    как один блок в две полосы. Между РАЗНЫМИ вещами промежуток обязан быть заметно больше, чем
    между частями одной; иначе граница пропадает, и глаз собирает их вместе.
  */
  dock: { paddingHorizontal: 16, gap: space.md, paddingTop: 20, paddingBottom: 6 },
  askRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  askAvatar: {
    width: 46, height: 46, borderRadius: 23, backgroundColor: color.onCoverSoft,
    alignItems: 'center', justifyContent: 'center',
  },
  askField: {
    flex: 1, height: 50, borderRadius: rad.full, backgroundColor: color.card,
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, gap: space.sm,
  },
  askText: { flex: 1, color: color.neutral400, fontSize: 15 },
  navFloat: { position: 'absolute', left: 0, right: 0, bottom: 0 },
  /** Карточка ближайшей встречи — кадр O.01, блок Activity. Только токены, как и всё на экране. */
  /** Строка встречи внутри своей карточки: то же сложение, что у приглашения. */
  /*
    `flex: 1` ОБЯЗАТЕЛЕН. Карточка `meet` — строка, и эта нажимаемая строка её единственный ребёнок:
    без растяжения она сжимается по содержимому, а колонка текста внутри получает нулевую ширину —
    на снимке от значка календаря остались только он сам да часики, весь текст исчез.
  */
  nextRow: { flex: 1, flexDirection: 'row', alignItems: 'flex-start', gap: space.md },
  /** Подпись над названием: карточка обязана называть себя, раз заголовка секции над ней нет. */
  stackCap: { ...type.labelSmall, color: color.muted, marginBottom: 2 } as any,

  nextCard: {
    marginHorizontal: space.lg, marginBottom: space.md, padding: space.lg,
    borderRadius: rad.lg, backgroundColor: color.card, gap: 4,
    shadowColor: '#000', shadowOpacity: 0.09, shadowRadius: 14,
    shadowOffset: { width: 0, height: 6 }, elevation: 3,
  },
  nextTitle: { ...type.title, color: color.fg } as any,
  nextWhen: { ...type.bodySmall, color: color.muted } as any,
  nextGo: { ...type.labelMedium, color: color.primary, marginTop: 4 } as any,

  hist: {
    alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 8,
    height: 36, paddingHorizontal: 16, borderRadius: rad.full, backgroundColor: color.card,
  },
  histText: { ...type.bodySmall, color: color.fg } as any,
  histArrow: { color: color.primary, fontSize: 18, fontWeight: '700' },
});
