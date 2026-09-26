/** Пользователи и роли (п. 5.2, P0): поиск, фильтры, создание, правка, блокировка, смена пароля. */
import { Fragment, useState } from 'react';
import { Banner, Button, Card, Segmented, StatusPill } from '@smena112/ui-kit';
import { useMe, type Role } from '../../shared/api/auth';
import { ROLE_TITLE, useCreateUser, useResetPassword, useSetBlocked, useUpdateUser, useUsers, type UserRow } from '../../shared/api/admin';
import { CabinetShell } from '../../shared/ui/CabinetShell';

const ROLES: Role[] = ['student', 'teacher', 'admin'];

function CreateForm({ onDone }: { onDone: () => void }) {
  const create = useCreateUser();
  const [f, setF] = useState({ login: '', full_name: '', role: 'student' as Role, password: '', operator_number: '' });
  return (
    <Card title="Новый пользователь">
      <div className="tch-form tch-form--grid">
        <label>Логин<input value={f.login} autoComplete="off" onChange={(e) => setF({ ...f, login: e.target.value })} /></label>
        <label>ФИО<input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></label>
        <label>Роль
          <select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>{ROLES.map((r) => <option key={r} value={r}>{ROLE_TITLE[r]}</option>)}</select>
        </label>
        <label>Номер оператора<input value={f.operator_number} onChange={(e) => setF({ ...f, operator_number: e.target.value })} /></label>
        <label>Пароль (от 8 символов)<input type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></label>
      </div>
      <div className="cab-filters" style={{ marginTop: 10 }}>
        <Button variant="primary" icon="plus" disabled={create.isPending || !f.login || !f.full_name || f.password.length < 8}
          onClick={() => create.mutate({ ...f, operator_number: f.operator_number || null }, { onSuccess: onDone })}>создать</Button>
        <Button variant="ghost" onClick={onDone}>отмена</Button>
      </div>
      {create.isError && <Banner status="critical">{create.error.message}</Banner>}
    </Card>
  );
}

function UserEditor({ u, onClose }: { u: UserRow; onClose: () => void }) {
  const me = useMe().data!;
  const update = useUpdateUser();
  const block = useSetBlocked();
  const reset = useResetPassword();
  const [f, setF] = useState({ full_name: u.full_name, role: u.role, operator_number: u.operator_number ?? '' });
  const [password, setPassword] = useState('');
  const [reason, setReason] = useState('');
  const err = update.error ?? block.error ?? reset.error;
  const self = u.id === me.user_id;
  return (
    <div className="tch-override adm-editor">
      <div className="tch-form tch-form--grid">
        <label>ФИО<input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></label>
        <label>Роль
          <select value={f.role} disabled={self} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>{ROLES.map((r) => <option key={r} value={r}>{ROLE_TITLE[r]}</option>)}</select>
        </label>
        <label>Номер оператора<input value={f.operator_number} onChange={(e) => setF({ ...f, operator_number: e.target.value })} /></label>
      </div>
      <div className="cab-filters" style={{ marginTop: 8 }}>
        <Button size="sm" variant="primary" icon="save" disabled={update.isPending} onClick={() => update.mutate({ id: u.id, ...f }, { onSuccess: onClose })}>сохранить</Button>
        <Button size="sm" variant="ghost" onClick={onClose}>закрыть</Button>
      </div>
      <div className="tch-form tch-form--grid" style={{ marginTop: 10 }}>
        <label>Новый пароль<input type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {u.status === 'active' && !self && <label>Причина блокировки<input value={reason} onChange={(e) => setReason(e.target.value)} /></label>}
      </div>
      <div className="cab-filters" style={{ marginTop: 8 }}>
        <Button size="sm" icon="shield" disabled={reset.isPending || password.length < 8}
          onClick={() => reset.mutate({ id: u.id, password }, { onSuccess: () => setPassword('') })}>задать пароль</Button>
        {!self && (u.status === 'active'
          ? <Button size="sm" variant="danger" icon="close" disabled={block.isPending} onClick={() => block.mutate({ id: u.id, blocked: true, reason })}>заблокировать</Button>
          : <Button size="sm" icon="check" disabled={block.isPending} onClick={() => block.mutate({ id: u.id, blocked: false })}>разблокировать</Button>)}
        {reset.isSuccess && <span className="cab-filters__label">пароль задан, сессии пользователя завершены</span>}
      </div>
      {err && <Banner status="critical">{err.message}</Banner>}
    </div>
  );
}

export function UsersPage() {
  const [f, setF] = useState({ q: '', role: '', status: '', page: 1 });
  const [creating, setCreating] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const q = useUsers(f);
  const total = q.data?.total ?? 0;
  return (
    <CabinetShell kind="admin" active="users" title="Пользователи" subtitle={`${total} в выборке`}
      actions={!creating && <Button variant="primary" icon="plus" onClick={() => setCreating(true)}>пользователь</Button>}>
      {creating && <CreateForm onDone={() => setCreating(false)} />}
      <div className="cab-filters">
        <input className="cab-select" style={{ width: 240 }} placeholder="логин или ФИО" aria-label="Поиск" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} />
        <Segmented ariaLabel="Роль" value={f.role} onChange={(v) => setF({ ...f, role: v, page: 1 })}
          options={[{ value: '', label: 'все' }, ...ROLES.map((r) => ({ value: r, label: ROLE_TITLE[r] }))]} />
        <Segmented ariaLabel="Статус" value={f.status} onChange={(v) => setF({ ...f, status: v, page: 1 })}
          options={[{ value: '', label: 'любой' }, { value: 'active', label: 'активные' }, { value: 'blocked', label: 'заблокированные' }]} />
      </div>
      <Card flush>
        <table className="cab-table">
          <thead><tr><th>ФИО</th><th>Логин</th><th>Роль</th><th>Опер.</th><th>Последний вход</th><th>Статус</th></tr></thead>
          <tbody>
            {q.data?.items.map((u) => (
              <Fragment key={u.id}>
                <tr style={{ cursor: 'pointer' }} onClick={() => setOpen(open === u.id ? null : u.id)} className={open === u.id ? 'is-picked' : ''}>
                  <td><b>{u.full_name}</b></td><td className="c-slate">{u.login}</td><td>{ROLE_TITLE[u.role]}</td>
                  <td>{u.operator_number ?? ''}</td>
                  <td>{u.last_login_at ? new Date(u.last_login_at).toLocaleString('ru-RU') : '—'}</td>
                  <td><StatusPill status={u.status === 'active' ? (u.locked_until && new Date(u.locked_until) > new Date() ? 'warn' : 'ok') : 'critical'}>
                    {u.status === 'active' ? (u.locked_until && new Date(u.locked_until) > new Date() ? 'вход заблокирован' : 'активен') : 'заблокирован'}
                  </StatusPill></td>
                </tr>
                {open === u.id && <tr className="tch-subrow"><td colSpan={6}><UserEditor u={u} onClose={() => setOpen(null)} /></td></tr>}
              </Fragment>
            ))}
          </tbody>
        </table>
        {total > 50 && (
          <div className="cab-filters" style={{ padding: 10 }}>
            <Button size="sm" disabled={f.page <= 1} onClick={() => setF({ ...f, page: f.page - 1 })}>назад</Button>
            <span className="cab-filters__label">стр. {f.page} из {Math.ceil(total / 50)}</span>
            <Button size="sm" disabled={f.page * 50 >= total} onClick={() => setF({ ...f, page: f.page + 1 })}>вперёд</Button>
          </div>
        )}
      </Card>
    </CabinetShell>
  );
}
