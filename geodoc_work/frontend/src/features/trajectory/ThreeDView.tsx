import { useEffect, useMemo, useState } from 'react';
import { RefreshCw, Eye, EyeOff } from 'lucide-react';
import { trajectoryJson } from './api';
import { Plot, PlotFrame, navigatorLayout, plotConfig } from './PlotFrame';
import type { ProjectTrajectoryResponse, TrajectorySeriesResponse } from './types';

const WELL_COLORS = ['#ef4444', '#22d3ee', '#a78bfa', '#34d399', '#fb923c', '#f472b6', '#facc15'];

export function ThreeDView({ projectId, wellId }: { projectId?: string; wellId?: string }) {
  const [showActual, setShowActual] = useState(true);
  const [showDesign, setShowDesign] = useState(true);
  const [actual, setActual] = useState<ProjectTrajectoryResponse | TrajectorySeriesResponse | null>(null);
  const [design, setDesign] = useState<TrajectorySeriesResponse | null>(null);
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    try {
      const a = await trajectoryJson<ProjectTrajectoryResponse | TrajectorySeriesResponse>(
        wellId ? `/trajectory/well/${wellId}/3d` : `/trajectory/project/${projectId}/3d`
      );
      setActual(a);
      if (wellId) {
        const d = await trajectoryJson<TrajectorySeriesResponse>(`/trajectory/well/${wellId}/design`).catch(() => null);
        setDesign(d);
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Ошибка 3D'); }
  };

  useEffect(() => { if (projectId || wellId) void load(); }, [projectId, wellId]);

  const traces = useMemo(() => {
    const out: unknown[] = [];
    const addLine = (name: string, points: Array<{ easting: number; northing: number; tvd: number; md: number }>, color: string, isDash = false) => {
      if (!points.length) return;
      out.push({
        type: 'scatter3d', mode: 'lines+markers', name,
        x: points.map(p => p.easting),
        y: points.map(p => p.northing),
        z: points.map(p => -p.tvd),
        text: points.map(p => `ГПИ: ${p.md} м<br>Восток: ${p.easting.toFixed(1)} м<br>Север: ${p.northing.toFixed(1)} м<br>Глубина: ${p.tvd.toFixed(1)} м`),
        hovertemplate: '%{text}<extra></extra>',
        line: { color, width: 4, dash: isDash ? 'dash' : undefined },
        marker: { size: 2, color },
      });
    };
    if (showActual && actual) {
      if ('series' in actual && actual.series.length && 'points' in actual.series[0]) {
        (actual as ProjectTrajectoryResponse).series.forEach((item, i) =>
          addLine(item.well_name, item.points, WELL_COLORS[i % WELL_COLORS.length])
        );
      } else {
        addLine('Рабочая скважина', (actual as TrajectorySeriesResponse).series || [], '#ef4444');
      }
    }
    if (showDesign && design?.series?.length) {
      addLine('Проект', design.series, '#22d3ee', true);
    }
    return out;
  }, [actual, design, showActual, showDesign]);

  return (
    <PlotFrame
      title={wellId ? '3D траектория скважины' : '3D группа скважин'}
      subtitle="Пространственное положение"
      tools={
        <>
          <button type="button" className={`nav-plot-btn-sm ${showActual ? 'active' : ''}`} onClick={() => setShowActual(v => !v)}>
            {showActual ? <Eye size={13} /> : <EyeOff size={13} />} Рабочая
          </button>
          <button type="button" className={`nav-plot-btn-sm ${showDesign ? 'active' : ''}`} onClick={() => setShowDesign(v => !v)}>
            {showDesign ? <Eye size={13} /> : <EyeOff size={13} />} Проект
          </button>
          <button type="button" className="nav-plot-btn-sm" onClick={load}><RefreshCw size={13} /> Обновить</button>
        </>
      }
    >
      {error ? <div className="nav-plot-error">{error}</div> : null}
      {!actual ? (
        <div className="nav-plot-nodata">
          <strong>Нет данных для 3D</strong>
          <p>Необходимы рассчитанные координаты: восток, север, вертикальная глубина (TVD).</p>
        </div>
      ) : (
        <>
          <Plot
            data={traces as never}
            layout={{
              ...navigatorLayout, height: 540,
              scene: {
                bgcolor: '#080e1c',
                xaxis: { title: '→ Восток (гео.) (м)', gridcolor: 'rgba(32,178,170,0.12)', color: '#8aacb8', showbackground: true, backgroundcolor: '#060d1a' },
                yaxis: { title: '→ Север (гео.) (м)', gridcolor: 'rgba(32,178,170,0.12)', color: '#8aacb8', showbackground: true, backgroundcolor: '#060d1a' },
                zaxis: { title: '↑ Глубина (м)', gridcolor: 'rgba(32,178,170,0.12)', color: '#8aacb8', showbackground: true, backgroundcolor: '#060d1a' },
                camera: { eye: { x: 1.5, y: 1.5, z: 0.8 } },
              },
              legend: { ...navigatorLayout.legend, x: 1.01, y: 1, orientation: 'v' as const },
              margin: { l: 0, r: 120, t: 30, b: 0 },
            }}
            config={{ ...plotConfig, scrollZoom: true }}
            style={{ width: '100%', height: 540 }}
          />
          <p className="nav-plot-subtitle" style={{ padding: '6px 4px 0', fontSize: 11 }}>
            Управление: левая кн. мыши — вращение, правая — перемещение, колесо — масштаб
          </p>
        </>
      )}
    </PlotFrame>
  );
}
