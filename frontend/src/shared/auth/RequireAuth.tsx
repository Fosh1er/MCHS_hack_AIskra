/** Защита маршрута: без входа — на экран входа, без права — сообщение. Сервер проверяет права сам
 *  (ADR-0010), здесь — только навигация, чтобы не показывать пользователю недоступные экраны. */
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useMe } from '../api/auth';
import { isTransient } from '../api/resilience';

/** `permission` — нужное право; `anyOf` — достаточно любого из списка. */
export function RequireAuth({ permission, anyOf, children }: { permission?: string; anyOf?: string[]; children: ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return null;
  if (me.isError) {
    return (
      <p className="arm-empty" style={{ padding: 24 }}>
        {isTransient(me.error) ? 'Ждём связи с сервером — страница откроется сама.' : `Сервер недоступен: ${me.error.message}`}
      </p>
    );
  }
  if (!me.data) return <Navigate to="/" replace state={{ from: location.pathname }} />;
  const denied = (permission && !me.data.permissions.includes(permission)) || (anyOf && !anyOf.some((p) => me.data!.permissions.includes(p)));
  if (denied) {
    return (
      <div style={{ padding: 24 }}>
        <h1 className="cab-title">Нет доступа</h1>
        <p>Роль «{me.data.role_title}» не может открыть этот раздел.</p>
      </div>
    );
  }
  return <>{children}</>;
}
