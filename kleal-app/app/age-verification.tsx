// A Didit return link is only a navigation hint. The root gate checks our server.
import React from 'react';
import { Redirect } from 'expo-router';
import { useOnb } from '../src/state';
export default function AgeVerificationReturn() {
  const { session, done } = useOnb();
  return <Redirect href={!session ? '/auth' : !done ? '/summary' : '/home'} />;
}
