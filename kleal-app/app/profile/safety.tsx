/**
 * Профиль → «Безопасность и приватность».
 *
 * ЧТО ЗДЕСЬ БЫЛО. Пятнадцать переключателей в пяти группах: «не встречаться поздно вечером»,
 * «избегать баров», «делиться планом с доверенным контактом», «никогда не делать выводов о
 * чувствительном», «не сводить меня с теми, кого я могу знать» и так далее. Сверка с боевым кодом
 * показала, что девять из них не читает НИКТО и НИГДЕ, ещё три пишет онбординг, но подбор их не
 * смотрит. Даже «поставить Kleal на паузу» уходила в поле `safety.paused`, которого не читает ни
 * одна служба, — а подбор смотрит на `receiving.status`. Человек двигал ползунок, и не менялось
 * ничего.
 *
 * Обещание безопасности, которое ничего не делает, хуже отсутствия обещания: на него полагаются.
 *
 * ЧТО ВМЕСТО. Осталось ровно то, что исполняется: список заблокированных (жёсткий фильтр подбора,
 * в обе стороны) и два экрана настроек над политикой приёма, которую подбор читает по-настоящему.
 * Экран стал коротким — потому что правды оказалось ровно на столько.
 */
import { useCallback, useState } from 'react';
import { useRouter, useFocusEffect } from 'expo-router';
import { ProfileShell, SectionHead, LinkRow } from '../../src/components/ProfileShell';
import { IconUserLock, IconUserX, IconClock } from '../../src/components/icons';
import { useLang, T } from '../../src/i18n';
import { useOnb } from '../../src/state';
import { agent } from '../../src/api';
import { SECTIONS } from '../../src/profile';
import { BLOCKED, VISIBILITY, AVAILABILITY, SETTING_ROWS } from '../../src/settings';

/*
  БОРД «Profile — new layout», B.08. Решение владельца 17.10.2026: только то, что работает. Правила
  встреч («Public places first», «No late one-on-ones»…) и «What Kleal uses for matching» сервер пока не
  исполняет — они появятся здесь, когда агент логики их сделает (список отправлен 17.10).
*/
export default function Safety() {
  useLang();
  const router = useRouter();
  const st = useOnb();
  const me = String(st.profile.name || '');
  const [blocked, setBlocked] = useState<number | null>(null);

  // Счётчик — с сервера и на каждый приход: человек возвращается сюда, сняв блокировку.
  useFocusEffect(useCallback(() => {
    if (!me) return;
    agent.safety(me).then((r: any) => setBlocked(Array.isArray(r?.blocked) ? r.blocked.length : 0)).catch(() => {});
  }, [me]));

  return (
    <ProfileShell title={SECTIONS[2].title()} onBack={() => router.back()}>
      <SectionHead
        title={T('Всё под твоим контролем', 'You’re in control', 'Tú mandas')}
        note={T('Kleal показывает район города, а не точное место. Уйти из поиска можно одним касанием — на паузе тебя не находит никто.',
          'Kleal shares your city area, never your exact spot. Leave search with one tap — while paused, nobody can find you.',
          'Kleal muestra tu zona, nunca tu sitio exacto. Sal de la búsqueda con un toque: en pausa nadie te encuentra.')}
      />
      <LinkRow Icon={IconUserLock} title={VISIBILITY.title()} sub={SETTING_ROWS.find((r) => r.id === 'visibility')!.sub()}
               onPress={() => router.navigate('/settings/visibility')} />
      <LinkRow Icon={IconClock} title={AVAILABILITY.title()} sub={SETTING_ROWS.find((r) => r.id === 'availability')!.sub()}
               onPress={() => router.navigate('/settings/availability')} />
      <LinkRow Icon={IconUserX} title={BLOCKED.title()}
               sub={blocked == null ? BLOCKED.lead() : blocked ? BLOCKED.row(blocked) : BLOCKED.none()}
               onPress={() => router.navigate('/settings/blocked')} />
    </ProfileShell>
  );
}
