import { useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { trajectoryJson } from './api';
import { Plot, PlotFrame, navigatorLayout, plotConfig } from './PlotFrame';
import type { ProjectTrajectoryResponse, SeparationResponse } from './types';

const WELL_COLORS = ['#ef4444', '#22d3ee', '#a78bfa', '#34d399', '#fb923c', '#f472b6', '#facc15'];
function fmt(v: number | null | undefined, dec = 1): string { return v == null ? '—' : v.toFixed(dec); }

export function SeparationView({ projectId }: { projectId: string }) {
  const [data, setData] = useState<SeparationResponse | null>(null);
  const [traj, setTraj] = useState<ProjectTrajectoryResponse | null>(null);
  const [error, setError] = useState('');

  const load = async () => {
    setError('');
    try {
      const [sep, t] = await Promise.all([
        trajectoryJson<SeparationResponse>(`/trajectory/project/${projectId}/separation`),
        trajectoryJson<ProjectTrajectoryResponse>(`/trajectory/project/${projectId}/3d`).catch(() => null),
      ]);
      setData(sep); setTraj(t);
    } catch (err) { setError(err instanceof Error ? err.message : 'Ошибка сближения'); }
  };
  useEffect(() => { void load(); }, [projectId]);

  const rows = data?.rows || [];
  const minRow = rows.reduce<typeof rows[0] | null>((best, r) => {
    if (r.min_distance_m == null) return best;
    if (best?.min_distance_m == null || r.min_distance_m < best.min_distance_m) return r;
    return best;
  }, null);

  const traces3d = useMemo(() => {
    if (!traj?.series?.length) return [];
    return traj.series.map((item, i) => ({
      type: 'scatter3d', mode: 'lines+markers', name: item.well_name,
      x: item.points.map(p => p.easting),
      y: item.points.map(p => p.northing),
      z: item.points.map(p => -p.tvd),
      text: item.points.map(p => `${item.well_name}<br>ГПИ: ${p.md} м`),
      hovertemplate: '%{text}<extra></extra>',
      line: { color: WELL_COLORS[i % WELL_COLORS.length], width: 4 },
      marker: { size: 2 },
    }));
  }, [traj]);

  return (
    <div className="nav-separation-layout">
      <PlotFrame
        title="Анализ сближения скважин"
        subtitle="Минимальные расстояния между скважинами группы"
        tools={<button type="button" className="nav-plot-btn-sm" onClick={load}><RefreshCw size={13} /> Вычислить</button>}
      >
        {error ? <div className="nav-plot-error">{error}</div> : null}
        {minRow && (
          <div className="nav-separation-stat">
            <span>Минимальное сближение:</span>
            <strong style={{ color: minRow.min_distance_m != null && minRow.min_distance_m < 20 ? '#ef4444' : '#4ade80' }}>
              {fmt(minRow.min_distance_m, 2)} м
            </strong>
            <span className="nav-separation-sep-label">
              {minRow.well_a_name} ↔ {minRow.well_b_name}
              &nbsp;|&nbsp; ГПИ A: {fmt(minRow.md_a, 0)} м &nbsp;|&nbsp; ГПИ B: {fmt(minRow.md_b, 0)} м
            </span>
          </div>
        )}
        {!rows.length && !error ? (
          <div className="nav-plot-nodata">
            <strong>Нет данных сближения</strong>
            <p>Для расчёта необходимо минимум две скважины с рассчитанными траекториями.</p>
          </div>
        ) : (
          <div className="nav-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Скважина A</th>
                  <th>Скважина B</th>
                  <th>Мин. расстояние (м)</th>
                  <th>ГПИ A (м)</th>
                  <th>ГПИ B (м)</th>
                  <th>Метод</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(row => (
                  <tr key={`${row.well_a_id}-${row.well_b_id}`} className={row.min_distance_m != null && row.min_distance_m < 20 ? 'nav-table-row warn' : 'nav-table-row'}>
                    <td>{row.well_a_name}</td>
                    <td>{row.well_b_name}</td>
                    <td className={row.min_distance_m != null && row.min_distance_m < 20 ? 'cell-alert' : ''}>{fmt(row.min_distance_m, 2)}</td>
                    <td>{fmt(row.md_a, 0)}</td>
                    <td>{fmt(row.md_b, 0)}</td>
                    <td>{row.method}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data?.warnings?.length ? <div className="nav-plot-warn">{data.warnings.join(' · ')}</div> : null}
      </PlotFrame>

      {traces3d.length > 0 && (
        <PlotFrame title="3D группы скважин" subtitle="Пространственное отображение">
          <Plot
            data={traces3d as never}
            layout={{
              ...navigatorLayout, height: 440,
              scene: {
                bgcolor: '#080e1c',
                xaxis: { title: '→ Восток (гео.) (м)', gridcolor: 'rgba(32,178,170,0.12)', color: '#8aacb8', showbackground: true, backgroundcolor: '#060d1a' },
                yaxis: { title: '→ Север (гео.) (м)', gridcolor: 'rgba(32,178,170,0.12)', color: '#8aacb8', showbackground: true, backgroundcolor: '#060d1a' },
                zaxis: { title: '↑ Глубина (м)', gridcolor: 'rgba(32,178,170,0.12)', color: '#8aacb8', showbackground: true, backgroundcolor: '#060d1a' },
                camera: { eye: { x: 1.2, y: 1.5, z: 0.9 } },
              },
              legend: { ...navigatorLayout.legend, x: 1.01, y: 1, orientation: 'v' as const },
              margin: { l: 0, r: 120, t: 24, b: 0 },
            }}
            config={{ ...plotConfig, scrollZoom: true }}
            style={{ width: '100%', height: 440 }}
          />
          <p className="nav-plot-subtitle" style={{ padding: '6px 4px 0', fontSize: 11 }}>Управление: левая кн. мыши — вращение, правая — перемещение, колесо — масштаб</p>
        </PlotFrame>
      )}
    </div>
  );
}
