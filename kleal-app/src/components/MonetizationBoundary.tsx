import { useEffect } from 'react';
import { AppState } from 'react-native';
import { useMonetizationDialog } from './MonetizationDialog';
import { router, useNavigationContainerRef } from 'expo-router';
import { api, getSession } from '../api';
import { useOnb } from '../state';
import { isMembership, isMembershipV2, previewNoticePresentation, MONETIZATION, PLUS } from '../monetization';
import { cancelReturnAction, captureReturnOrigin, configureMonetization, deferAction, returnAction, returnActionRoute } from '../monetization-actions';

/** One explanation, quota sheet and grant notification for every entry point. */
export function MonetizationBoundary() {
  const session = useOnb().session || '';
  const navigation = useNavigationContainerRef();
  const {show,view}=useMonetizationDialog(session,getSession);
  useEffect(() => {
    let active = true;
    let explained = false;
    let noticing = false;
    const dialogs = new Set<(e:Error)=>void>();
    const dialog = <T,>(show:(resolve:(value:T)=>void,reject:(e:Error)=>void)=>void) => new Promise<T>((resolve,reject)=>{
      const fail=(e:Error)=>{dialogs.delete(fail);reject(e);}; dialogs.add(fail);
      show(value=>{dialogs.delete(fail); if(!active || session!==getSession()) fail(new Error('account_changed'));else resolve(value);},fail);
    });
    returnAction(session);
    const load = async () => {
      if (!session) return null;
      const result = await api.get('/api/onboarding/monetization/v2/status');
      if (!active || session !== getSession()) return null;
      if (!isMembership(result)) throw new Error('membership_unknown');
      return result;
    };
    const refresh = async () => {
      try {
        const data = await load();
        if (isMembershipV2(data) && data.previewNotice && !noticing) {
          const notice = previewNoticePresentation(data);
          if (!notice) return;
          noticing = true;
          show(notice.title,notice.message,[
            { text:MONETIZATION.continue(),onPress:() => {
              if (!active || session !== getSession()) return;
              void api.post('/api/onboarding/monetization/v2/notice',{commandId:`notice_${data.previewStartedAt}`})
                .catch(() => { noticing=false; });
            } },
          ]);
        }
      } catch { /* unknown is rendered on Plus; never guess a tier */ }
    };
    configureMonetization({
      before:async () => {
        const data = await load();
        if (isMembershipV2(data) && data.previewEligible && !explained) {
          await dialog<void>((resolve,reject) => show(PLUS.title(),MONETIZATION.previewInfo(),[
            {text:PLUS.cancel(),style:'cancel',onPress:() => reject(new Error('action_cancelled'))},
            {text:MONETIZATION.continue(),onPress:() => { explained=true; resolve(); }},
          ],{cancelable:false}));
        }
      },
      changed:() => { void refresh(); },
      blocked:async (action,retry) => {
        const message = action.reason==='organizer_search_quota' ? MONETIZATION.organizerQuota()
          : action.reason==='chat_quota' ? MONETIZATION.chatQuota() : MONETIZATION.searchQuota();
        return dialog((resolve,reject) => {
          const open = () => {
            if (action.session !== getSession()) { reject(new Error('account_changed')); return; }
            const origin=captureReturnOrigin(navigation);
            if (!origin) { reject(new Error('action_cancelled')); return; }
            deferAction(action,retry,origin).then(resolve,reject);
            router.navigate(returnActionRoute(getSession(),'plus')!);
          };
          show(PLUS.title(),message,[
            // Role screens provide their permission-aware recovery via api options.
            // A generic cancellation must not promise to choose another owner.
            {text:PLUS.cancel(),style:'cancel',onPress:() => reject(new Error('action_cancelled'))},
            {text:action.reason==='organizer_search_quota' ? MONETIZATION.freeSlot() : PLUS.title(),onPress:open},
          ],{cancelable:false});
        });
      },
    });
    void refresh();
    const listener = AppState.addEventListener('change',state => { if (state==='active') void refresh(); });
    return () => { active=false; listener.remove(); configureMonetization({}); cancelReturnAction();
      for(const reject of dialogs) reject(new Error('account_changed')); dialogs.clear(); };
  },[session,navigation,show]);
  return view;
}
