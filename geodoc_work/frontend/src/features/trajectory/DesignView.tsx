import { useEffect, useMemo, useState } from 'react';
import { trajectoryJson } from './api';
import { Plot, PlotFrame, navigatorLayout, plotConfig } from './PlotFrame';
import type { TrajectorySeriesResponse } from './types';

export function DesignView({ wellId }: { wellId: string }) {
  const [data, setData] = useState<TrajectorySeriesResponse | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    trajectoryJson<TrajectorySeriesResponse>(`/trajectory/well/${wellId}/design`).then(setData).catch(err => setError(err instanceof Error ? err.message : 'Ошибка проекта'));
  }, [wellId]);
  const points = data?.series || [];
  const traces = useMemo(() => [{ type: 'scatter', mode: 'lines+markers', name: 'design', x: points.map(p => p.vertical_section ?? p.northing), y: points.map(p => p.tvd), text: points.map(p => `MD ${p.md} м`) }], [points]);
  return (
    <PlotFrame title="Проектный профиль">
      {error ? <div className="traj-warning">{error}</div> : null}
      <Plot data={traces as never} layout={{ ...navigatorLayout, height: 520, xaxis: { ...navigatorLayout.xaxis, title: 'Vertical section, m' }, yaxis: { ...navigatorLayout.yaxis, title: 'TVD, m', autorange: 'reversed' } }} config={plotConfig} style={{ width: '100%', height: 520 }} />
      {data?.warnings?.length ? <div className="traj-warning">{data.warnings.join(' · ')}</div> : null}
    </PlotFrame>
  );
}
