import { createContext, useCallback, useContext, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Icon, type IconName } from "../icons";

interface ToastState {
  show: boolean;
  msg: string;
  icon: IconName;
}
type ShowToast = (msg: string, icon?: IconName) => void;

const ToastContext = createContext<ShowToast>(() => {});

export const useToast = (): ShowToast => useContext(ToastContext);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState>({ show: false, msg: "", icon: "check" });
  const timer = useRef<number | undefined>(undefined);

  const show = useCallback<ShowToast>((msg, icon = "check") => {
    window.clearTimeout(timer.current);
    setToast({ show: true, msg, icon });
    timer.current = window.setTimeout(() => setToast((t) => ({ ...t, show: false })), 2200);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      {toast.show && (
        <div
          style={{
            position: "fixed",
            bottom: 24,
            left: "50%",
            transform: "translateX(-50%)",
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "12px 18px",
            background: "var(--ink)",
            color: "var(--surface)",
            borderRadius: 11,
            boxShadow: "var(--shadow-lg)",
            fontSize: 13.5,
            fontWeight: 500,
            zIndex: 60,
            animation: "toastIn .25s ease both",
          }}
        >
          <Icon name={toast.icon} size={16} />
          {toast.msg}
        </div>
      )}
    </ToastContext.Provider>
  );
}
