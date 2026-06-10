import { useEffect, useRef, type ReactNode } from 'react';

type PlotlyLite = {
  react: (element: HTMLElement, data: unknown[], layout: Record<string, unknown>, config?: Record<string, unknown>) => Promise<unknown>;
  purge: (element: HTMLElement) => void;
};

let plotlyPromise: Promise<PlotlyLite> | null = null;
function ensurePlotly(): Promise<PlotlyLite> {
  if (!plotlyPromise) {
    plotlyPromise = import('plotly.js-dist-min').then((mod) => mod.default as PlotlyLite);
  }
  return plotlyPromise;
}

export function Plot({ data, layout, config, style }: {
  data?: unknown[];
  layout?: Record<string, unknown>;
  config?: Record<string, unknown>;
  style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    let cancelled = false;
    ensurePlotly().then((Plotly) => {
      if (!cancelled && ref.current) {
        void Plotly.react(ref.current, data || [], layout || {}, config || {});
      }
    }).catch(() => undefined);
    return () => {
      cancelled = true;
      if (ref.current) void ensurePlotly().then(Plotly => Plotly.purge(ref.current as HTMLElement));
    };
  }, [data, layout, config]);
  return <div ref={ref} style={style} className="plotly-host" />;
}

// Dark engineering-grade plot theme
export const navigatorLayout = {
  paper_bgcolor: '#080e1c',
  plot_bgcolor: '#080e1c',
  font: { color: '#c8d8e0', family: 'Inter, ui-monospace, system-ui, sans-serif', size: 12 },
  margin: { l: 64, r: 24, t: 40, b: 56 },
  xaxis: {
    gridcolor: 'rgba(32,178,170,0.1)',
    gridwidth: 1,
    zerolinecolor: 'rgba(32,178,170,0.3)',
    zerolinewidth: 1,
    tickcolor: '#4a6a7a',
    tickfont: { color: '#8aacb8', size: 11 },
    linecolor: 'rgba(32,178,170,0.2)',
  },
  yaxis: {
    gridcolor: 'rgba(32,178,170,0.1)',
    gridwidth: 1,
    zerolinecolor: 'rgba(32,178,170,0.3)',
    zerolinewidth: 1,
    tickcolor: '#4a6a7a',
    tickfont: { color: '#8aacb8', size: 11 },
    linecolor: 'rgba(32,178,170,0.2)',
  },
  legend: {
    bgcolor: 'rgba(8,14,28,0.85)',
    bordercolor: 'rgba(32,178,170,0.2)',
    borderwidth: 1,
    font: { color: '#c8d8e0', size: 11 },
  },
  hoverlabel: {
    bgcolor: '#0f1f36',
    bordercolor: 'rgba(32,178,170,0.4)',
    font: { color: '#e8f4f8', size: 12 },
  },
};

export const plotConfig = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'],
  toImageButtonOptions: { format: 'png', scale: 2 },
};

export function PlotFrame({ title, subtitle, tools, children, className }: {
  title: string;
  subtitle?: string;
  tools?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`nav-plot-frame ${className || ''}`}>
      <div className="nav-plot-header">
        <div className="nav-plot-title-group">
          <div className="nav-plot-title">{title}</div>
          {subtitle && <div className="nav-plot-subtitle">{subtitle}</div>}
        </div>
        {tools && <div className="nav-plot-tools">{tools}</div>}
      </div>
      <div className="nav-plot-body">
        {children}
      </div>
    </section>
  );
}
