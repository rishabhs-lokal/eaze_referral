import { useCallback, useRef, useState } from 'react';
import type { ToastTone } from '../components/Toast';

export type ToastState = { tone: ToastTone; message: string } | null;

export function useToast(autoDismissMs = 3000) {
  const [toast, setToast] = useState<ToastState>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback(
    (tone: ToastTone, message: string) => {
      if (timer.current) clearTimeout(timer.current);
      setToast({ tone, message });
      timer.current = setTimeout(() => setToast(null), autoDismissMs);
    },
    [autoDismissMs]
  );

  return { toast, showToast };
}
