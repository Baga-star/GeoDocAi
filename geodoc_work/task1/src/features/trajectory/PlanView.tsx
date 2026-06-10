import { useEffect, useMemo, useState } from 'react';
import { RefreshCw, ZoomIn, Maximize2, Crosshair } from 'lucide-react';
import { trajectoryJson } from './api';
import { Plot, PlotFrame, navigatorLayout, plotConfig } from './PlotFrame';
import type { ProjectTrajectoryResponse, TrajectorySeriesResponse } from './types';

const WELL_COLORS = ['#20b2aa', '#f97316', '#a78bfa', '#34d399', '#fb923c', '#60a5fa', '#f472b6', '#facc15'];

export function PlanView({ projectId, wellId, fullscreen, onFullscreen }: {
  projectId?: string;
  wellId?: string;
  fullscreen?: boolean;
  onFullscreen?: () => void;
}) {
  const [data, setData] = useState<ProjectTrajectoryResponse | TrajectorySeriesResponse | null>(null);
  const [error, setError] = useState('');
  const [azimuth, setAzimuth] = useState(0);
  const [loading, setLoading] = useState(false);

  const path = wellId
    ? `/trajectory/well/${wellId}/plan`
    : `/trajectory/project/${projectId}/plan`;

  const load = async () => {
    setError('');
    setLoading(true);
    try {
      setData(await trajectoryJson(path));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки плана');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (projectId || wellId) void load();
  }, [projectId, wellId]);

  const plotHeight = fullscreen ? window.innerHeight - 180 : 520;

  const traces = useMemo(() => {
    if (!data) return [];
    if ('series' in data && Array.isArray(data.series) && data.series.length && 'points' in data.series[0]) {
      return (data as ProjectTrajectoryResponse).series.map((item, i) => ({
        type: 'scatter',
        mode: 'lines+markers',
        name: item.well_name,
        x: item.points.map(p => p.easting),
        y: item.points.map(p => p.northing),
        text: item.points.map(p => `${item.well_name}<br>Глуб. по стволу: ${p.md} м<br>ВГ: ${p.tvd.toFixed(1)} м`),
        hovertemplate: '%{text}<extra></extra>',
        line: { color: WELL_COLORS[i % WELL_COLORS.length], width: 2 },
        marker: { color: WELL_COLORS[i % WELL_COLORS.length], size: 4 },
      }));
    }
    const points = (data as TrajectorySeriesResponse).series || [];
    return [{
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Рабочая скважина',
      x: points.map(p => p.easting),
      y: points.map(p => p.northing),
      text: points.map(p => `Глуб. по стволу: ${p.md} м<br>ВГ: ${p.tvd.toFixed(1)} м`),
      hovertemplate: '%{text}<extra></extra>',
      line: { color: '#20b2aa', width: 2.5 },
      marker: { color: '#20b2aa', size: 5 },
    }];
  }, [data]);

  const isProject = !wellId;
  const title = isProject ? 'Карта проекта — горизонтальная проекция' : 'План скважины — горизонтальная проекция';

  return (
    <PlotFrame
      title={title}
      subtitle={`Азимут плоскости проекции: ${azimuth}°`}
      tools={
        <div className="nav-plot-controls">
          <div className="nav-control-group">
            <label className="nav-control-label">
              <Crosshair size={12} />
              Азимут
            </label>
            <input
              type="number" min={0} max={360} value={azimuth}
              className="nav-control-input"
              onChange={e => setAzimuth(Number(e.target.value))}
            />
            <span className="nav-control-unit">°</span>
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
          <span>Загрузка данных плана...</span>
        </div>
      ) : traces.length === 0 ? (
        <div className="nav-plot-nodata">
          <ZoomIn size={32} />
          <div>Нет данных для отображения плана</div>
          <div className="nav-nodata-sub">Проверьте наличие инклинометрических данных в системе</div>
        </div>
      ) : (
        <Plot
          data={traces as never}
          layout={{
            ...navigatorLayout,
            height: plotHeight,
            xaxis: {
              ...navigatorLayout.xaxis,
              title: { text: '→ ВОСТОК (гео.) (м)', font: { color: '#8aacb8', size: 11 } },
              scaleanchor: 'y',
              scaleratio: 1,
            },
            yaxis: {
              ...navigatorLayout.yaxis,
              title: { text: '→ СЕВЕР (гео.) (м)', font: { color: '#8aacb8', size: 11 } },
            },
            showlegend: true,
            legend: { ...navigatorLayout.legend, x: 0.01, y: 0.99, xanchor: 'left', yanchor: 'top' },
          }}
          config={plotConfig}
          style={{ width: '100%', height: plotHeight }}
        />
      )}
      {data?.warnings?.length ? <div className="nav-plot-warn">{data.warnings.join(' · ')}</div> : null}
    </PlotFrame>
  );
}
