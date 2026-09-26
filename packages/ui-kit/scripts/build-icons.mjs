// Генерирует icons/icons.js (спрайт для статичных HTML-страниц) из icons/icons.json —
// единого источника путей, который также импортирует React-компонент <Icon/>.
// Запуск: node scripts/build-icons.mjs  (Node >= 16)
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const paths = JSON.parse(readFileSync(join(root, 'icons/icons.json'), 'utf8'));

const symbols = Object.entries(paths)
  .map(([name, d]) => `<symbol id="i-${name}" viewBox="0 0 24 24"><path d="${d}"/></symbol>`)
  .join('');

const out = `/* СГЕНЕРИРОВАНО scripts/build-icons.mjs из icons.json — не править руками.
   Material Icons (Google), Apache License 2.0.
   Вставляет SVG-спрайт в <body>; использование: <svg class="i"><use href="#i-phone"/></svg> */
(function () {
  var sprite = '<svg xmlns="http://www.w3.org/2000/svg" style="display:none">${symbols}</svg>';
  function inject() { document.body.insertAdjacentHTML('afterbegin', sprite); }
  if (document.body) inject(); else document.addEventListener('DOMContentLoaded', inject);
})();
`;
writeFileSync(join(root, 'icons/icons.js'), out);
console.log(`icons.js: ${Object.keys(paths).length} icons`);
