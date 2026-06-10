import { useEffect, useState } from 'react';
import { CheckCircle2, RefreshCw } from 'lucide-react';
import { trajectoryJson } from './api';
import type { SurveyDataResponse, SurveyStation } from './types';

function toNum(value: string): number {
  const num = Number(String(value).replace(',', '.'));
  return Number.isFinite(num) ? num : 0;
}

export function TrajectoryDataGrid({ wellId, projectId, wellName }: { wellId: string; projectId?: string; wellName?: string }) {
  const [data, setData] = useState<SurveyDataResponse | null>(null);
  const [rows, setRows] = useState<SurveyStation[]>([]);
  const [status, setStatus] = useState('');

  const load = async () => {
    setStatus('');
    const next = await trajectoryJson<SurveyDataResponse>(`/trajectory/well/${wellId}/data`);
    setData(next);
    setRows(next.stations || []);
  };
  useEffect(() => { void load().catch(err => setStatus(err instanceof Error ? err.message : 'Ошибка данных')); }, [wellId]);

  const updateRow = (index: number, field: keyof SurveyStation, value: string | boolean) => {
    setRows(prev => prev.map((row, ri) => ri === index ? { ...row, [field]: typeof value === 'boolean' ? value : toNum(value) } : row));
  };

  const approveAndRecalculate = async () => {
    setStatus('Сохраняю корректировки и пересчитываю…');
    try {
      await trajectoryJson('/trajectory/import-survey', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          project_name: 'Trajectory project',
          well_id: wellId,
          well_name: wellName || 'Well',
          approved: true,
          columns: ['MD', 'Inc', 'Azi'],
          rows: rows.map(row => [row.md, row.inc, row.azi]),
        }),
      });
      await trajectoryJson(`/trajectory/recalculate/${wellId}`, { method: 'POST' });
      setStatus('Данные подтверждены, траектория пересчитана');
      await load();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Не удалось подтвердить данные');
    }
  };

  return (
    <section className="trajectory-table-card">
      <header>
        <div><span className="label">Validation grid</span><h2>Данные инклинометрии</h2></div>
        <div className="plot-tools"><button type="button" onClick={load}><RefreshCw size={15} />Обновить</button><button type="button" onClick={approveAndRecalculate}><CheckCircle2 size={15} />Подтвердить и пересчитать</button></div>
      </header>
      {data?.validation?.warnings?.length ? <div className="traj-warning">{data.validation.warnings.join(' · ')}</div> : null}
      {data?.validation?.errors?.length ? <div className="traj-error">{data.validation.errors.join(' · ')}</div> : null}
      <div className="table-scroll">
        <table>
          <thead><tr><th>MD</th><th>Inc / зенит</th><th>Azi / азимут</th><th>Approved</th><th>Source</th></tr></thead>
          <tbody>{rows.map((row, index) => (
            <tr key={`${row.md}-${index}`}>
              <td><input value={row.md} onChange={e => updateRow(index, 'md', e.target.value)} /></td>
              <td><input value={row.inc} onChange={e => updateRow(index, 'inc', e.target.value)} /></td>
              <td><input value={row.azi} onChange={e => updateRow(index, 'azi', e.target.value)} /></td>
              <td><input type="checkbox" checked={row.approved} onChange={e => updateRow(index, 'approved', e.target.checked)} /></td>
              <td><small>{row.provenance?.document_name || 'manual'} {row.provenance?.page ? `стр. ${row.provenance.page}` : ''} {row.provenance?.row_index ? `строка ${row.provenance.row_index}` : ''}</small></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      {data?.segments?.length ? <p className="traj-footnote">Проектных сегментов: {data.segments.length}. Они используются в «Проектный профиль» и «Отклонение».</p> : null}
      {status ? <div className="traj-warning">{status}</div> : null}
    </section>
  );
}
