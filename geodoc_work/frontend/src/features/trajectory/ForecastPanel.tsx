import { useMemo, useState } from 'react';
import { BarChart2, Play, RefreshCw } from 'lucide-react';
import { trajectoryJson } from './api';
import { Plot, PlotFrame, navigatorLayout, plotConfig } from './PlotFrame';
import type { ForecastResponse } from './types';

export function ForecastPanel({ wellId }: { wellId: string }) {
  const [targetMd, setTargetMd] = useState('');
  const [stepM, setStepM] = useState('10');
  const [result, setResult] = useState<ForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const run = async () => {
    setLoading(true); setError(''); setResult(null);
    try {
      const body = {
        mode: 'basic_hold',
        target_md: Number(targetMd) || undefined,
        step_m: Number(stepM) || 10,
      };
      const r = await trajectoryJson<ForecastResponse>(
        `/trajectory/well/${wellId}/forecast`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
      );
      setResult(r);
      if (r.status === 'warning' && !r.series?.length) {
        setError(r.warnings.join(' '));
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Ошибка прогноза'); }
    finally { setLoading(false); }
  };

  const traces = useMemo(() => {
    if (!result?.series?.length) return [];
    const pts = result.series;
    return [{
      type: 'scatter', mode: 'lines+markers', name: 'Прогноз (hold)',
      x: pts.map(p => p.vertical_section ?? 0),
      y: pts.map(p => -p.tvd),
      text: pts.map(p => `ГПИ: ${p.md} м | TVD: ${p.tvd.toFixed(1)} м`),
      hovertemplate: '%{text}<extra></extra>',
      line: { color: '#34d399', width: 2, dash: 'dot' },
      marker: { size: 3 },
    }];
  }, [result]);

  return (
    <PlotFrame
      title="Прогноз траектории"
      subtitle="Геометрическое продление ствола по последнему зениту и азимуту"
      tools={
        <>
          <div className="nav-control-group">
            <span className="nav-control-label">Цел. ГПИ:</span>
            <input
              className="nav-control-input"
              type="number" min={0} placeholder="напр. 3500"
              value={targetMd} onChange={e => setTargetMd(e.target.value)}
              style={{ width: 90 }}
            />
            <span className="nav-control-unit">м</span>
          </div>
          <div className="nav-control-group">
            <span className="nav-control-label">Шаг:</span>
            <input
              className="nav-control-input"
              type="number" min={1} max={100}
              value={stepM} onChange={e => setStepM(e.target.value)}
              style={{ width: 52 }}
            />
            <span className="nav-control-unit">м</span>
          </div>
          <button type="button" className="nav-plot-btn-sm" onClick={run} disabled={loading || !targetMd}>
            {loading ? <RefreshCw size={13} /> : <Play size={13} />}
            {loading ? 'Расчёт…' : 'Вычислить'}
          </button>
        </>
      }
    >
      {error ? <div className="nav-plot-error">{error}</div> : null}

      {!result && !error && (
        <div className="nav-plot-nodata">
          <BarChart2 size={36} />
          <strong>Прогноз не выполнен</strong>
          <p>Введите целевую глубину по стволу (ГПИ) и нажмите «Вычислить».</p>
          <p className="nav-plot-subtitle" style={{ marginTop: 8, fontSize: 11, maxWidth: 420 }}>
            Метод «Удержание» — геометрическое продление скважины с сохранением
            последних значений зенита и азимута. Подходит для оперативной оценки
            забоя при неизменном направлении бурения.
          </p>
        </div>
      )}

      {result?.series?.length ? (
        <>
          <div className="nav-deviation-stat">
            <span>Точек прогноза:</span>
            <strong style={{ color: '#34d399' }}>{result.series.length}</strong>
            <span>|</span>
            <span>Конечная ГПИ:</span>
            <strong>{result.series[result.series.length - 1]?.md.toFixed(0)} м</strong>
            <span>|</span>
            <span>TVD:</span>
            <strong>{result.series[result.series.length - 1]?.tvd.toFixed(1)} м</strong>
          </div>
          <Plot
            data={traces as never}
            layout={{
              ...navigatorLayout,
              height: 360,
              xaxis: { ...navigatorLayout.xaxis, title: 'Отход (верт. секция) → (м)', autorange: true },
              yaxis: { ...navigatorLayout.yaxis, title: '↓ Вертикальная глубина (м)', autorange: true },
            }}
            config={plotConfig}
            style={{ width: '100%', height: 360 }}
          />
          {result.warnings?.length ? (
            <div className="nav-plot-warn" style={{ marginTop: 8 }}>
              ℹ️ {result.warnings.join(' ')}
            </div>
          ) : null}
        </>
      ) : null}
    </PlotFrame>
  );
}
