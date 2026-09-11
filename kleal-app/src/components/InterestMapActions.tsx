import React from 'react';
import { StyleSheet, View } from 'react-native';
import { STEP_HOBBIES } from '../onboarding';
import { space } from '../theme';
import { GlassPill } from './Glass';

export function InterestMapActions({ selected, onDone }: {
  selected: string[];
  onDone: (keys: string[], own?: boolean) => void;
}) {
  const need = 3;
  return (
    <View style={styles.actions} testID="interest-map-actions">
      <GlassPill label={STEP_HOBBIES.mapOwn()} labelLines={3} style={styles.action}
        onPress={() => onDone(selected, true)} />
      <GlassPill
        label={selected.length >= need ? STEP_HOBBIES.mapCount(selected.length) : STEP_HOBBIES.mapMin(need)}
        labelLines={3}
        tone="brand"
        style={styles.action}
        disabled={selected.length < need}
        onPress={() => { if (selected.length >= need) onDone(selected); }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  actions: { gap: space.sm },
  action: { height: 'auto', minHeight: 48, paddingVertical: space.sm, paddingHorizontal: space.md },
});
