/**
 * ДЕЙСТВИЕ НАД ПОЛЕМ ВВОДА — одна компактная кнопка по центру, как «Make the plan» на борде
 * (GR.21): не полоса во всю ширину, а пилюля по подписи с фирменным свечением, к которой ведёт
 * глаз. Слева — необязательный крестик в стеклянном круге: убрать подсказку, если она сейчас
 * не нужна. Крестик показывается, только когда у действия есть другой путь; единственный выход
 * со шага им не прячут.
 *
 * Стоит в слоте `footer` чат-оболочки: над композером и вне прокрутки ленты — её не надо искать.
 */
import { StyleSheet, View } from 'react-native';
import { GlassPill } from './Glass';
import { GlassIconButton } from './LiquidGlass';
import { IconClose } from './icons';

export function DockAction({
  label, onPress, disabled, busy, tone = 'brand', onDismiss, dismissLabel = '', compact = false,
}: {
  label: string;
  onPress?: () => void;
  disabled?: boolean;
  busy?: boolean;
  /** Коралловая — главное действие; светлое стекло — предложение, а не призыв (GR.18). */
  tone?: 'brand' | 'light';
  /** Есть — слева крестик, убирающий подсказку. */
  onDismiss?: () => void;
  dismissLabel?: string;
  /** Размер борда «GR · Offline — new layout»: кнопка и крестик по 40 (GR.18/GR.21). */
  compact?: boolean;
}) {
  return (
    <View style={s.row}>
      {onDismiss ? (
        <GlassIconButton label={dismissLabel} onPress={onDismiss} size={compact ? 40 : 44}>
          <IconClose size={20} />
        </GlassIconButton>
      ) : null}
      <GlassPill tone={tone} label={label} onPress={onPress} disabled={disabled} busy={busy}
                 small={compact} style={compact ? s.pillSmall : s.pill} />
    </View>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, paddingVertical: 4 },
  /** Высота 48 и поля по подписи — кнопка ровно такого размера, как её слово. */
  pill: { height: 48, minWidth: 150 },
  pillSmall: { height: 40 },
});
