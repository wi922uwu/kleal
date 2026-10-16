import React, { useEffect, useMemo, useState } from 'react';
import { AppState, View, Text, Pressable, ActivityIndicator, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { ProfileShell, Card } from '../src/components/ProfileShell';
import { useLang } from '../src/i18n';
import { useOnb } from '../src/state';
import { getSession } from '../src/api';
import { MembershipClient, MembershipView } from '../src/membership-client';
import { PLUS, expiresLabel, referencePrice, Product } from '../src/monetization';
import { color, radius, space, type } from '../src/theme';

export default function Plus() {
  useLang();
  const router = useRouter();
  const session = useOnb().session || '';
  const client = useMemo(() => new MembershipClient(), []);
  const [view, setView] = useState<MembershipView>(client.view);
  const [selected, select] = useState<Product['id']>('plus_monthly');
  const [confirm, setConfirm] = useState(false);
  useEffect(() => {
    const unsubscribe = client.subscribe(setView);
    return () => { unsubscribe(); client.dispose(); };
  }, [client]);
  useEffect(() => { setConfirm(false); void client.load(); }, [client, session]);
  useEffect(() => {
    const listener = AppState.addEventListener('change', (state) => { if (state === 'active') void client.load(); });
    const timer = setInterval(() => { if (AppState.currentState === 'active') void client.load(); }, 60000);
    return () => { listener.remove(); clearInterval(timer); };
  }, [client]);
  // Even before React's account-change effect, never paint the previous owner's membership.
  const current = view.session === getSession();
  const data = current ? view.data : null;
  const busy = !current || view.busy;
  const error = current ? view.error : null;
  return (
    <ProfileShell title={PLUS.title()} onBack={() => router.canGoBack() ? router.back() : router.replace('/settings')}>
      <Text style={s.hero}>{PLUS.lead()}</Text>
      <Card>
        <Text style={s.label}>{PLUS.stage()}</Text>
        <Text style={s.body}>{PLUS.stageNote()}</Text>
      </Card>
      {busy ? <View style={s.loading} accessibilityLiveRegion="polite"><ActivityIndicator color={color.primary} /><Text style={s.body}>{PLUS.loading()}</Text></View> : null}
      {error ? <Card><Text accessibilityRole="alert" style={s.error}>{error === 'sign_in' ? PLUS.login() : PLUS.error()}</Text><Button label={PLUS.retry()} onPress={() => { void client.load(); }} /></Card> : null}
      {data ? <>
        <Card>
          <Text accessibilityLiveRegion="polite" style={s.title}>{data.state === 'preview' ? PLUS.preview() : data.state === 'expired' ? PLUS.expired() : PLUS.free()}</Text>
          {data.state === 'preview' && data.expiresAt ? <Text style={s.label}>{PLUS.until(expiresLabel(data.expiresAt))}</Text> : null}
          <Text style={s.body}>{PLUS.preserved()}</Text>
        </Card>
        <Text style={s.title}>{PLUS.compare()}</Text>
        {data.products.map((product) => <Pressable key={product.id} accessibilityRole="radio" accessibilityState={{ checked: selected === product.id }}
          onPress={() => select(product.id)} style={[s.option, selected === product.id && s.selected]}>
          <Text style={s.title}>{product.period === 'month' ? PLUS.monthly() : PLUS.annual()}</Text>
          <Text style={s.price}>{referencePrice(product)}</Text>
          <Text style={s.body}>{PLUS.period(product.period)}</Text>
        </Pressable>)}
        <Text style={s.note}>{PLUS.priceNote()}</Text>
        <Card><Text style={s.body}>{PLUS.features()}</Text></Card>
        {data.canStartPreview && !confirm ? <Button label={PLUS.start()} onPress={() => setConfirm(true)} /> : null}
        {data.canStartPreview && confirm ? <Card>
          <Text style={s.title}>{PLUS.consent()}</Text><Text style={s.body}>{PLUS.consentNote()}</Text>
          <Button label={PLUS.confirm()} onPress={() => { setConfirm(false); void client.start(); }} />
          <Button secondary label={PLUS.cancel()} onPress={() => setConfirm(false)} />
        </Card> : null}
        {!data.previewEnabled ? <Text style={s.note}>{PLUS.unavailable()}</Text> : null}
        <Button disabled label={PLUS.purchase()} onPress={() => {}} />
        <Text style={s.note}>{PLUS.restore()}</Text>
        <Button secondary label={PLUS.retry()} onPress={() => { void client.load(); }} />
      </> : null}
    </ProfileShell>
  );
}

function Button({ label, onPress, disabled = false, secondary = false }: { label: string; onPress: () => void; disabled?: boolean; secondary?: boolean }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress}
    style={[s.button, secondary && s.secondary, disabled && s.disabled]}><Text style={[s.buttonText, secondary && s.secondaryText]}>{label}</Text></Pressable>;
}

// ===== вид — existing Kleal tokens; scrollable actions and flexible text for both mobile platforms.
const s = StyleSheet.create({
  hero: { ...type.h2, color: color.fg, marginBottom: space.lg },
  title: { ...type.title, color: color.fg, marginBottom: space.sm },
  label: { ...type.labelMedium, color: color.primary, marginBottom: space.sm },
  body: { ...type.body, color: color.muted },
  note: { ...type.caption, color: color.muted, marginVertical: space.md },
  error: { ...type.body, color: color.danger },
  price: { ...type.h2, color: color.fg },
  option: { borderWidth: 2, borderColor: color.border, backgroundColor: color.card, borderRadius: radius.xl, padding: space.lg, marginBottom: space.sm },
  selected: { borderColor: color.primary },
  button: { minHeight: 48, borderRadius: radius.full, backgroundColor: color.primary, justifyContent: 'center', alignItems: 'center', padding: space.md, marginTop: space.sm },
  buttonText: { ...type.button, color: color.onPrimary, textAlign: 'center' },
  secondary: { backgroundColor: color.neutral100 },
  secondaryText: { color: color.fg },
  disabled: { opacity: 0.5 },
  loading: { paddingVertical: space.lg, gap: space.sm, alignItems: 'center' },
});
