import { useEffect, useState } from 'react';
import { trajectoryJson } from './api';
import type { SeparationResponse } from './types';
import { GitCompareArrows } from 'lucide-react';

export function SeparationView({ projectId }: { projectId: string }) {
  const [data, setData] = useState<SeparationResponse | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    trajectoryJson<SeparationResponse>(`/trajectory/project/${projectId}/separation`)
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Ошибка анализа сближения'));
  }, [projectId]);

  const rows = data?.rows || [];
  const fmt = (v?: number | null) => v != null ? v.toFixed(2) : '—';

  return (
    <div className="nav-separation">
      <div className="nav-section-header">
        <GitCompareArrows size={18} />
        <div>
          <div className="nav-section-title">Анализ сближения скважин</div>
          <div className="nav-section-sub">Минимальные расстояния между стволами скважин в группе</div>
        </div>
      </div>

      {error ? <div className="nav-plot-error">{error}</div> : null}
      {data?.warnings?.length ? <div className="nav-plot-warn">{data.warnings.join(' · ')}</div> : null}

      {rows.length === 0 && !error ? (
        <div className="nav-plot-nodata">
          <GitCompareArrows size={32} />
          <div>Нет данных сближения</div>
          <div className="nav-nodata-sub">Убедитесь, что в проекте более одной скважины с инклинометрическими данными</div>
        </div>
      ) : (
        <div className="nav-table-scroll">
          <table className="nav-table">
            <thead>
              <tr>
                <th>Скважина 1</th>
                <th>Скважина 2</th>
                <th>Мин. расстояние (м)</th>
                <th>Глуб. скв. 1 (м)</th>
                <th>Глуб. скв. 2 (м)</th>
                <th>Метод</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={`${row.well_a_id}-${row.well_b_id}`}>
                  <td className="nav-td-name">{row.well_a_name}</td>
                  <td className="nav-td-name">{row.well_b_name}</td>
                  <td className={`nav-td-accent ${(row.min_distance_m ?? 999) < 10 ? 'nav-td-danger' : ''}`}>
                    {fmt(row.min_distance_m)}
                  </td>
                  <td>{fmt(row.md_a)}</td>
                  <td>{fmt(row.md_b)}</td>
                  <td className="nav-td-muted">{row.method}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
