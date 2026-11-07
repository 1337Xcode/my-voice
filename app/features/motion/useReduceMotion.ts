/** Whether the system asks for reduced motion; all motion in the app is off when it does. */
import { useEffect, useState } from 'react';
import type { MotiTransitionProp } from 'moti';
import { AccessibilityInfo } from 'react-native';

import { useSettings } from '@/features/settings/SettingsProvider';

/** True when the system or his own setting asks for reduced motion. */
export function useReduceMotion(): boolean {
  const { settings } = useSettings();
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    let mounted = true;
    AccessibilityInfo.isReduceMotionEnabled()
      .then((value) => mounted && setReduce(value))
      .catch(() => undefined);
    const subscription = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduce);
    return () => {
      mounted = false;
      subscription.remove();
    };
  }, []);
  return reduce || settings.reduceMotion;
}

/** A short timing transition for state changes, or none when motion is reduced. */
export function stateTransition(reduce: boolean): MotiTransitionProp {
  return { type: 'timing', duration: reduce ? 0 : 220 } as MotiTransitionProp;
}
