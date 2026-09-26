import type { SVGProps } from 'react';
import paths from '../icons/icons.json';
import { cx } from './util';

export type IconName = keyof typeof paths;
export type IconSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

export interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'ref'> {
  name: IconName;
  size?: IconSize;
  /** Если задан — иконка озвучивается скринридером; иначе декоративная (aria-hidden). */
  title?: string;
}

/** Material Icons (Apache 2.0). Пути — из icons/icons.json (единый источник со спрайтом для HTML). */
export function Icon({ name, size = 'md', title, className, ...rest }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={cx('i', size !== 'md' && `i--${size}`, className)}
      aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
      {...rest}
    >
      {title && <title>{title}</title>}
      <path d={paths[name]} />
    </svg>
  );
}
