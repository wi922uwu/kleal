/**
 * Логотип Kleal: `LogoMark` — капля крупно (A.03, 186×167) и `LogoFace` — она же в шапке чата.
 * (`Wordmark` — капля со словом — нигде не рисовался и удалён при чистке 18.10.2026.)
 *
 * ЭТО ЭКСПОРТ ИЗ FIGMA, а не нарисованные заново. У капли внутри радиальный градиент, стеклянная
 * плёнка с размытием подложки, падающая и внутренняя тени.
 * Повторить это на SVG в RN можно, но результат отличался бы — а логотип это ровно то место, где
 * «почти похоже» читается как ошибка. Поэтому картинка.
 *
 * Пропорции зашиты константой: они постоянные, и вызывающему достаточно задать
 * ширину. Растягивать логотип по месту нельзя, поэтому высота считается, а не принимается.
 */
import { Image, StyleSheet, View } from 'react-native';

/** Пропорции из борда: 186×167. */
const MARK_RATIO = 167 / 186;

export function LogoMark({ width = 186 }: { width?: number }) {
  return (
    <Image
      accessibilityIgnoresInvertColors
      source={require('../../assets/art/logo-mark.png')}
      style={[s.img, { width, height: width * MARK_RATIO }]}
      resizeMode="contain"
    />
  );
}

/**
 * Мордочка Kleal в шапке разговора и в окне создания.
 *
 * С 18.10.2026 — НАСТОЯЩАЯ КАПЛЯ, а не рисунок. Раньше здесь был плоский круг с градиентом и двумя
 * овалами: рядом с каплей в навбаре (стекло, мягкий край, хвостик) он читался подделкой, и Иван
 * попросил заменить на «нормального». Берётся та же картинка, что у логотипа (уже прогрета в
 * _layout), чуть крупнее рамки: у картинки прозрачные поля, и видимое пятно иначе было бы мельче
 * прежнего круга.
 */
export function LogoFace({ size = 49 }: { size?: number }) {
  const w = size * 1.22;
  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Image
        accessibilityIgnoresInvertColors
        source={require('../../assets/art/logo-mark.png')}
        style={{ position: 'absolute', width: w, height: w * MARK_RATIO }}
        resizeMode="contain"
      />
    </View>
  );
}

// ===== вид
const s = StyleSheet.create({
  img: { alignSelf: 'center' },
});
