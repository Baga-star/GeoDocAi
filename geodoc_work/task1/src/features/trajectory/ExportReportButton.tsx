import { Download, FileSpreadsheet, CheckCircle2, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import { trajectoryBlob } from './api';

export function ExportReportButton({ wellId, wellName }: { wellId: string; wellName?: string }) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'error'>('idle');
  const [msg, setMsg] = useState('');

  const download = async () => {
    setStatus('loading');
    setMsg('');
    try {
      const blob = await trajectoryBlob(`/trajectory/well/${wellId}/report.xlsx`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trajectory_${(wellName || wellId).replace(/\s+/g, '_')}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setStatus('ok');
      setMsg('Отчёт Excel успешно скачан');
    } catch (err) {
      setStatus('error');
      setMsg(err instanceof Error ? err.message : 'Ошибка формирования отчёта');
    }
  };

  return (
    <div className="nav-excel-panel">
      <div className="nav-section-header">
        <FileSpreadsheet size={18} />
        <div>
          <div className="nav-section-title">Excel-отчёт по траектории</div>
          <div className="nav-section-sub">{wellName || wellId}</div>
        </div>
      </div>

      <div className="nav-excel-contents">
        <div className="nav-excel-title">Содержимое отчёта:</div>
        <ul className="nav-excel-list">
          <li>Исходные данные инклинометрии (MD, Зенит, Азимут)</li>
          <li>Расчётные координаты (Север, Восток, Вертикальная глубина, Отход)</li>
          <li>Данные плана и профиля</li>
          <li>Проектные параметры участков</li>
          <li>Отклонение от проектного профиля</li>
          <li>Анализ сближения скважин (если данные доступны)</li>
          <li>Источники данных и предупреждения</li>
        </ul>
      </div>

      <button
        type="button"
        className={`nav-excel-btn ${status === 'loading' ? 'loading' : ''}`}
        onClick={download}
        disabled={status === 'loading'}
      >
        <Download size={16} />
        {status === 'loading' ? 'Формирую отчёт...' : 'Скачать Excel-отчёт'}
      </button>

      {status === 'ok' && (
        <div className="nav-excel-status ok">
          <CheckCircle2 size={14} />
          <span>{msg}</span>
        </div>
      )}
      {status === 'error' && (
        <div className="nav-excel-status error">
          <AlertCircle size={14} />
          <span>{msg}</span>
        </div>
      )}
    </div>
  );
}
