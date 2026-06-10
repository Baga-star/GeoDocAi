import { useEffect, useMemo, useState } from 'react';
import { trajectoryJson } from './api';
import { Plot, PlotFrame, navigatorLayout, plotConfig } from './PlotFrame';
import type { DeviationResponse, DeviationRow } from './types';

export function DeviationView({ wellId }: { wellId: string }) {
  const [data, setData] = useState<DeviationResponse | null>(null);
  const [error, setError] = useState('');
  const [selectedRow, setSelectedRow] = useState<DeviationRow | null>(null);

  useEffect(() => {
    trajectoryJson<DeviationResponse>(`/trajectory/well/${wellId}/deviation`)
      .then(d => { setData(d); if (d.rows.length) setSelectedRow(d.rows[0]); })
      .catch(err => setError(err instanceof Error ? err.message : 'Ошибка отклонения'));
  }, [wellId]);

  const rows = data?.rows || [];

  const traces = useMemo(() => {
    const out: unknown[] = [{
      type: 'scatter',
      mode: 'lines',
      name: 'Отклонение от проекта',
      x: rows.map(r => r.md),
      y: rows.map(r => r.distance_m ?? 0),
      line: { color: '#f97316', width: 2 },
      hovertemplate: 'Глуб. по стволу: %{x} м<br>Отклонение: %{y:.2f} м<extra></extra>',
    }];

    if (selectedRow) {
      out.push({
        type: 'scatter',
        mode: 'markers',
        name: 'Выбранная точка',
        x: [selectedRow.md],
        y: [selectedRow.distance_m ?? 0],
        marker: { color: '#fbbf24', size: 12, symbol: 'circle', line: { color: '#fff', width: 2 } },
        hovertemplate: 'Глуб. по стволу: %{x} м<br>Отклонение: %{y:.2f} м<extra></extra>',
      });
    }
    return out;
  }, [rows, selectedRow]);

  const fmt = (v?: number | null) => v != null ? v.toFixed(2) : '—';

  return (
    <div className="nav-deviation-layout">
      {/* Left: table */}
      <div className="nav-deviation-table">
        <div className="nav-table-header">
          <div className="nav-table-title">Анализ отклонения от проектного профиля</div>
          {data?.max_distance_m != null && (
            <div className="nav-table-stat">
              Макс. отклонение: <strong>{data.max_distance_m.toFixed(2)} м</strong>
            </div>
          )}
        </div>
        {error ? <div className="nav-plot-error">{error}</div> : null}
        <div className="nav-table-scroll">
          <table className="nav-table">
            <thead>
              <tr>
                <th>Откл. (м)</th>
                <th>Верт.глуб. (м)</th>
                <th>Хотн. (м)</th>
                <th>Йотн. (м)</th>
                <th>Верт.глуб.пр. (м)</th>
                <th>Хотн.пр. (м)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr
                  key={`${row.md}-${row.nearest_design_md}`}
                  className={selectedRow?.md === row.md ? 'nav-table-row-active' : ''}
                  onClick={() => setSelectedRow(row)}
                >
                  <td className="nav-td-accent">{fmt(row.distance_m)}</td>
                  <td>{fmt(row.tvd)}</td>
                  <td>{fmt(row.northing)}</td>
                  <td>{fmt(row.easting)}</td>
                  <td>{fmt(row.delta_tvd != null ? row.tvd + row.delta_tvd : null)}</td>
                  <td>{fmt(row.delta_northing != null ? row.northing + row.delta_northing : null)}</td>
                </tr>
              ))}
              {!rows.length && (
                <tr><td colSpan={6} className="nav-table-empty">Нет данных отклонения</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {selectedRow && (
          <div className="nav-selected-info">
            <span className="nav-selected-label">Выбрана точка:</span>
            <span>Глуб. по стволу <strong>{selectedRow.md} м</strong></span>
            <span>Отклонение <strong>{fmt(selectedRow.distance_m)} м</strong></span>
            <span>ΔN <strong>{fmt(selectedRow.delta_northing)}</strong></span>
            <span>ΔE <strong>{fmt(selectedRow.delta_easting)}</strong></span>
            <span>ΔH <strong>{fmt(selectedRow.delta_tvd)}</strong></span>
          </div>
        )}
      </div>

      {/* Right: chart */}
      <div className="nav-deviation-chart">
        <PlotFrame
          title="Отклонение от проектного профиля"
          subtitle="Минимальное расстояние до ближайшей точки проекта"
        >
          {traces.length > 0 ? (
            <Plot
              data={traces as never}
              layout={{
                ...navigatorLayout,
                height: 420,
                xaxis: {
                  ...navigatorLayout.xaxis,
                  title: { text: 'Глубина по стволу (м)', font: { color: '#8aacb8', size: 11 } },
                },
                yaxis: {
                  ...navigatorLayout.yaxis,
                  title: { text: 'Отклонение от проекта (м)', font: { color: '#8aacb8', size: 11 } },
                },
                showlegend: true,
                legend: { ...navigatorLayout.legend, x: 0.99, y: 0.99, xanchor: 'right', yanchor: 'top' },
              }}
              config={plotConfig}
              style={{ width: '100%', height: 420 }}
            />
          ) : (
            <div className="nav-plot-nodata">Нет данных отклонения</div>
          )}
          {data?.warnings?.length ? <div className="nav-plot-warn">{data.warnings.join(' · ')}</div> : null}
        </PlotFrame>
      </div>
    </div>
  );
}
