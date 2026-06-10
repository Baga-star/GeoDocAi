import { useEffect, useMemo, useState } from 'react';
import { RefreshCw, ZoomIn, Eye, EyeOff } from 'lucide-react';
import { trajectoryJson } from './api';
import { Plot, PlotFrame, plotConfig } from './PlotFrame';
import type { ProjectTrajectoryResponse, TrajectorySeriesResponse } from './types';

const WELL_COLORS = ['#20b2aa', '#f97316', '#a78bfa', '#34d399', '#fb923c', '#60a5fa', '#f472b6', '#facc15'];

const scene3DLayout = {
  paper_bgcolor: '#080e1c',
  plot_bgcolor: '#080e1c',
  font: { color: '#c8d8e0', family: 'Inter, ui-monospace, system-ui, sans-serif', size: 11 },
};

export function ThreeDView({ projectId, wellId }: { projectId?: string; wellId?: string }) {
  const [showActual, setShowActual] = useState(true);
  const [showDesign, setShowDesign] = useState(true);
  const [actual, setActual] = useState<ProjectTrajectoryResponse | TrajectorySeriesResponse | null>(null);
  const [design, setDesign] = useState<TrajectorySeriesResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setError('');
    setLoading(true);
    try {
      setActual(await trajectoryJson(wellId ? `/trajectory/well/${wellId}/3d` : `/trajectory/project/${projectId}/3d`));
      if (wellId) {
        setDesign(await trajectoryJson<TrajectorySeriesResponse>(`/trajectory/well/${wellId}/design`).catch(() => null));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки 3D данных');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (projectId || wellId) void load();
  }, [projectId, wellId]);

  const traces = useMemo(() => {
    const out: unknown[] = [];
    const addPoints = (
      name: string,
      points: Array<{ easting: number; northing: number; tvd: number; md: number; inc: number; azi: number }>,
      color: string,
      dash?: string
    ) => {
      out.push({
        type: 'scatter3d',
        mode: 'lines+markers',
        name,
        x: points.map(p => p.easting),
        y: points.map(p => p.northing),
        z: points.map(p => -p.tvd),
        text: points.map(p => `Глуб. по стволу: ${p.md} м<br>Зенит: ${p.inc.toFixed(2)}°<br>Азимут: ${p.azi.toFixed(2)}°<br>ВГ: ${p.tvd.toFixed(1)} м`),
        hovertemplate: '%{text}<extra></extra>',
        line: { color, width: 3, dash: dash || 'solid' },
        marker: { color, size: 3 },
      });
    };

    if (showActual && actual) {
      if ('series' in actual && actual.series.length && 'points' in actual.series[0]) {
        (actual as ProjectTrajectoryResponse).series.forEach((item, i) =>
          addPoints(item.well_name, item.points, WELL_COLORS[i % WELL_COLORS.length])
        );
      } else {
        addPoints('Рабочая скважина', (actual as TrajectorySeriesResponse).series || [], '#20b2aa');
      }
    }
    if (showDesign && design?.series?.length) {
      addPoints('Проектный профиль', design.series, '#fbbf24', 'dash');
    }
    return out;
  }, [actual, design, showActual, showDesign]);

  const isProject = !wellId;

  return (
    <PlotFrame
      title={isProject ? '3D группы скважин' : '3D траектория скважины'}
      subtitle="Пространственное положение ствола скважины"
      tools={
        <div className="nav-plot-controls">
          <button
            type="button"
            className={`nav-layer-toggle ${showActual ? 'on' : 'off'}`}
            onClick={() => setShowActual(v => !v)}
          >
            {showActual ? <Eye size={13} /> : <EyeOff size={13} />}
            Рабочая скважина
          </button>
          {design && (
            <button
              type="button"
              className={`nav-layer-toggle ${showDesign ? 'on' : 'off'}`}
              onClick={() => setShowDesign(v => !v)}
            >
              {showDesign ? <Eye size={13} /> : <EyeOff size={13} />}
              Проект
            </button>
          )}
          <button type="button" className="nav-plot-btn" onClick={load} disabled={loading}>
            <RefreshCw size={13} className={loading ? 'nav-spin' : ''} />
            Обновить
          </button>
        </div>
      }
    >
      {error ? <div className="nav-plot-error">{error}</div> : null}
      {loading && !actual ? (
        <div className="nav-plot-loading">
          <RefreshCw size={24} className="nav-spin" />
          <span>Загрузка 3D данных...</span>
        </div>
      ) : traces.length === 0 ? (
        <div className="nav-plot-nodata">
          <ZoomIn size={32} />
          <div>Нет данных для 3D отображения</div>
          <div className="nav-nodata-sub">Требуются координаты: Север, Восток, Вертикальная глубина</div>
        </div>
      ) : (
        <Plot
          data={traces as never}
          layout={{
            ...scene3DLayout,
            height: 580,
            margin: { l: 0, r: 0, t: 40, b: 0 },
            scene: {
              bgcolor: '#080e1c',
              xaxis: {
                title: 'Восток (м)',
                gridcolor: 'rgba(32,178,170,0.12)',
                zerolinecolor: 'rgba(32,178,170,0.3)',
                tickfont: { color: '#8aacb8', size: 10 },
                titlefont: { color: '#c8d8e0', size: 11 },
              },
              yaxis: {
                title: 'Север (м)',
                gridcolor: 'rgba(32,178,170,0.12)',
                zerolinecolor: 'rgba(32,178,170,0.3)',
                tickfont: { color: '#8aacb8', size: 10 },
                titlefont: { color: '#c8d8e0', size: 11 },
              },
              zaxis: {
                title: 'Глубина (м)',
                gridcolor: 'rgba(32,178,170,0.12)',
                zerolinecolor: 'rgba(32,178,170,0.3)',
                tickfont: { color: '#8aacb8', size: 10 },
                titlefont: { color: '#c8d8e0', size: 11 },
              },
              camera: { eye: { x: 1.5, y: 1.5, z: 0.8 } },
            },
            legend: {
              bgcolor: 'rgba(8,14,28,0.85)',
              bordercolor: 'rgba(32,178,170,0.2)',
              borderwidth: 1,
              font: { color: '#c8d8e0', size: 11 },
            },
            showlegend: true,
          }}
          config={{ ...plotConfig, modeBarButtonsToRemove: ['lasso2d', 'select2d', 'toImage'] }}
          style={{ width: '100%', height: 580 }}
        />
      )}
    </PlotFrame>
  );
}
