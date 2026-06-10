import { useEffect, useMemo, useState } from 'react';
import {
  Database, FileSearch, Maximize2, PlayCircle, X,
  Map, Boxes, GitCompareArrows, Table2, LineChart,
  Download, Route, BarChart2, Layers, RefreshCw
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

function EmptyTrajectoryState({ onAutoImport, onSeedDemo, busy }: {
  onAutoImport: () => void;
  onSeedDemo: () => void;
  busy: boolean;
}) {
  return (
    <div className="nav-empty-state">
      <div className="nav-empty-icon">
        <Route size={48} />
      </div>
      <div className="nav-empty-title">Нет данных инклинометрии</div>
      <div className="nav-empty-sub">
        Загрузите инклинометрические данные или запустите demo-режим для просмотра всех функций модуля.
      </div>
      <div className="nav-empty-schema">
        <div className="nav-schema-label">Ожидаемый формат:</div>
        <pre>{`Глубина по стволу | Зенит (°) | Азимут (°)\n0                 | 0         | 0\n100               | 0         | 0\n200               | 10        | 90`}</pre>
      </div>
      <div className="nav-empty-actions">
        <button type="button" className="nav-btn-primary" onClick={onSeedDemo} disabled={busy}>
          <PlayCircle size={16} />
          <span>Загрузить Demo данные</span>
        </button>
        <button type="button" className="nav-btn-secondary" onClick={onAutoImport} disabled={busy}>
          <FileSearch size={16} />
          <span>Автоимпорт из документов</span>
        </button>
      </div>
    </div>
  );
}

function TabButton({ action, label, icon, active, onClick }: {
  action: string; label: string; icon: React.ReactNode;
  active: boolean; onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`nav-tab-btn ${active ? 'active' : ''}`}
      onClick={onClick}
      title={label}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

export function TrajectoryWorkspace() {
  const [tree, setTree] = useState<TrajectoryTreeResponse | null>(null);
  const [selected, setSelected] = useState<TreeNode | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busyImport, setBusyImport] = useState(false);

  const loadTree = async () => {
    setError('');
    try {
      const next = await trajectoryJson<TrajectoryTreeResponse>('/trajectory/tree');
      setTree(next);
      setSelected(current => current || findFirstView(next.nodes));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Trajectory API недоступен');
    }
  };

  const runTrajectoryAction = async (kind: 'documents' | 'demo') => {
    setError('');
    setNotice('');
    setBusyImport(true);
    try {
      const result = kind === 'demo'
        ? await trajectoryPostJson<AutoImportTrajectoryResponse>('/trajectory/seed-demo')
        : await trajectoryPostJson<AutoImportTrajectoryResponse>('/trajectory/import-from-documents', { approved: false });
      const parts = [
        kind === 'demo' ? 'Demo trajectory данные добавлены.' : 'Автоимпорт из документов выполнен.',
        `Survey: ${result.survey_imported}`,
        `Design: ${result.design_imported}`,
        ...(result.warnings || []),
      ];
      setNotice(parts.filter(Boolean).join(' '));
      setSelected(null);
      await loadTree();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось выполнить импорт trajectory данных');
    } finally {
      setBusyImport(false);
    }
  };

  useEffect(() => { void loadTree(); }, []);

  const action = selected?.action as TrajectoryAction | undefined;
  const projectId = selected?.meta?.project_id || tree?.project_id || undefined;
  const wellId = selected?.meta?.well_id;
  const wellName = selected?.meta?.well_name || selected?.label;

  // Quick-access tabs for the active well/project
  const hasData = Boolean(tree?.nodes?.length);
  const activeWellId = wellId || (selected?.meta?.well_id);
  const activeProjectId = projectId;

  const selectAction = (act: TrajectoryAction) => {
    if (!tree?.nodes) return;
    // find node with this action
    const findNode = (nodes: TreeNode[]): TreeNode | null => {
      for (const n of nodes) {
        if (n.action === act) return n;
        const c = findNode(n.children || []);
        if (c) return c;
      }
      return null;
    };
    const node = findNode(tree.nodes);
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
  }, [action, selected, projectId, wellId, wellName, fullscreen, tree, busyImport]);

  const selectNode = (node: TreeNode) => {
    setSelected(node);
    if (node.action === 'project-plan' || node.action === 'well-profile') setFullscreen(false);
    else setFullscreen(false);
  };

  // Determine active tab label for topbar
  const tabLabels: Record<string, string> = {
    'project-plan': 'Карта проекта',
    'project-3d': '3D группы скважин',
    'project-separation': 'Сближение скважин',
    'well-data': 'Данные / Инклинометрия',
    'well-plan': 'План',
    'well-profile': 'Профиль',
    'well-3d': '3D скважины',
    'well-design': 'Проектный профиль',
    'well-deviation': 'Отклонение от проекта',
    'well-forecast': 'Прогноз',
    'well-excel': 'Отчёт в Excel',
  };

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
          <TrajectoryNavigator nodes={tree?.nodes || []} activeId={selected?.id} onSelect={selectNode} />
        </div>

        <div className="nav-sidebar-actions">
          <button type="button" className="nav-sidebar-btn" onClick={loadTree} title="Обновить дерево">
            <RefreshCw size={14} />
            <span>Обновить</span>
          </button>
          <button type="button" className="nav-sidebar-btn" onClick={() => void runTrajectoryAction('demo')} disabled={busyImport} title="Загрузить demo данные">
            <PlayCircle size={14} />
            <span>Demo данные</span>
          </button>
          <button type="button" className="nav-sidebar-btn" onClick={() => void runTrajectoryAction('documents')} disabled={busyImport} title="Автоимпорт из документов">
            <FileSearch size={14} />
            <span>Из документов</span>
          </button>
        </div>

        {notice ? <div className="nav-notice">{notice}</div> : null}
        {tree?.warnings?.length ? <div className="nav-warn">{tree.warnings.join(' · ')}</div> : null}
        {error ? <div className="nav-error">{error}</div> : null}
      </aside>

      {/* Main content */}
      <div className="nav-main">
        {/* Top bar with well selector + quick tabs */}
        <div className="nav-topbar">
          <div className="nav-topbar-left">
            <div className="nav-well-label">Скважина:</div>
            <div className="nav-well-name">{wellName || selected?.label || '—'}</div>
            {action && <div className="nav-view-badge">{tabLabels[action] || action}</div>}
          </div>

          <div className="nav-quick-tabs">
            {activeProjectId && (
              <>
                <TabButton action="project-plan" label="Карта" icon={<Map size={14} />} active={action === 'project-plan'} onClick={() => selectAction('project-plan')} />
                <TabButton action="project-3d" label="3D куст" icon={<Boxes size={14} />} active={action === 'project-3d'} onClick={() => selectAction('project-3d')} />
                <TabButton action="project-separation" label="Сближение" icon={<GitCompareArrows size={14} />} active={action === 'project-separation'} onClick={() => selectAction('project-separation')} />
                <div className="nav-tab-divider" />
              </>
            )}
            {activeWellId && (
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

        {/* Main plot / content area */}
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
              <X size={16} />
              <span>Закрыть</span>
            </button>
          </div>
          <div className="nav-fullscreen-content">{content}</div>
        </div>
      )}
    </div>
  );
}
