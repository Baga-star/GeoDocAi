import { useState } from 'react';
import { trajectoryJson } from './api';
import type { ForecastResponse } from './types';

export function ForecastPanel({ wellId }: { wellId: string }) {
  const [targetMd, setTargetMd] = useState(0);
  const [result, setResult] = useState<ForecastResponse | null>(null);
  const [error, setError] = useState('');
  const requestContract = async () => {
    setError('');
    try { setResult(await trajectoryJson(`/trajectory/well/${wellId}/forecast`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: 'contract' }) })); } catch (err) { setError(err instanceof Error ? err.message : 'Ошибка прогноза'); }
  };
  const requestBasic = async () => {
    setError('');
    try { setResult(await trajectoryJson(`/trajectory/well/${wellId}/forecast`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: 'basic_hold', target_md: targetMd }) })); } catch (err) { setError(err instanceof Error ? err.message : 'Ошибка прогноза'); }
  };
  return (
    <section className="trajectory-table-card compact">
      <h2>Прогноз траектории</h2>
      <p>Phase 1 не выдумывает steering-модель. Без BHA, DLS limits, target window и uncertainty rules backend возвращает честный service contract.</p>
      <div className="forecast-actions">
        <button type="button" onClick={requestContract}>Проверить service contract</button>
        <label>Target MD <input type="number" value={targetMd} onChange={e => setTargetMd(Number(e.target.value))} /></label>
        <button type="button" onClick={requestBasic}>Basic hold</button>
      </div>
      {error ? <div className="traj-error">{error}</div> : null}
      {result ? <div className="traj-warning"><strong>{result.status}</strong><br />{result.warnings.join(' · ')}<br />Forecast points: {result.series.length}</div> : null}
    </section>
  );
}
