import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Modal, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { color, radius, space, type } from '../theme';

type Choice = {text:string;style?:'cancel'|'default'|'destructive';onPress?:()=>void};
type Dialog = {id:number;title:string;message:string;buttons:Choice[];session:string};

/** RN Web's Alert is empty. Keep the same explicit choices on both platforms. */
export function useMonetizationDialog(session:string,readSession:()=>string) {
  const [queue,setQueue]=useState<Dialog[]>([]);
  const current=useRef({session,active:true,sequence:0,epoch:0});
  current.current.session=session;
  useEffect(()=>{current.current.active=true;setQueue([]);return ()=>{current.current.active=false;current.current.epoch++;};},[session]);
  const dismiss=useCallback(()=>{current.current.epoch++;setQueue([]);},[]);
  const show=useCallback((title:string,message:string,buttons:Choice[],_options?:unknown)=>{
    const owner=session,id=++current.current.sequence,epoch=current.current.epoch;
    let selected=false;
    const guarded=buttons.map(button=>({...button,onPress:()=>{
      if(selected || !current.current.active || current.current.session!==owner || readSession()!==owner || current.current.epoch!==epoch) return;
      selected=true;setQueue(items=>items.filter(item=>item.id!==id));button.onPress?.();
    }}));
    if(Platform?.OS!=='web') Alert.alert(title,message,guarded,{cancelable:false});
    else setQueue(items=>[...items,{id,title,message,buttons:guarded,session:owner}]);
  },[session,readSession]);
  const dialog=queue.find(item=>item.session===session);
  const view=dialog ? <Modal transparent visible accessibilityViewIsModal
    onRequestClose={()=>dialog.buttons.find(button=>button.style==='cancel')?.onPress?.()}>
    <View style={s.backdrop}><View style={s.dialog} accessibilityRole="alert">
      <Text style={s.title}>{dialog.title}</Text><Text style={s.body}>{dialog.message}</Text>
      {dialog.buttons.map((button,index)=><Pressable key={index} accessibilityRole="button"
        onPress={button.onPress} style={s.button}><Text style={s.buttonText}>{button.text}</Text></Pressable>)}
    </View></View>
  </Modal> : null;
  return {show,view,dismiss};
}

// ===== вид
const s=StyleSheet.create({
  backdrop:{flex:1,backgroundColor:color.bg,alignItems:'center',justifyContent:'center',padding:space.lg},
  dialog:{width:'100%',maxWidth:440,padding:space.lg,borderRadius:radius.lg,backgroundColor:color.bg},
  title:{...type.title,color:color.fg,marginBottom:space.sm},body:{...type.body,color:color.fg,marginBottom:space.md},
  button:{minHeight:48,padding:space.md,marginTop:space.sm,borderRadius:radius.full,backgroundColor:color.primary},
  buttonText:{...type.button,color:color.onPrimary,textAlign:'center'},
});
