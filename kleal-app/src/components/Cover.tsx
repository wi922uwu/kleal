/**
 * Обложка карточки — фотография по теме затеи.
 *
 * Раньше на этом месте во всех шести экранах стоял плоский прямоугольник со значком-заглушкой:
 * у затеи про падел и у затеи про настолки он выглядел одинаково, и полоса сверху карточки не
 * сообщала ничего. Теперь у каждой из 51 подгруппы таксономии своя фотография (см. src/covers.ts).
 *
 * ЧТО ЭТОТ КОМПОНЕНТ БЕРЁТ НА СЕБЯ и о чём экрану больше думать не надо:
 *   — сам выбирает картинку по теме, категории или названию;
 *   — держит цвет под ней, пока она грузится, и остаётся с ним, если не загрузилась вовсе;
 *   — кладёт лёгкое затемнение, без которого белые чипы и закладка теряются на светлом кадре.
 *
 * Всё, что лежало поверх обложки — чипы состояния, закладка, — передаётся детьми и рисуется над
 * картинкой в прежнем виде: экраны свою разметку не меняют.
 */
import React, { useState } from 'react';
import { Image, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import { coverFor, coverOfSub } from '../covers';
import { color } from '../theme';

export function Cover({
  intent, sub, style, children,
}: {
  /** Затея целиком: темы, категория, название — по ним и выбирается картинка. */
  intent?: any;
  /** Либо прямо подгруппа, когда затеи под рукой нет, а тема известна. */
  sub?: string;
  /** Стиль полосы: высота и скругления у каждого экрана свои, они остаются его делом. */
  style?: StyleProp<ViewStyle>;
  children?: React.ReactNode;
}) {
  /*
    Сеть может не дойти — у этого продукта такое не редкость, российские операторы режут чужие
    адреса. Тогда остаётся ровный фирменный цвет, то есть ровно то, что было здесь до картинок:
    хуже прежнего не станет никогда.
  */
  const [failed, setFailed] = useState(false);
  const uri = sub ? coverOfSub(sub) : coverFor(intent);

  return (
    <View style={style}>
      {failed ? null : (
        <Image
          source={{ uri }}
          style={s.img}
          resizeMode="cover"
          onError={() => setFailed(true)}
          // Обложка — украшение: читать её вслух нечего, а имени затеи она не заменяет.
          accessible={false}
        />
      )}
      {/* Затемнение снизу: белый чип на светлом небе иначе не читается. */}
      {failed ? null : <View style={s.scrim} pointerEvents="none" />}
      {children}
    </View>
  );
}

const s = StyleSheet.create({
  // Явные координаты, а не absoluteFillObject: в RN 0.86 его нет.
  img: { position: 'absolute', left: 0, top: 0, right: 0, bottom: 0, backgroundColor: color.coverFallback },
  scrim: { position: 'absolute', left: 0, top: 0, right: 0, bottom: 0, backgroundColor: 'rgba(17,19,26,0.18)' },
});
