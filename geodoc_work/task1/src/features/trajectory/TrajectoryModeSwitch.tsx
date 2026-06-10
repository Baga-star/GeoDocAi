import { FileText, Route } from 'lucide-react';
import type { AppMode } from './types';

export function TrajectoryModeSwitch({ mode, onChange }: { mode: AppMode; onChange: (mode: AppMode) => void }) {
  return (
    <div className="traj-switch" aria-label="Режим GeoDoc AI">
      <button type="button" className={mode === 'documents' ? 'active' : ''} onClick={() => onChange('documents')}>
        <FileText size={15} /> Документы
      </button>
      <button type="button" className={mode === 'trajectories' ? 'active' : ''} onClick={() => onChange('trajectories')}>
        <Route size={15} /> Траектории
      </button>
    </div>
  );
}
