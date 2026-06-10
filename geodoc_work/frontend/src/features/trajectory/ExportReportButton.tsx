import { Download, FileSpreadsheet, CheckCircle, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import { trajectoryBlob } from './api';

type Status = 'idle' | 'loading' | 'done' | 'error';

const REPORT_SECTIONS = [
  { label: 'Исходные данные инклинометрии', desc: 'MD, зенит, азимут — все станции замера' },
  { label: 'Рассчитанные координаты', desc: 'TVD, север, восток, отход, вертикальная секция' },
  { label: 'Данные плана', desc: 'Горизонтальная проекция — координаты карты куста' },
  { label: 'Профиль (вертикальная проекция)', desc: 'Вертикальная секция + TVD' },
  { label: 'Проектный профиль', desc: 'Параметры проектных участков и сегменты' },
  { label: 'Отклонение от проекта', desc: 'Мин. расстояния, ΔTVD, ΔСевер, ΔВосток' },
  { label: 'Сближение скважин', desc: 'Мин. расстояния между скважинами группы' },
  { label: 'Качество данных', desc: 'Источники, аномалии, статус проверки' },
];

export function ExportReportButton({ wellId, wellName }: { wellId: string; wellName?: string }) {
  const [status, setStatus] = useState<Status>('idle');
  const [message, setMessage] = useState('');

  const download = async () => {
    setStatus('loading'); setMessage('Формирование Excel-отчёта…');
    try {
      const blob = await trajectoryBlob(`/trajectory/well/${wellId}/report.xlsx`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trajectory_${(wellName || wellId).replace(/\s+/g, '_')}.xlsx`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      setStatus('done'); setMessage('Отчёт успешно скачан');
      setTimeout(() => { setStatus('idle'); setMessage(''); }, 4000);
    } catch (err) {
      setStatus('error'); setMessage(err instanceof Error ? err.message : 'Ошибка при формировании Excel');
    }
  };

  return (
    <div className="nav-excel-panel">
      <div className="nav-excel-title">
        <FileSpreadsheet size={22} style={{ color: '#4ade80' }} />
        <div>
          <strong>Отчёт в Excel</strong>
          <span>Скважина: {wellName || wellId}</span>
        </div>
      </div>

      <div className="nav-excel-contents">
        <div className="nav-excel-sections-label">Содержание отчёта:</div>
        <div className="nav-excel-list">
          {REPORT_SECTIONS.map(s => (
            <div key={s.label} className="nav-excel-item">
              <strong>{s.label}</strong>
              <span>{s.desc}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="nav-excel-actions">
        <button
          className="nav-excel-download-btn"
          type="button"
          onClick={download}
          disabled={status === 'loading'}
        >
          <Download size={16} />
          {status === 'loading' ? 'Формирование…' : 'Скачать Excel-отчёт'}
        </button>
        {status === 'done' && <div className="nav-excel-status ok"><CheckCircle size={15} />{message}</div>}
        {status === 'error' && <div className="nav-excel-status err"><AlertCircle size={15} />{message}</div>}
      </div>
    </div>
  );
}
