/** Подсказка горячей клавиши: видна, пока зажат Alt (как в АРМ-112). */
export function Hint({ k, style }: { k: string; style?: React.CSSProperties }) {
  return <span className="arm112-hint" style={{ top: -8, left: 0, ...style }} aria-hidden="true">{k}</span>;
}
