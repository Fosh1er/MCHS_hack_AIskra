/** Экран входа как в АРМ-112 (image1.png): логин, пароль, номер АРМ, «ВОЙТИ».
 *  На демо-стенде (режимы demo и dev, F2) — лента «синтетические данные» и вход в роль одной кнопкой. */
import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Icon, type IconName } from '@smena112/ui-kit';
import { homeFor, useDemoAccounts, useDemoLogin, useLogin, useMe, type DemoAccount, type DemoAccounts, type Me } from '../shared/api/auth';

/** Возврат после входа — только на свой путь: «/…», без «//» и «/\» (открытый редирект, п. 6.2). */
export function safeInternalPath(p: string | undefined): string | undefined {
  return p && p.startsWith('/') && !p.startsWith('//') && !p.includes('\\') && !/[\u0000-\u001f]/.test(p) ? p : undefined;
}

export function LoginPage() {
  const me = useMe();
  const login = useLogin();
  const demo = useDemoAccounts();
  const navigate = useNavigate();
  const from = safeInternalPath((useLocation().state as { from?: string } | null)?.from);
  const [form, setForm] = useState({ login: '', password: '', arm: '' });

  if (me.data) return <Navigate to={from ?? homeFor(me.data)} replace />;

  const enter = (user: Me) => navigate(from ?? homeFor(user), { replace: true });
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate({ login: form.login, password: form.password, arm_number: form.arm || undefined }, { onSuccess: enter });
  };
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  return (
    <div className="arm-login">
      <div />
      <div className="arm-login__side">
        {demo.data && <div className="arm-login__ribbon" role="note">Демонстрационный стенд · данные синтетические</div>}
        <form className="arm-login__form" onSubmit={onSubmit} noValidate>
          <div className="arm-login__brand">
            <span className="arm-login__num">112</span>
            <span className="arm-login__caption">ВХОД В СИСТЕМУ</span>
          </div>
          <label className="arm-login__field">логин:
            <input name="login" autoComplete="username" autoFocus={!demo.data} required value={form.login} onChange={set('login')} />
          </label>
          <label className="arm-login__field">пароль:
            <input name="password" type="password" autoComplete="current-password" required value={form.password} onChange={set('password')} />
          </label>
          <label className="arm-login__field">номер АРМ:
            <input name="arm" inputMode="numeric" maxLength={6} pattern="\d*" value={form.arm} onChange={set('arm')} />
          </label>
          <button className="arm-login__btn" type="submit" disabled={login.isPending || !form.login || !form.password}>
            {login.isPending ? 'ВХОД…' : 'ВОЙТИ'}
          </button>
          {login.isError && <div className="arm-login__error" role="alert">{login.error.message}</div>}
          <p className="arm-login__hint">Учебный тренажёр. Учётную запись выдаёт администратор учебного центра.</p>
        </form>
        {demo.data && <DemoPanel data={demo.data} onEnter={enter} />}
      </div>
    </div>
  );
}

function iconFor(a: DemoAccount): IconName {
  if (a.role === 'teacher') return 'school';
  return a.title.includes('ДДС') ? 'phone' : 'headset';
}

/** Демо-учётки (F2): карточка роли и кнопка «Войти» — вход без пароля, сессия как после обычного входа. */
function DemoPanel({ data, onEnter }: { data: DemoAccounts; onEnter: (user: Me) => void }) {
  const demoLogin = useDemoLogin();
  const [pending, setPending] = useState<string | null>(null);
  const enter = (login: string) => {
    setPending(login);
    demoLogin.mutate(login, { onSuccess: onEnter, onSettled: () => setPending(null) });
  };

  return (
    <section className="arm-demo" aria-labelledby="arm-demo-title">
      <h2 className="arm-demo__title" id="arm-demo-title">Временные учётки по ролям</h2>
      <p className="arm-demo__note">
        Вход в роль — кнопкой «Войти» или вручную логином и паролем в форме слева. Номер АРМ — любой, например 123.
      </p>
      <ul className="arm-demo__list">
        {data.accounts.map((a) => (
          <li className="arm-demo__card" key={a.login}>
            <Icon name={iconFor(a)} size="lg" />
            <div>
              <div className="arm-demo__role">{a.title}</div>
              <div className="arm-demo__name">{a.full_name}{a.arm_number ? ` · АРМ ${a.arm_number}` : ''}</div>
              <div className="arm-demo__name">логин: <code>{a.login}</code>{data.password && <> · пароль: <code>{data.password}</code></>}</div>
              {a.hint.length > 0 && (
                <ul className="arm-demo__hint">{a.hint.map((h) => <li key={h}>{h}</li>)}</ul>
              )}
            </div>
            <button
              className="arm-demo__btn"
              type="button"
              disabled={demoLogin.isPending}
              onClick={() => enter(a.login)}
              aria-label={`Войти: ${a.title}, ${a.full_name}`}
            >
              {pending === a.login ? 'ВХОД…' : 'ВОЙТИ'}
            </button>
          </li>
        ))}
      </ul>
      {demoLogin.isError && <div className="arm-login__error" role="alert">{demoLogin.error.message}</div>}
    </section>
  );
}
