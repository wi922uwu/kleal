/**
 * Точечная правка сводки интента.
 *
 * Контролы в листе работают с полной копией Draft — им нужны соседние значения, чтобы правильно
 * показать диапазон, карту и зависимости. Но наружу разрешено выпустить только поля выбранного
 * параметра. Это защищает от двух вещей сразу: «Отмена» ничего не меняет, а случайное изменение
 * соседнего контрола не перезаписывает уже собранный интент.
 */
export type IntentEditTarget =
  | 'mode' | 'size' | 'groupSize'
  | 'date' | 'time' | 'timezone'
  | 'audience' | 'nature'
  | 'place' | 'link' | 'both';

export type EditableIntentDraft = {
  mode?: string;
  size?: '1:1' | 'group';
  groupSize?: number;
  date: string;
  minutes: number;
  tz: string;
  sex?: string;
  minAge: number;
  maxAge: number;
  nature: Record<string, string>;
  district?: string;
  radiusKm: number;
  link: string;
  address?: string;
  lat?: number;
  lon?: number;
};

/** Новая независимая сессия правки; вложенный nature тоже нельзя разделять с живым draft. */
export function beginIntentEdit<D extends EditableIntentDraft>(draft: D): D {
  return { ...draft, nature: { ...draft.nature } };
}

const placePatch = <D extends EditableIntentDraft>(from: D) => ({
  district: from.district,
  radiusKm: from.radiusKm,
  address: from.address,
  lat: from.lat,
  lon: from.lon,
});

/**
 * Коммитит ровно выбранный параметр. Несовместимое поле очищается только в одном подтверждённом
 * случае: у 1:1 нет размера группы. При обратном переходе размер показывается человеку в том же
 * листе и сохраняется явно; скрытого фиксированного размера нет.
 */
export function applyIntentEdit<D extends EditableIntentDraft>(
  original: D,
  edited: D,
  target: IntentEditTarget,
): D {
  const next: D = beginIntentEdit(original);
  if (target === 'mode') {
    return {
      ...next,
      mode: edited.mode,
      // Единственная запрашиваемая зависимость режима: Group Online нельзя сохранить без ссылки.
      ...(edited.mode === 'online' && edited.size === 'group' ? { link: edited.link } : {}),
    };
  }
  if (target === 'size') {
    return {
      ...next,
      size: edited.size,
      groupSize: edited.size === 'group' ? edited.groupSize : undefined,
      // При переходе в Group ссылка коммитится только если она стала обязательной и была показана.
      ...(edited.size === 'group' && edited.mode === 'online' ? { link: edited.link } : {}),
    };
  }
  if (target === 'groupSize') {
    return { ...next, size: 'group', groupSize: edited.groupSize };
  }
  if (target === 'date') return { ...next, date: edited.date };
  if (target === 'time') return { ...next, minutes: edited.minutes };
  if (target === 'timezone') return { ...next, tz: edited.tz };
  if (target === 'audience') {
    return { ...next, sex: edited.sex, minAge: edited.minAge, maxAge: edited.maxAge };
  }
  if (target === 'nature') return { ...next, nature: { ...edited.nature } };
  if (target === 'place') return { ...next, ...placePatch(edited) };
  if (target === 'link') return { ...next, link: edited.link };
  return { ...next, ...placePatch(edited), link: edited.link };
}
