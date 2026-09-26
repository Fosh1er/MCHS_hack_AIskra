/** Эмулятор АРМ повторяет рабочее место оператора 112 (п. 9.1) и рассчитан на экран от 1024 px (п. 6.3).
 *  На телефоне и планшете вертикально — объяснение и переходы вместо сломанной вёрстки; поворот планшета
 *  снимает объяснение сам. «Открыть всё равно» запоминается до закрытия вкладки. */
import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '@smena112/ui-kit';
import { useMe } from '../api/auth';

const MIN_WIDTH = 1000;
const KEY = 'aiskra:arm-narrow-ok';

function useWidth(): number {
  const [w, setW] = useState(() => window.innerWidth);
  useEffect(() => {
    const on = () => setW(window.innerWidth);
    window.addEventListener('resize', on);
    window.addEventListener('orientationchange', on);
    return () => { window.removeEventListener('resize', on); window.removeEventListener('orientationchange', on); };
  }, []);
  return w;
}

const readOk = () => { try { return sessionStorage.getItem(KEY) === '1'; } catch { return false; } };

export function ArmScreenGuard({ children }: { children: ReactNode }) {
  const width = useWidth();
  const navigate = useNavigate();
  const me = useMe().data;
  const [ok, setOk] = useState(readOk);
  if (width >= MIN_WIDTH || ok) return <>{children}</>;
  const portraitTablet = width >= 700 && window.innerHeight > window.innerWidth;
  const cabinet = me?.role === 'teacher' ? '/teacher' : me?.role === 'admin' ? '/admin' : '/student';
  const proceed = () => { try { sessionStorage.setItem(KEY, '1'); } catch { /* нет хранилища */ } setOk(true); };
  return (
    <div className="arm-guard" role="dialog" aria-labelledby="arm-guard-title">
      <div className="arm-guard__box">
        <Icon name={portraitTablet ? 'refresh' : 'dashboard'} size="lg" />
        <h1 id="arm-guard-title">{portraitTablet ? 'Поверните планшет горизонтально' : 'Эмулятор АРМ — для большого экрана'}</h1>
        <p>
          Карточка и журналы повторяют рабочее место оператора 112 и диспетчера ДДС и рассчитаны на экран от 1024 точек
          по ширине — компьютер или планшет в горизонтальном положении.
        </p>
        <p>На телефоне удобно смотреть занятия, результаты и справочную базу в кабинете.</p>
        <div className="arm-guard__actions">
          <button type="button" className="arm-guard__primary" onClick={() => navigate(cabinet)}>перейти в кабинет</button>
          <button type="button" className="arm-guard__secondary" onClick={proceed}>открыть всё равно</button>
        </div>
      </div>
    </div>
  );
}
