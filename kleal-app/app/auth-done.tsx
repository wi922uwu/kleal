/**
 * A.03.3 — «Ты в деле».
 *
 * Показывается ТОЛЬКО новому. Борд разводит два исхода стрелками: новый аккаунт → A.03.3 → анкета
 * A.04; существующий → сразу на главную, и A.03.3 пропускается. Поэтому решение принимает экран
 * кода (по `isNew` с сервера), а не этот: сюда просто не приходят те, кому он не нужен.
 *
 * ЭТО ЕДИНСТВЕННЫЙ КАДР ПОТОКА БЕЗ ФОРМЫ — и в борде он единственный цветной: тёплое пятно во
 * весь центр и иллюстрация поверх него. Два предыдущих экрана намеренно бледные, потому что там
 * набирают текст; здесь набирать нечего, и цвет наконец можно вернуть.
 */
import React from 'react';
import { View, Text, StyleSheet, Image } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import Svg, { Defs, Ellipse, RadialGradient, Stop } from 'react-native-svg';
import { AUTH } from '../src/auth';
import { useLang } from '../src/i18n';
import { Ambient, GLOW_DONE } from '../src/components/Ambient';
import { GlassPill } from '../src/components/Glass';
import { color, displayFamily, space, type } from '../src/theme';

/**
 * Ореол под иллюстрацией.
 *
 * В борде это эллипс с линейным градиентом из фирменного красного в янтарь, размытый на 100 —
 * то есть от самого градиента остаётся только тёплое свечение. Размытия слоя в RN нет (`expo-blur`
 * размывает то, что ПОД видом, а не сам вид), и повторять его нечем. Но размытый двухцветный
 * эллипс и два мягких пятна рядом дают на глаз одно и то же, а стоят один Svg вместо нативного
 * фильтра — тем более что радиальный градиент и так гаснет к краю, как размытие.
 */
function Halo({ size }: { size: number }) {
  return (
    <Svg width={size} height={size} style={s.halo} pointerEvents="none">
      <Defs>
        <RadialGradient id="h0">
          <Stop offset="0" stopColor={color.primary} stopOpacity={0.55} />
          <Stop offset="1" stopColor={color.primary} stopOpacity={0} />
        </RadialGradient>
        <RadialGradient id="h1">
          <Stop offset="0" stopColor={color.ambientAmber} stopOpacity={0.6} />
          <Stop offset="1" stopColor={color.ambientAmber} stopOpacity={0} />
        </RadialGradient>
      </Defs>
      {/* Красный выше и левее, янтарь ниже и правее — так же, как идёт градиент в борде. */}
      <Ellipse cx={size * 0.42} cy={size * 0.4} rx={size * 0.42} ry={size * 0.36} fill="url(#h0)" />
      <Ellipse cx={size * 0.6} cy={size * 0.62} rx={size * 0.38} ry={size * 0.32} fill="url(#h1)" />
    </Svg>
  );
}

export default function AuthDone() {
  const lang = useLang();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <View style={s.wrap}>
      <Ambient glows={GLOW_DONE} />
      <View style={[s.page, { paddingTop: insets.top + 24, paddingBottom: insets.bottom + space.lg }]}>
        <View style={s.mid}>
          <View style={s.art}>
            <Halo size={HALO} />
            <Image
              accessibilityIgnoresInvertColors
              source={require('../assets/art/auth-keyhole.png')}
              style={s.pic}
              resizeMode="contain"
            />
          </View>
          {/* Гарнитура заголовка зависит от языка — см. displayFamily. */}
          <Text style={[s.h, { fontFamily: displayFamily(lang) }]}>{AUTH.doneTitle()}</Text>
          <Text style={s.note}>{AUTH.doneNote()}</Text>
        </View>

        {/*
          `replace`, а не переход: назад отсюда возвращаться некуда и незачем — код уже погашен,
          сессия выдана, а экран ввода кода за спиной означал бы кнопку в никуда.
        */}
        <GlassPill
          tone="brand"
          label={AUTH.setUp()}
          onPress={() => router.replace('/chat')}
          style={s.cta}
        />
      </View>
    </View>
  );
}

// ===== вид
/** Иллюстрация из борда и ореол вокруг неё: ореол заметно шире, иначе он читается как рамка. */
const PIC = 195;
const HALO = 300;

const s = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: color.ambientBase },
  page: { flex: 1, paddingHorizontal: 24 },
  mid: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  art: { width: HALO, height: HALO, alignItems: 'center', justifyContent: 'center' },
  halo: { ...StyleSheet.absoluteFill },
  pic: { width: PIC, height: PIC },
  h: { ...type.display, color: color.fg, textAlign: 'center', marginTop: space.sm } as any,
  note: {
    ...type.displaySubLg,
    color: color.muted,
    textAlign: 'center',
    marginTop: space.md,
    paddingHorizontal: space.md,
  } as any,
  // Кнопка входа выше стеклянных: у неё в борде своя высота, 56 против 52.
  cta: { height: 56 },
});
