import { useEffect, useMemo, useState } from 'react';
import { Maximize2, RefreshCw, Navigation } from 'lucide-react';
import { trajectoryJson } from './api';
import { Plot, PlotFrame, navigatorLayout, plotConfig } from './PlotFrame';
import type { TrajectorySeriesResponse } from './types';

export function ProfileView({
  wellId, fullscreen, onFullscreen,
}: {
  wellId: string; fullscreen?: boolean; onFullscreen?: () => void;
}) {
  const [azimuth, setAzimuth] = useState(0);
  const [azInput, setAzInput] = useState('0');
  const [actual, setActual] = useState<TrajectorySeriesResponse | null>(null);
  const [design, setDesign] = useState<TrajectorySeriesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async (az: number) => {
    setLoading(true); setError('');
    try {
      const [a, d] = await Promise.all([
        trajectoryJson<TrajectorySeriesResponse>(`/trajectory/well/${wellId}/profile?azimuth=${az}`),
        trajectoryJson<TrajectorySeriesResponse>(`/trajectory/well/${wellId}/design?azimuth=${az}`).catch(() => null),
      ]);
      setActual(a); setDesign(d);
    } catch (err) { setError(err instanceof Error ? err.message : 'Ошибка профиля'); }
    finally { setLoading(false); }
  };

  useEffect(() => { void load(0); }, [wellId]);

  const applyAzimuth = () => {
    const val = Number(azInput);
    if (!isNaN(val)) { setAzimuth(val); void load(val); }
  };

  const traces = useMemo(() => {
    const out: unknown[] = [];
    const apts = actual?.series || [];
    const dpts = design?.series || [];

    if (apts.length) {
      out.push({
        type: 'scatter', mode: 'lines+markers', name: 'Рабочая скважина',
        x: apts.map(p => p.vertical_section ?? 0),
        y: apts.map(p => -p.tvd),
        text: apts.map(p =>
          `ГПИ: ${p.md} м<br>Верт. глубина: ${p.tvd.toFixed(1)} м<br>Зенит: ${p.inc?.toFixed(1) ?? '—'}°<br>Азимут: ${p.azi?.toFixed(1) ?? '—'}°<br>Отход: ${(p.vertical_section ?? 0).toFixed(1)} м`
        ),
        hovertemplate: '%{text}<extra></extra>',
        line: { color: '#ef4444', width: 2.5 }, marker: { size: 3 },
      });
    }

    if (dpts.length) {
      out.push({
        type: 'scatter', mode: 'lines', name: 'Проект',
        x: dpts.map(p => p.vertical_section ?? 0),
        y: dpts.map(p => -p.tvd),
        text: dpts.map(p => `Проект ГПИ: ${p.md} м`),
        hovertemplate: '%{text}<extra></extra>',
        line: { color: '#22d3ee', width: 2, dash: 'dash' },
      });
      const TOL = 10;
      out.push({
        type: 'scatter', mode: 'lines', name: 'Коридор допуска',
        x: [
          ...dpts.map(p => (p.vertical_section ?? 0) - TOL),
          ...dpts.map(p => (p.vertical_section ?? 0) + TOL).reverse(),
        ],
        y: [
          ...dpts.map(p => -p.tvd - TOL),
          ...dpts.map(p => -p.tvd + TOL).reverse(),
        ],
        fill: 'toself', fillcolor: 'rgba(34,211,238,0.07)',
        line: { color: 'rgba(34,211,238,0.25)', width: 1, dash: 'dot' }, hoverinfo: 'skip',
      });
    }
    return out;
  }, [actual, design]);

  const h = fullscreen ? 680 : 480;

  return (
    <PlotFrame
      title="Профиль скважины"
      subtitle="Вертикальная проекция"
      tools={
        <>
          <div className="nav-control-group">
            <Navigation size={13} />
            <span className="nav-control-label">Азимут:</span>
            <input
              className="nav-control-input" type="number" min={0} max={360}
              value={azInput} onChange={e => setAzInput(e.target.value)}
            />
            <span className="nav-control-unit">°</span>
            <button type="button" className="nav-plot-btn-sm" onClick={applyAzimuth} disabled={loading}>
              {loading ? '…' : 'Применить'}
            </button>
          </div>
          <button type="button" className="nav-plot-btn-sm" onClick={() => void load(azimuth)} disabled={loading}>
            <RefreshCw size={13} /> Обновить
          </button>
          {onFullscreen && (
            <button type="button" className="nav-plot-btn-sm" onClick={onFullscreen}>
              <Maximize2 size={13} /> Полный экран
            </button>
          )}
        </>
      }
    >
      {error ? <div className="nav-plot-error">{error}</div> : null}
      {!actual || loading ? (
        <div className="nav-plot-nodata">
          {loading
            ? <strong>Пересчёт для азимута {azimuth}°…</strong>
            : <><strong>Нет данных профиля</strong><p>Необходимы рассчитанные точки траектории.</p></>
          }
        </div>
      ) : (
        <Plot
          data={traces as never}
          layout={{
            ...navigatorLayout,
            height: h,
            xaxis: {
              ...navigatorLayout.xaxis,
              title: `Отход (верт. секция, азимут ${azimuth}°) → (м)`,
              autorange: true,
            },
            yaxis: {
              ...navigatorLayout.yaxis,
              title: '↓ Вертикальная глубина (м)',
              autorange: true,
            },
            legend: { ...navigatorLayout.legend, x: 1.01, y: 1, orientation: 'v' as const },
          }}
          config={plotConfig}
          style={{ width: '100%', height: h }}
        />
      )}
      {actual?.warnings?.length ? <div className="nav-plot-warn">{actual.warnings.join(' · ')}</div> : null}
    </PlotFrame>
  );
}
