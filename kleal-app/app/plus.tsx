import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, Pressable, ActivityIndicator, StyleSheet } from 'react-native';
import { useMonetizationDialog } from '../src/components/MonetizationDialog';
import { useFocusEffect, useRouter } from 'expo-router';
import { ProfileShell, Card } from '../src/components/ProfileShell';
import { useLang } from '../src/i18n';
import { usePolling } from '../src/polling';
import { useOnb } from '../src/state';
import { api, getSession } from '../src/api';
import { MembershipClient, MembershipView } from '../src/membership-client';
import { PLUS, MONETIZATION, membershipPresentation, searchStateLabel, isMembershipV2 } from '../src/monetization';
import { blurReturnAction, navigateReturnAction, cancelReturnAction, returnAction, returnActionRoute, resumeReturnAction } from '../src/monetization-actions';
import { color, radius, space, type } from '../src/theme';

export default function Plus() {
  useLang();
  const router = useRouter();
  const session = useOnb().session || '';
  const dialog=useMonetizationDialog(session,getSession);
  const client = useMemo(() => new MembershipClient(),[]);
  const [view,setView] = useState<MembershipView>(client.view);
  const [working,setWorking] = useState(false);
  const [error,setError] = useState('');
  const [inlineSwap,setInlineSwap] = useState<{searchId:string; blockerId:string} | null>(null);
  const pending = returnAction(getSession());
  // React Navigation blur covers hardware back, gestures, tab-away and unmount.
  useFocusEffect(useCallback(()=>()=>{dialog.dismiss();blurReturnAction(session,'plus');},[session,dialog.dismiss]));
  useEffect(() => { const off=client.subscribe(setView); return () => { off(); client.dispose(); }; },[client]);
  useEffect(() => { setError(''); setInlineSwap(null); void client.load(); },[client,session]);
  usePolling(useCallback(()=>{void client.load();},[client,session]),60000,!!session);
  const data = view.session===getSession() ? view.data : null;
  const v2 = isMembershipV2(data) ? data : null;
  const foundation=data && !isMembershipV2(data) ? data : null;
  const presentation = data ? membershipPresentation(data) : null;
  const back = () => { cancelReturnAction(); router.canGoBack() ? router.back() : router.replace('/settings'); };
  const run = async (fn:()=>Promise<unknown>, searchId?:string) => {
    setWorking(true); setError(''); setInlineSwap(null);
    try { await fn(); await client.load(); }
    catch (e) {
      if (session!==getSession()) return;
      const details=(e as {body?:{error?:string;blockerIds?:string[]}})?.body;
      setError(details?.error==='search_quota' ? MONETIZATION.searchQuota()
        : details?.error==='chat_quota' ? MONETIZATION.chatQuota()
        : details?.error==='organizer_search_quota' ? MONETIZATION.organizerQuota() : MONETIZATION.unknown());
      const blockerId=details?.blockerIds?.length===1 ? details.blockerIds[0] : null;
      if (searchId && details?.error==='search_quota' && blockerId && blockerId!==searchId
        && v2?.searches.some(s=>s.id===blockerId && s.state==='active')) setInlineSwap({searchId,blockerId});
    }
    finally { setWorking(false); }
  };
  const resumeSearch = (searchId:string, swapSearchId?:string) => run(() => api.post('/api/agent/search-command',{
    operation:'resume',searchId,...(swapSearchId ? {swapSearchId} : {}),
  },undefined,{quotaPresentation:'inline'}),searchId);
  const resume = (swapSearchId?:string) => run(async () => {
    // Keep failures visible here; return just before resolving the originating screen.
    await resumeReturnAction(getSession(),swapSearchId ? {swapSearchId} : undefined,
      origin => { if (origin) router.dismissTo(origin); });
  });
  return <ProfileShell title={PLUS.title()} onBack={back}>
    {dialog.view}
    <Text style={s.hero}>{PLUS.stage()}</Text>
    {presentation?.notice ? <Card><Text style={s.body}>{presentation.notice}</Text></Card> : null}
    {(view.busy || working) ? <View accessibilityLiveRegion="polite"><ActivityIndicator color={color.primary}/><Text style={s.body}>{PLUS.loading()}</Text></View> : null}
    {view.error || error ? <Text accessibilityRole="alert" style={s.error}>{error || (view.error==='sign_in' ? PLUS.login() : PLUS.error())}</Text> : null}
    {data ? <Card>
      <Text accessibilityLiveRegion="polite" style={s.title}>{presentation?.status}</Text>
      {presentation?.plusTiming ? <Text style={s.body}>{presentation.plusTiming}</Text> : null}
      {presentation?.sources.map(source => <Text key={source} style={s.body}>{source}</Text>)}
      {presentation?.timing ? <Text style={s.body}>{presentation.timing}</Text> : null}
      <Text style={s.body}>{PLUS.preserved()}</Text>
    </Card> : null}
    {v2 ? <Card><Text style={s.body}>{MONETIZATION.freeRules()}</Text><Text style={s.body}>{MONETIZATION.plusRules()}</Text></Card> : null}
    {v2?.searches.map(search => <Card key={search.id}>
      <Text style={s.title}>{search.title || search.id}</Text>
      <Text accessibilityLiveRegion="polite" style={s.body}>{searchStateLabel(search.state)}</Text>
      {search.state==='active' ? <Button disabled={working} label={MONETIZATION.pause()} onPress={() => void run(() => api.post('/api/agent/search-command',{
        operation:'pause',searchId:search.id,intent:{_searchId:search.id},commandId:`pause_${search.id}_${Date.now()}`,
      },undefined,{quotaPresentation:'inline'}))}/> : null}
      {search.state==='paused' ? <Button disabled={working} label={MONETIZATION.resumeSearch()}
        onPress={() => void resumeSearch(search.id)}/> : null}
      {search.state==='paused' && inlineSwap?.searchId===search.id ? <Button disabled={working}
        label={MONETIZATION.swap()} onPress={() => dialog.show(MONETIZATION.swap(),MONETIZATION.swapConfirm(),[
          {text:PLUS.cancel(),style:'cancel'},
          {text:MONETIZATION.continue(),onPress:() => { void resumeSearch(search.id,inlineSwap.blockerId); }},
        ])}/> : null}
      {v2.plan==='plus' && search.state==='active' ? <Button disabled={working || v2.keepSearchId===search.id} label={MONETIZATION.keep()} onPress={() => void run(() => api.post('/api/onboarding/monetization/v2/keep-search',{
        searchId:search.id,commandId:`keep_${search.id}_${Date.now()}`,
      }))}/> : null}
    </Card>)}
    {v2?.recoverableGroups?.map(group=><Card key={'legacy:'+group.gid}>
      <Text style={s.title}>{group.title}</Text>
      <Text style={s.body}>{MONETIZATION.legacyRecovery()}</Text>
      <Button disabled={working} label={MONETIZATION.recoverGroup()}
        onPress={()=>void run(()=>api.post('/api/agent/group-recover',{gid:group.gid},undefined,{quotaPresentation:'inline'}))}/>
    </Card>)}
    {pending ? <Card>
      <Text style={s.body}>{pending.reason==='chat_quota' ? MONETIZATION.chatQuota() : pending.reason==='organizer_search_quota' ? MONETIZATION.organizerQuota() : MONETIZATION.searchQuota()}</Text>
      {pending.reason==='search_quota' && pending.blockerIds?.length===1 ? <Button disabled={working} label={MONETIZATION.swap()} onPress={() => dialog.show(MONETIZATION.swap(),MONETIZATION.swapConfirm(),[
        {text:PLUS.cancel(),style:'cancel'},{text:MONETIZATION.continue(),onPress:() => { void resume(pending.blockerIds![0]); }},
      ])}/> : null}
      {pending.reason==='chat_quota' ? v2?.chatBlockers?.map(blocker=><Button key={blocker.sessionId}
        label={MONETIZATION.freeSlot()+' · '+blocker.peerName} onPress={() => {
          const route=returnActionRoute(getSession(),'conversation');
          if (route && navigateReturnAction(getSession(),'plus','conversation')) router.navigate({...route,
            params:{...route.params,who:blocker.peerName,who_id:blocker.peerId}});
        }}/>) : null}
      <Button disabled={working} label={MONETIZATION.resume()} onPress={() => { void resume(); }}/>
      <Button label={MONETIZATION.cancelAction()} onPress={back}/>
    </Card> : null}
    {foundation ? <Text style={s.body}>{foundation.previewEnabled ? PLUS.stageNote() : PLUS.unavailable()}</Text> : null}
    {foundation?.previewEnabled && foundation.canStartPreview && foundation.state==='free' ?
      <Button disabled={working || view.busy} label={PLUS.start()} onPress={()=>dialog.show(PLUS.consent(),PLUS.consentNote(),[
        {text:PLUS.cancel(),style:'cancel'},
        {text:PLUS.confirm(),onPress:()=>{void run(async()=>{if (!await client.start()) throw new Error('preview_failed');});}},
      ])}/> : null}
    <Button disabled={working} label={PLUS.retry()} onPress={() => { void client.load(); }}/>
  </ProfileShell>;
}
function Button({label,onPress,disabled=false}:{label:string;onPress:()=>void;disabled?:boolean}) {
  return <Pressable accessibilityRole="button" accessibilityState={{disabled}} disabled={disabled} onPress={onPress}
    style={[s.button,disabled && s.disabled]}><Text style={s.buttonText}>{label}</Text></Pressable>;
}
// ===== вид
const s=StyleSheet.create({
  hero:{...type.h2,color:color.fg,marginBottom:space.lg},title:{...type.title,color:color.fg,marginBottom:space.sm},
  body:{...type.body,color:color.muted,marginBottom:space.sm},error:{...type.body,color:color.danger},
  button:{minHeight:48,borderRadius:radius.full,backgroundColor:color.primary,padding:space.md,marginTop:space.sm,justifyContent:'center',alignItems:'center'},
  buttonText:{...type.button,color:color.onPrimary,textAlign:'center'},disabled:{opacity:0.5},
});
