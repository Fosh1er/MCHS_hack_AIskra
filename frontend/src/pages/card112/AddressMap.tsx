/** Окно карты блока «Адрес» (п. 1.2): точка с радиусом 50 м, «Указать на карте», ввод координат + «ОК»
 *  (instr/image21, image27, image28). Тайлов нет — изолированный контур: схема из границ районов
 *  и точек домов адресного справочника (OpenStreetMap), дома показываются с масштаба 16. */
import { useEffect, useRef, useState } from 'react';
import type { FeatureCollection } from 'geojson';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Icon } from '@smena112/ui-kit';
import { fetchHouses, reverseGeocode, useDistrictShapes, type GeocodeResult } from '../../shared/api/dictionaries';

const MOSCOW: L.LatLngTuple = [55.7539, 37.6208];
const RADIUS_M = 50;
const HOUSES_ZOOM = 16;

/** Цвета — из токенов ui-kit (Leaflet рисует SVG и не видит CSS-переменные напрямую). */
function tokens() {
  const css = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  return { accent: v('--c-blue-600', '#157dbd'), orange: v('--c-orange-600', '#ec653b'), line: v('--c-slate-600', '#4f5a62'), house: v('--c-graphite-700', '#3a4046') };
}

export function AddressMap({ lat, lon, district, readOnly = false, onPick, onClose }: {
  lat: number | null; lon: number | null; district: string | null; readOnly?: boolean;
  onPick?: (r: GeocodeResult) => void; onClose: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const marker = useRef<L.LayerGroup | null>(null);
  const houses = useRef<L.LayerGroup | null>(null);
  const shapes = useDistrictShapes();
  const [picking, setPicking] = useState(false);
  const [coords, setCoords] = useState({ lat: lat != null ? lat.toFixed(6) : '', lon: lon != null ? lon.toFixed(6) : '' });
  const [status, setStatus] = useState('');
  const pickingRef = useRef(picking);
  pickingRef.current = picking;

  // Esc закрывает окно карты, а не карточку (глобальные горячие клавиши карточки слушают window в фазе всплытия)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.stopPropagation();
      if (pickingRef.current) setPicking(false); else onClose();
    };
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [onClose]);

  const place = async (p: L.LatLng, center = false) => {
    const t = tokens();
    marker.current?.clearLayers();
    L.circle(p, { radius: RADIUS_M, color: t.orange, weight: 2, fillOpacity: 0.12 }).addTo(marker.current!);
    L.circleMarker(p, { radius: 6, color: t.orange, weight: 3, fillColor: '#fff', fillOpacity: 1 }).addTo(marker.current!);
    if (center) map.current?.setView(p, Math.max(map.current.getZoom(), HOUSES_ZOOM + 1));
    setCoords({ lat: p.lat.toFixed(6), lon: p.lng.toFixed(6) });
    if (readOnly || !onPick) return;
    setStatus('Определяю адрес…');
    try {
      const r = await reverseGeocode(p.lat, p.lng);
      onPick(r);
      setStatus(r.address ? `${r.address.label} — ${Math.round(r.distance_m ?? 0)} м от точки` : 'Рядом нет дома из справочника — заполнены координаты и район');
    } catch (e) {
      setStatus(`Не удалось определить адрес: ${(e as Error).message}`);
    }
  };

  // карта создаётся один раз
  useEffect(() => {
    if (!box.current || map.current) return;
    const m = L.map(box.current, { zoomControl: true, attributionControl: true, minZoom: 9, maxZoom: 19 })
      .setView(lat != null && lon != null ? [lat, lon] : MOSCOW, lat != null ? HOUSES_ZOOM + 1 : 11);
    m.attributionControl.setPrefix(false).addAttribution('© участники OpenStreetMap (ODbL)');
    marker.current = L.layerGroup().addTo(m);
    houses.current = L.layerGroup().addTo(m);
    map.current = m;
    if (lat != null && lon != null) void place(L.latLng(lat, lon));
    m.on('click', (e: L.LeafletMouseEvent) => {
      if (!pickingRef.current) return;
      setPicking(false);
      void place(e.latlng);
    });
    let seq = 0;
    const loadHouses = async () => {
      const layer = houses.current!;
      if (m.getZoom() < HOUSES_ZOOM) { layer.clearLayers(); return; }
      const b = m.getBounds();
      const my = ++seq;
      const pts = await fetchHouses({ min_lat: b.getSouth(), min_lon: b.getWest(), max_lat: b.getNorth(), max_lon: b.getEast() }).catch(() => []);
      if (my !== seq) return;
      layer.clearLayers();
      const t = tokens();
      for (const h of pts) {
        L.circleMarker([h.lat, h.lon], { radius: 3, color: t.house, weight: 1, fillOpacity: 0.7 })
          .bindTooltip(h.label, { direction: 'top' })
          .on('click', (e) => { if (pickingRef.current) { L.DomEvent.stop(e); setPicking(false); void place(L.latLng(h.lat, h.lon)); } })
          .addTo(layer);
      }
    };
    m.on('moveend', () => { void loadHouses(); });
    void loadHouses();
    return () => { m.remove(); map.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // границы районов — когда загрузятся
  useEffect(() => {
    const m = map.current;
    if (!m || !shapes.data) return;
    const t = tokens();
    const layer = L.geoJSON(shapes.data as unknown as FeatureCollection, {
      style: (f) => ({
        color: t.line, weight: 1, fillColor: t.accent,
        fillOpacity: f?.properties?.code === district ? 0.12 : 0.03,
      }),
      interactive: false,
    }).addTo(m);
    const labels = L.layerGroup(
      shapes.data.features.map((f) => L.marker([f.properties.label[1], f.properties.label[0]], {
        icon: L.divIcon({ className: 'arm112-map__label', html: f.properties.name, iconSize: undefined }), interactive: false,
      })),
    );
    const toggleLabels = () => { if (m.getZoom() >= 12 && m.getZoom() < HOUSES_ZOOM + 1) labels.addTo(m); else labels.remove(); };
    m.on('zoomend', toggleLabels);
    toggleLabels();
    layer.bringToBack();
    return () => { layer.remove(); labels.remove(); m.off('zoomend', toggleLabels); };
  }, [shapes.data, district]);

  useEffect(() => { box.current?.classList.toggle('arm112-map__canvas--pick', picking); }, [picking]);

  const applyCoords = () => {
    const la = Number(coords.lat.replace(',', '.'));
    const lo = Number(coords.lon.replace(',', '.'));
    if (!Number.isFinite(la) || !Number.isFinite(lo) || Math.abs(la) > 90 || Math.abs(lo) > 180) {
      setStatus('Введите широту и долготу числами, например 55.7652 и 37.6667');
      return;
    }
    void place(L.latLng(la, lo), true);
  };

  return (
    <div className="arm112-map" role="dialog" aria-label="Карта">
      <div className="arm112-map__head">
        <b>Карта</b>
        {!readOnly && (
          <>
            <label>широта <input className="arm112v-input" value={coords.lat} onChange={(e) => setCoords({ ...coords, lat: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && applyCoords()} /></label>
            <label>долгота <input className="arm112v-input" value={coords.lon} onChange={(e) => setCoords({ ...coords, lon: e.target.value })} onKeyDown={(e) => e.key === 'Enter' && applyCoords()} /></label>
            <button type="button" className="arm-minibtn" onClick={applyCoords}>ОК</button>
            <button type="button" className={`arm-minibtn${picking ? ' arm-minibtn--on' : ''}`} aria-pressed={picking} onClick={() => setPicking(!picking)}>Указать на карте</button>
          </>
        )}
        <span className="arm112-map__radius">радиус {RADIUS_M} м</span>
        <button type="button" className="arm-iconsq" aria-label="Закрыть карту (Esc)" onClick={onClose}><Icon name="close" size="sm" /></button>
      </div>
      <div ref={box} className="arm112-map__canvas" />
      {status && <div className="arm112-map__status" role="status">{status}</div>}
      {picking && <div className="arm112-map__hint">Щёлкните по карте или по точке дома</div>}
    </div>
  );
}
