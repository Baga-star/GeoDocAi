import { useEffect, useMemo, useState } from 'react';
import { Maximize2, RefreshCw, Navigation } from 'lucide-react';
import { trajectoryJson } from './api';
import { Plot, PlotFrame, navigatorLayout, plotConfig } from './PlotFrame';
import type { ProjectTrajectoryResponse, TrajectorySeriesResponse } from './types';

const WELL_COLORS = ['#ef4444', '#22d3ee', '#a78bfa', '#34d399', '#fb923c', '#f472b6'];

/** Rotate (easting, northing) by azimuth so that azimuth direction → X-axis */
function rotateByAzimuth(easting: number, northing: number, azDeg: number) {
  if (azDeg === 0) return { x: easting, y: northing };
  const az = (azDeg * Math.PI) / 180;
  return {
    x: easting * Math.cos(az) + northing * Math.sin(az),
    y: -easting * Math.sin(az) + northing * Math.cos(az),
  };
}

export function PlanView({
  projectId, wellId, fullscreen, onFullscreen,
}: {
  projectId?: string; wellId?: string; fullscreen?: boolean; onFullscreen?: () => void;
}) {
  const [data, setData] = useState<ProjectTrajectoryResponse | TrajectorySeriesResponse | null>(null);
  const [design, setDesign] = useState<TrajectorySeriesResponse | null>(null);
  const [azimuth, setAzimuth] = useState(0);
  const [azInput, setAzInput] = useState('0');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const path = wellId ? `/trajectory/well/${wellId}/plan` : `/trajectory/project/${projectId}/plan`;

  const load = async (az: number) => {
    setLoading(true); setError('');
    try {
      setData(await trajectoryJson(path));
      if (wellId) {
        const d = await trajectoryJson<TrajectorySeriesResponse>(
          `/trajectory/well/${wellId}/design?azimuth=${az}`
        ).catch(() => null);
        setDesign(d);
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Ошибка плана'); }
    finally { setLoading(false); }
  };

  useEffect(() => { if (projectId || wellId) void load(azimuth); }, [projectId, wellId]);

  const applyAzimuth = () => {
    const val = Number(azInput);
    if (!isNaN(val)) { setAzimuth(val); void load(val); }
  };

  const traces = useMemo(() => {
    const out: unknown[] = [];
    if (!data) return out;

    const rotate = (e: number, n: number) => rotateByAzimuth(e, n, azimuth);

    // Project plan (multiple wells)
    if ('series' in data && Array.isArray(data.series) && data.series.length && 'points' in data.series[0]) {
      const proj = data as ProjectTrajectoryResponse;
      proj.series.forEach((item, i) => {
        const pts = item.points.map(p => rotate(p.easting, p.northing));
        out.push({
          type: 'scatter', mode: 'lines+markers', name: item.well_name,
          x: pts.map(p => p.x), y: pts.map(p => p.y),
          text: item.points.map(p => `${item.well_name}<br>ГПИ: ${p.md} м<br>TVD: ${p.tvd.toFixed(1)} м`),
          hovertemplate: '%{text}<extra></extra>',
          line: { color: WELL_COLORS[i % WELL_COLORS.length], width: 2.5 },
          marker: { size: 4 },
        });
        // Well label at endpoint
        const last = item.points[item.points.length - 1];
        if (last) {
          const lp = rotate(last.easting, last.northing);
          out.push({
            type: 'scatter', mode: 'text', showlegend: false,
            x: [lp.x], y: [lp.y], text: [item.well_name],
            textposition: 'top right',
            textfont: { color: WELL_COLORS[i % WELL_COLORS.length], size: 11 },
            hoverinfo: 'skip',
          });
        }
      });
      return out;
    }

    // Single well plan
    const points = (data as TrajectorySeriesResponse).series || [];
    const pts = points.map(p => rotate(p.easting, p.northing));
    out.push({
      type: 'scatter', mode: 'lines+markers', name: 'Рабочая скважина',
      x: pts.map(p => p.x), y: pts.map(p => p.y),
      text: points.map(p => `ГПИ: ${p.md} м | Верт. глубина: ${p.tvd.toFixed(1)} м`),
      hovertemplate: '%{text}<extra></extra>',
      line: { color: '#ef4444', width: 2.5 }, marker: { size: 4 },
    });

    if (design?.series?.length) {
      const dp = design.series;
      const dpts = dp.map(p => rotate(p.easting, p.northing));
      out.push({
        type: 'scatter', mode: 'lines', name: 'Проект',
        x: dpts.map(p => p.x), y: dpts.map(p => p.y),
        text: dp.map(p => `Проект ГПИ: ${p.md} м`),
        hovertemplate: '%{text}<extra></extra>',
        line: { color: '#22d3ee', width: 2, dash: 'dash' },
      });
      const TOL = 10;
      out.push({
        type: 'scatter', mode: 'lines', name: 'Коридор допуска',
        x: [...dpts.map(p => p.x - TOL), ...dpts.map(p => p.x + TOL).reverse()],
        y: [...dpts.map(p => p.y), ...dpts.map(p => p.y).reverse()],
        fill: 'toself', fillcolor: 'rgba(34,211,238,0.07)',
        line: { color: 'rgba(34,211,238,0.25)', width: 1, dash: 'dot' }, hoverinfo: 'skip',
      });
      const last = dp[dp.length - 1];
      if (last) {
        const lp = rotate(last.easting, last.northing);
        const R = 20;
        const angles = Array.from({ length: 37 }, (_, i) => (i * Math.PI * 2) / 36);
        out.push({
          type: 'scatter', mode: 'lines', name: 'Круг допуска',
          x: angles.map(a => lp.x + R * Math.cos(a)),
          y: angles.map(a => lp.y + R * Math.sin(a)),
          line: { color: '#a78bfa', width: 1.5 }, hoverinfo: 'skip',
        });
      }
    }

    return out;
  }, [data, design, azimuth]);

  const h = fullscreen ? 680 : 480;
  const xLabel = azimuth === 0
    ? 'Восток → (м)'
    : `Ось азимута ${azimuth}° → (м)`;
  const yLabel = azimuth === 0
    ? '↑ Север (м)'
    : `↑ Перпендикуляр к азимуту ${azimuth}°`;

  return (
    <PlotFrame
      title={wellId ? 'План скважины' : 'Карта проекта — план группы скважин'}
      subtitle="Горизонтальная проекция"
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
            <button type="button" className={`nav-plot-btn-sm ${loading ? '' : ''}`} onClick={applyAzimuth} disabled={loading}>
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
      {!data || loading ? (
        <div className="nav-plot-nodata">
          {loading ? <strong>Загрузка…</strong> : <><strong>Нет данных плана</strong><p>Необходимы рассчитанные координаты.</p></>}
        </div>
      ) : (
        <Plot
          data={traces as never}
          layout={{
            ...navigatorLayout,
            height: h,
            xaxis: {
              ...navigatorLayout.xaxis,
              title: xLabel,
              // NO scaleanchor - let Plotly auto-fit to container
              autorange: true,
            },
            yaxis: {
              ...navigatorLayout.yaxis,
              title: yLabel,
              autorange: true,
            },
            legend: { ...navigatorLayout.legend, x: 1.01, y: 1, orientation: 'v' as const },
            annotations: [{
              x: 0.01, y: 0.99, xref: 'paper', yref: 'paper',
              text: azimuth === 0
                ? 'Азимут плоскости: 0° (Стандарт: Север вверх)'
                : `Азимут плоскости: ${azimuth}° — повёрнуто`,
              showarrow: false,
              font: { color: '#6a8a9a', size: 10 }, align: 'left',
            }],
          }}
          config={plotConfig}
          style={{ width: '100%', height: h }}
        />
      )}
      {data && !loading && (data as { warnings?: string[] }).warnings?.length ? (
        <div className="nav-plot-warn">{(data as { warnings: string[] }).warnings.join(' · ')}</div>
      ) : null}
    </PlotFrame>
  );
}
