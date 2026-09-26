/** Экран входа как в АРМ-112 (image1.png): логин, пароль, номер АРМ, «ВОЙТИ». */
import { useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { homeFor, useLogin, useMe } from '../shared/api/auth';

export function LoginPage() {
  const me = useMe();
  const login = useLogin();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [form, setForm] = useState({ login: '', password: '', arm: '' });

  if (me.data) return <Navigate to={from ?? homeFor(me.data)} replace />;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate(
      { login: form.login, password: form.password, arm_number: form.arm || undefined },
      { onSuccess: (user) => navigate(from ?? homeFor(user), { replace: true }) },
    );
  };
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  return (
    <div className="arm-login">
      <div />
      <form className="arm-login__form" onSubmit={onSubmit} noValidate>
        <div className="arm-login__brand">
          <span className="arm-login__num">112</span>
          <span className="arm-login__caption">ВХОД В СИСТЕМУ</span>
        </div>
        <label className="arm-login__field">логин:
          <input name="login" autoComplete="username" autoFocus required value={form.login} onChange={set('login')} />
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
    </div>
  );
}
