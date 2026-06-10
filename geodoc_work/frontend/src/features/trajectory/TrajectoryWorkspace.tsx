import { useEffect, useMemo, useState } from 'react';
import {
  Database, FileSearch, Maximize2, PlayCircle, X,
  Map, Boxes, GitCompareArrows, Table2, LineChart,
  Download, Route, BarChart2, RefreshCw
} from 'lucide-react';
import { trajectoryJson, trajectoryPostJson } from './api';
import { DeviationView } from './DeviationView';
import { DesignView } from './DesignView';
import { ExportReportButton } from './ExportReportButton';
import { ForecastPanel } from './ForecastPanel';
import { PlanView } from './PlanView';
import { ProfileView } from './ProfileView';
import { SeparationView } from './SeparationView';
import { ThreeDView } from './ThreeDView';
import { TrajectoryDataGrid } from './TrajectoryDataGrid';
import { TrajectoryNavigator } from './TrajectoryNavigator';
import type { AutoImportTrajectoryResponse, TrajectoryAction, TrajectoryTreeResponse, TreeNode } from './types';

function findFirstView(nodes: TreeNode[]): TreeNode | null {
  for (const node of nodes) {
    if (node.type === 'view') return node;
    const child = findFirstView(node.children || []);
    if (child) return child;
  }
  return null;
}

function findNodeByWell(nodes: TreeNode[], wellId: string, action: TrajectoryAction): TreeNode | null {
  for (const node of nodes) {
    if (node.action === action && node.meta?.well_id === wellId) return node;
    const found = findNodeByWell(node.children || [], wellId, action);
    if (found) return found;
  }
  return null;
}

function findNodeByProject(nodes: TreeNode[], projectId: string, action: TrajectoryAction): TreeNode | null {
  for (const node of nodes) {
    if (node.action === action && node.meta?.project_id === projectId) return node;
    const found = findNodeByProject(node.children || [], projectId, action);
    if (found) return found;
  }
  return null;
}

function findNodeByAction(nodes: TreeNode[], action: TrajectoryAction): TreeNode | null {
  for (const node of nodes) {
    if (node.action === action) return node;
    const found = findNodeByAction(node.children || [], action);
    if (found) return found;
  }
  return null;
}

function EmptyTrajectoryState({ onAutoImport, onSeedDemo, busy }: {
  onAutoImport: () => void; onSeedDemo: () => void; busy: boolean;
}) {
  return (
    <div className="nav-empty-state">
      <div className="nav-empty-icon"><Route size={48} /></div>
      <div className="nav-empty-title">Нет данных инклинометрии</div>
      <div className="nav-empty-sub">
        Загрузите файл с данными скважины или запустите demo-режим.
      </div>
      <div className="nav-empty-schema">
        <div className="nav-schema-label">Формат Excel для импорта:</div>
        <pre>{`MD    | Inc  | Azi\n0     | 0    | 0\n100   | 0    | 0\n200   | 10   | 90`}</pre>
      </div>
      <div className="nav-empty-actions">
        <button type="button" className="nav-btn-primary" onClick={onSeedDemo} disabled={busy}>
          <PlayCircle size={16} /><span>Demo данные</span>
        </button>
        <button type="button" className="nav-btn-secondary" onClick={onAutoImport} disabled={busy}>
          <FileSearch size={16} /><span>Из загруженных документов</span>
        </button>
      </div>
    </div>
  );
}

function TabButton({ action, label, icon, active, onClick }: {
  action: string; label: string; icon: React.ReactNode; active: boolean; onClick: () => void;
}) {
  return (
    <button type="button" className={`nav-tab-btn ${active ? 'active' : ''}`} onClick={onClick} title={label}>
      {icon}<span>{label}</span>
    </button>
  );
}

const TAB_LABELS: Record<string, string> = {
  'project-plan': 'Карта проекта', 'project-3d': '3D группы', 'project-separation': 'Сближение',
  'well-data': 'Инклинометрия', 'well-plan': 'План', 'well-profile': 'Профиль',
  'well-3d': '3D', 'well-design': 'Проект', 'well-deviation': 'Отклонение',
  'well-forecast': 'Прогноз', 'well-excel': 'Excel',
};

export function TrajectoryWorkspace() {
  const [tree, setTree] = useState<TrajectoryTreeResponse | null>(null);
  const [selected, setSelected] = useState<TreeNode | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busyImport, setBusyImport] = useState(false);

  const loadTree = async (): Promise<TrajectoryTreeResponse | null> => {
    setError('');
    try {
      const next = await trajectoryJson<TrajectoryTreeResponse>('/trajectory/tree');
      setTree(next);
      return next;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Trajectory API недоступен');
      return null;
    }
  };

  const runTrajectoryAction = async (kind: 'documents' | 'demo') => {
    setError(''); setNotice(''); setBusyImport(true);
    try {
      const result = kind === 'demo'
        ? await trajectoryPostJson<AutoImportTrajectoryResponse>('/trajectory/seed-demo')
        : await trajectoryPostJson<AutoImportTrajectoryResponse>('/trajectory/import-from-documents', { approved: true });

      const parts = [
        kind === 'demo' ? 'Demo данные загружены.' : 'Импорт выполнен.',
        result.survey_imported > 0 ? `Инклинометрия: ${result.survey_imported} станций.` : '',
        result.design_imported > 0 ? `Проект: ${result.design_imported} сегментов.` : '',
        ...(result.warnings?.slice(0, 2) || []),
      ].filter(Boolean);
      setNotice(parts.join(' '));

      // Reload tree and navigate to the newly created well
      const newTree = await loadTree();
      if (newTree && result.well_id) {
        const wellPlanNode = findNodeByWell(newTree.nodes, result.well_id, 'well-plan');
        if (wellPlanNode) { setSelected(wellPlanNode); setFullscreen(false); return; }
      }
      if (newTree && result.project_id) {
        const projectPlan = findNodeByProject(newTree.nodes, result.project_id, 'project-plan');
        if (projectPlan) { setSelected(projectPlan); setFullscreen(false); return; }
      }
      if (newTree) {
        const first = findFirstView(newTree.nodes);
        if (first) setSelected(first);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось выполнить импорт');
    } finally { setBusyImport(false); }
  };

  useEffect(() => {
    loadTree().then(t => {
      if (t && !selected) setSelected(findFirstView(t.nodes));
    });
  }, []);

  const action = selected?.action as TrajectoryAction | undefined;
  const projectId = selected?.meta?.project_id || tree?.project_id || undefined;
  const wellId = selected?.meta?.well_id;
  const wellName = selected?.meta?.well_name || selected?.label;

  // Track active well/project context separately — survives project-level tab clicks
  const [activeWellId, setActiveWellId] = useState<string | undefined>();
  const [activeProjectId, setActiveProjectId] = useState<string | undefined>();

  useEffect(() => {
    if (wellId) setActiveWellId(wellId);
    if (projectId) setActiveProjectId(projectId);
  }, [wellId, projectId]);

  const selectAction = (act: TrajectoryAction) => {
    if (!tree?.nodes) return;
    // Try current well first, then current project, then first match
    const wid = wellId || activeWellId;
    const pid = projectId || activeProjectId;
    let node: TreeNode | null = null;
    if (wid) node = findNodeByWell(tree.nodes, wid, act);
    if (!node && pid) node = findNodeByProject(tree.nodes, pid, act);
    // Never fall back to findNodeByAction — that would pick demo data
    if (node) setSelected(node);
  };

  const content = useMemo(() => {
    if (!selected || !action) return (
      <EmptyTrajectoryState
        onAutoImport={() => void runTrajectoryAction('documents')}
        onSeedDemo={() => void runTrajectoryAction('demo')}
        busy={busyImport}
      />
    );
    if (action === 'project-plan' && projectId) return <PlanView projectId={projectId} fullscreen={fullscreen} onFullscreen={() => setFullscreen(true)} />;
    if (action === 'project-3d' && projectId) return <ThreeDView projectId={projectId} />;
    if (action === 'project-separation' && projectId) return <SeparationView projectId={projectId} />;
    if (action === 'well-data' && wellId) return <TrajectoryDataGrid wellId={wellId} projectId={projectId} wellName={wellName} />;
    if (action === 'well-plan' && wellId) return <PlanView wellId={wellId} fullscreen={fullscreen} onFullscreen={() => setFullscreen(true)} />;
    if (action === 'well-profile' && wellId) return <ProfileView wellId={wellId} fullscreen={fullscreen} onFullscreen={() => setFullscreen(true)} />;
    if (action === 'well-3d' && wellId) return <ThreeDView wellId={wellId} />;
    if (action === 'well-design' && wellId) return <DesignView wellId={wellId} />;
    if (action === 'well-deviation' && wellId) return <DeviationView wellId={wellId} />;
    if (action === 'well-forecast' && wellId) return <ForecastPanel wellId={wellId} />;
    if (action === 'well-excel' && wellId) return <ExportReportButton wellId={wellId} wellName={wellName} />;
    return (
      <EmptyTrajectoryState
        onAutoImport={() => void runTrajectoryAction('documents')}
        onSeedDemo={() => void runTrajectoryAction('demo')}
        busy={busyImport}
      />
    );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [action, selected, projectId, wellId, wellName, fullscreen, busyImport]);

  // Show well tabs if we have an active well in context
  const showWellTabs = !!(wellId || activeWellId);
  const showProjectTabs = !!(projectId || activeProjectId);
  const hasData = Boolean(tree?.nodes?.length);

  return (
    <div className="nav-workspace">
      {/* Left sidebar */}
      <aside className="nav-sidebar">
        <div className="nav-sidebar-header">
          <div className="nav-sidebar-brand">
            <Route size={18} className="nav-brand-icon" />
            <div>
              <div className="nav-brand-title">GeoDoc</div>
              <div className="nav-brand-sub">Навигатор траекторий</div>
            </div>
          </div>
        </div>

        <div className="nav-sidebar-section-label">Структура проекта</div>
        <div className="nav-sidebar-tree">
          <TrajectoryNavigator nodes={tree?.nodes || []} activeId={selected?.id} onSelect={setSelected} />
        </div>

        <div className="nav-sidebar-actions">
          <button type="button" className="nav-sidebar-btn" onClick={() => void loadTree()} title="Обновить дерево">
            <RefreshCw size={14} /><span>Обновить</span>
          </button>
          <button type="button" className="nav-sidebar-btn" onClick={() => void runTrajectoryAction('demo')} disabled={busyImport}>
            <PlayCircle size={14} /><span>Demo данные</span>
          </button>
          <button type="button" className="nav-sidebar-btn" onClick={() => void runTrajectoryAction('documents')} disabled={busyImport}>
            <FileSearch size={14} /><span>Из документов</span>
          </button>
        </div>

        {notice ? <div className="nav-notice">{notice}</div> : null}
        {tree?.warnings?.length ? <div className="nav-warn">{tree.warnings.join(' · ')}</div> : null}
        {error ? <div className="nav-error">{error}</div> : null}
      </aside>

      {/* Main content */}
      <div className="nav-main">
        {/* Top bar */}
        <div className="nav-topbar">
          <div className="nav-topbar-left">
            <div className="nav-well-label">Скважина:</div>
            <div className="nav-well-name">{wellName || selected?.label || '—'}</div>
            {action && <div className="nav-view-badge">{TAB_LABELS[action] || action}</div>}
          </div>

          <div className="nav-quick-tabs">
            {showProjectTabs && (
              <>
                <TabButton action="project-plan" label="Карта" icon={<Map size={14} />} active={action === 'project-plan'} onClick={() => selectAction('project-plan')} />
                <TabButton action="project-3d" label="3D куст" icon={<Boxes size={14} />} active={action === 'project-3d'} onClick={() => selectAction('project-3d')} />
                <TabButton action="project-separation" label="Сближение" icon={<GitCompareArrows size={14} />} active={action === 'project-separation'} onClick={() => selectAction('project-separation')} />
                <div className="nav-tab-divider" />
              </>
            )}
            {showWellTabs && (
              <>
                <TabButton action="well-data" label="Данные" icon={<Table2 size={14} />} active={action === 'well-data'} onClick={() => selectAction('well-data')} />
                <TabButton action="well-plan" label="План" icon={<Map size={14} />} active={action === 'well-plan'} onClick={() => selectAction('well-plan')} />
                <TabButton action="well-profile" label="Профиль" icon={<LineChart size={14} />} active={action === 'well-profile'} onClick={() => selectAction('well-profile')} />
                <TabButton action="well-3d" label="3D" icon={<Boxes size={14} />} active={action === 'well-3d'} onClick={() => selectAction('well-3d')} />
                <TabButton action="well-deviation" label="Отклонение" icon={<GitCompareArrows size={14} />} active={action === 'well-deviation'} onClick={() => selectAction('well-deviation')} />
                <TabButton action="well-forecast" label="Прогноз" icon={<BarChart2 size={14} />} active={action === 'well-forecast'} onClick={() => selectAction('well-forecast')} />
                <TabButton action="well-excel" label="Excel" icon={<Download size={14} />} active={action === 'well-excel'} onClick={() => selectAction('well-excel')} />
              </>
            )}
          </div>

          <div className="nav-topbar-right">
            <button type="button" className="nav-icon-btn" onClick={() => setFullscreen(true)} title="Полный экран">
              <Maximize2 size={15} />
            </button>
          </div>
        </div>

        {/* Canvas */}
        <div className="nav-canvas">
          {hasData ? content : (
            <EmptyTrajectoryState
              onAutoImport={() => void runTrajectoryAction('documents')}
              onSeedDemo={() => void runTrajectoryAction('demo')}
              busy={busyImport}
            />
          )}
        </div>
      </div>

      {/* Fullscreen overlay */}
      {fullscreen && (
        <div className="nav-fullscreen">
          <div className="nav-fullscreen-bar">
            <div className="nav-well-name">{wellName || '—'}</div>
            <button type="button" className="nav-icon-btn" onClick={() => setFullscreen(false)}>
              <X size={16} /><span>Закрыть</span>
            </button>
          </div>
          <div className="nav-fullscreen-content">{content}</div>
        </div>
      )}
    </div>
  );
}
