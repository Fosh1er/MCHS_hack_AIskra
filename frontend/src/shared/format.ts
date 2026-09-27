/** Русские форматы (п. 6.3): «81,7», «1 024», даты и время — ru-RU. Пустое значение — «—». */
const nf = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });

export const num = (n: number | null | undefined): string => (n === null || n === undefined || Number.isNaN(n) ? '—' : nf.format(n));

export const bytes = (b: number): string => (b > 2 ** 20 ? `${num(Math.round((b / 2 ** 20) * 10) / 10)} МБ` : `${num(Math.max(1, Math.round(b / 1024)))} КБ`);
/** «1 раз», «3 раза», «5 раз»: форма слова по числу. */
export const plural = (n: number, one: string, few: string, many: string): string => {
  const m10 = n % 10, m100 = n % 100;
  return m10 === 1 && m100 !== 11 ? one : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? few : many;
};
