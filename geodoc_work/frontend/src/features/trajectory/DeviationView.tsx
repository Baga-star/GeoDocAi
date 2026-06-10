import { useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { trajectoryJson } from './api';
import { Plot, PlotFrame, navigatorLayout, plotConfig } from './PlotFrame';
import type { DeviationResponse, DeviationRow } from './types';

function fmt(v: number | null | undefined, dec = 1): string {
  return v == null ? '—' : v.toFixed(dec);
}

export function DeviationView({ wellId }: { wellId: string }) {
  const [data, setData] = useState<DeviationResponse | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState('');

  const load = () => {
    trajectoryJson<DeviationResponse>(`/trajectory/well/${wellId}/deviation`)
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Ошибка отклонения'));
  };
  useEffect(() => { load(); }, [wellId]);

  const rows = data?.rows || [];
  const selRow: DeviationRow | null = selected != null ? rows[selected] ?? null : null;

  const traces = useMemo(() => {
    if (!rows.length) return [];
    const out: unknown[] = [];
    out.push({
      type: 'scatter', mode: 'lines+markers', name: 'Отклонение от проекта',
      x: rows.map(r => r.md), y: rows.map(r => r.distance_m ?? 0),
      text: rows.map(r => `ГПИ: ${r.md} м<br>Отклонение: ${fmt(r.distance_m, 2)} м<br>ΔTVD: ${fmt(r.delta_tvd, 2)} м<br>ΔСевер: ${fmt(r.delta_northing, 2)} м<br>ΔВосток: ${fmt(r.delta_easting, 2)} м`),
      hovertemplate: '%{text}<extra></extra>',
      line: { color: '#ef4444', width: 2 }, marker: { size: 4 },
    });
    if (selRow) {
      out.push({
        type: 'scatter', mode: 'markers', name: 'Выбранная точка',
        x: [selRow.md], y: [selRow.distance_m ?? 0],
        marker: { size: 14, color: '#facc15', symbol: 'circle-open', line: { width: 3 } },
        hoverinfo: 'skip', showlegend: false,
      });
    }
    out.push({
      type: 'scatter', mode: 'lines', name: 'Нулевое отклонение',
      x: [rows[0].md, rows[rows.length - 1].md], y: [0, 0],
      line: { color: '#22d3ee', width: 1, dash: 'dot' }, hoverinfo: 'skip',
    });
    return out;
  }, [rows, selRow]);

  return (
    <div className="nav-deviation-layout">
      <PlotFrame
        title="Отклонение от проектного профиля"
        subtitle="Минимальное расстояние между рабочим стволом и проектом"
        tools={
          <button type="button" className="nav-plot-btn-sm" onClick={load}>
            <RefreshCw size={13} /> Вычислить
          </button>
        }
      >
        {error ? <div className="nav-plot-error">{error}</div> : null}
        {!rows.length && !error ? (
          <div className="nav-plot-nodata">
            <strong>Нет данных отклонения</strong>
            <p>Для расчёта необходим импортированный и подтверждённый проектный профиль.</p>
          </div>
        ) : (
          <>
            {data?.max_distance_m != null && (
              <div className="nav-deviation-stat">
                <span>Макс. отклонение:</span>
                <strong style={{ color: '#ef4444' }}>{data.max_distance_m.toFixed(2)} м</strong>
                {selRow && (
                  <>
                    <span className="nav-deviation-sep">|</span>
                    <span>Выбрано ГПИ: {selRow.md} м — отклонение: {fmt(selRow.distance_m, 2)} м</span>
                  </>
                )}
              </div>
            )}
            <div className="nav-deviation-chart">
              <Plot
                data={traces as never}
                layout={{
                  ...navigatorLayout, height: 300,
                  xaxis: { ...navigatorLayout.xaxis, title: 'Глубина по стволу (м)' },
                  yaxis: { ...navigatorLayout.yaxis, title: 'Отклонение от проекта (м)' },
                  legend: { ...navigatorLayout.legend, orientation: 'h' as const, y: -0.25 },
                }}
                config={plotConfig}
                style={{ width: '100%', height: 300 }}
              />
            </div>
          </>
        )}
        {data?.warnings?.length ? <div className="nav-plot-warn">{data.warnings.join(' · ')}</div> : null}
      </PlotFrame>

      {rows.length > 0 && (
        <div className="nav-deviation-table">
          <div className="nav-deviation-table-header">
            <span>Таблица анализируемых точек ствола скважины</span>
            <small>Выберите строку для подсветки на графике</small>
          </div>
          <div className="nav-table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Глубина по стволу (м)</th>
                  <th>Верт. глубина (м)</th>
                  <th>Север (м)</th>
                  <th>Восток (м)</th>
                  <th>Пр. ГПИ (м)</th>
                  <th>Отклонение (м)</th>
                  <th>ΔTVD (м)</th>
                  <th>ΔСевер (м)</th>
                  <th>ΔВосток (м)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr
                    key={`${row.md}-${i}`}
                    className={`nav-table-row ${selected === i ? 'selected' : ''} ${row.distance_m != null && row.distance_m > 15 ? 'warn' : ''}`}
                    onClick={() => setSelected(selected === i ? null : i)}
                  >
                    <td>{fmt(row.md)}</td>
                    <td>{fmt(row.tvd)}</td>
                    <td>{fmt(row.northing, 2)}</td>
                    <td>{fmt(row.easting, 2)}</td>
                    <td>{fmt(row.nearest_design_md)}</td>
                    <td className={row.distance_m != null && row.distance_m > 15 ? 'cell-alert' : ''}>{fmt(row.distance_m, 2)}</td>
                    <td>{fmt(row.delta_tvd, 2)}</td>
                    <td>{fmt(row.delta_northing, 2)}</td>
                    <td>{fmt(row.delta_easting, 2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
