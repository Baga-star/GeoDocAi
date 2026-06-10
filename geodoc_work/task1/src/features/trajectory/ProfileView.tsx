import { useEffect, useMemo, useState } from 'react';
import { RefreshCw, Maximize2, Crosshair, ZoomIn } from 'lucide-react';
import { trajectoryJson } from './api';
import { Plot, PlotFrame, navigatorLayout, plotConfig } from './PlotFrame';
import type { TrajectorySeriesResponse } from './types';

export function ProfileView({ wellId, fullscreen, onFullscreen }: {
  wellId: string;
  fullscreen?: boolean;
  onFullscreen?: () => void;
}) {
  const [azimuth, setAzimuth] = useState(0);
  const [data, setData] = useState<TrajectorySeriesResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setError('');
    setLoading(true);
    try {
      setData(await trajectoryJson(`/trajectory/well/${wellId}/profile?azimuth=${azimuth}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки профиля');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [wellId, azimuth]);

  const points = data?.series || [];
  const plotHeight = fullscreen ? window.innerHeight - 180 : 520;

  const traces = useMemo(() => {
    if (!points.length) return [];
    return [{
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Рабочая скважина',
      x: points.map(p => p.vertical_section ?? 0),
      y: points.map(p => p.tvd),
      text: points.map(p => `Глуб. по стволу: ${p.md} м<br>Зенит: ${p.inc.toFixed(2)}°<br>Азимут: ${p.azi.toFixed(2)}°<br>ВГ: ${p.tvd.toFixed(1)} м<br>Отход: ${(p.vertical_section ?? 0).toFixed(1)} м`),
      hovertemplate: '%{text}<extra></extra>',
      line: { color: '#20b2aa', width: 2.5 },
      marker: { color: '#20b2aa', size: 5 },
    }];
  }, [points]);

  return (
    <PlotFrame
      title="Профиль скважины — вертикальная проекция"
      subtitle={`Направление плоскости проекции: ${azimuth}°`}
      tools={
        <div className="nav-plot-controls">
          <div className="nav-control-group">
            <label className="nav-control-label">
              <Crosshair size={12} />
              Азимут плоскости
            </label>
            <input
              type="number" min={0} max={360} value={azimuth}
              className="nav-control-input"
              onChange={e => setAzimuth(Number(e.target.value))}
            />
            <span className="nav-control-unit">°</span>
            <button type="button" className="nav-plot-btn-sm" onClick={load} disabled={loading}>
              Применить
            </button>
          </div>
          <button type="button" className="nav-plot-btn" onClick={load} disabled={loading}>
            <RefreshCw size={13} className={loading ? 'nav-spin' : ''} />
            Обновить
          </button>
          {onFullscreen && (
            <button type="button" className="nav-plot-btn" onClick={onFullscreen}>
              <Maximize2 size={13} />
              Во весь экран
            </button>
          )}
        </div>
      }
    >
      {error ? <div className="nav-plot-error">{error}</div> : null}
      {loading && !data ? (
        <div className="nav-plot-loading">
          <RefreshCw size={24} className="nav-spin" />
          <span>Загрузка профиля...</span>
        </div>
      ) : traces.length === 0 ? (
        <div className="nav-plot-nodata">
          <ZoomIn size={32} />
          <div>Нет данных для отображения профиля</div>
        </div>
      ) : (
        <Plot
          data={traces as never}
          layout={{
            ...navigatorLayout,
            height: plotHeight,
            xaxis: {
              ...navigatorLayout.xaxis,
              title: { text: `Азимут оси → ${azimuth}° (направление плоскости верт. проекции) (м)`, font: { color: '#8aacb8', size: 11 } },
            },
            yaxis: {
              ...navigatorLayout.yaxis,
              title: { text: 'Вертикальная глубина (м)', font: { color: '#8aacb8', size: 11 } },
              autorange: 'reversed',
            },
            showlegend: true,
            legend: { ...navigatorLayout.legend, x: 0.99, y: 0.01, xanchor: 'right', yanchor: 'bottom' },
          }}
          config={plotConfig}
          style={{ width: '100%', height: plotHeight }}
        />
      )}
      {data?.warnings?.length ? <div className="nav-plot-warn">{data.warnings.join(' · ')}</div> : null}
    </PlotFrame>
  );
}
