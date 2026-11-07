/** Opens the incoming-call screen whenever the server says someone is calling him through his call link. */
import { router } from 'expo-router';
import { useEffect } from 'react';

import { useConnection } from '@/features/connection/ConnectionProvider';

export function IncomingCallWatcher() {
  const { socket } = useConnection();
  useEffect(
    () =>
      socket?.onMessage((message) => {
        if (message.type === 'incoming_call') router.push({ pathname: '/incoming', params: { callId: message.call_id, name: message.name ?? '' } });
      }),
    [socket],
  );
  return null;
}
