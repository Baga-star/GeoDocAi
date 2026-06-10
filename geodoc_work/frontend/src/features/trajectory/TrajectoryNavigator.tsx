import { ChevronDown, ChevronRight, Map, Boxes, GitCompareArrows, Table2, LineChart, Download, Route, BarChart2, Layers } from 'lucide-react';
import { useState } from 'react';
import type { TreeNode } from './types';

function iconFor(action?: string | null) {
  if (action === 'project-plan' || action === 'well-plan') return <Map size={14} />;
  if (action?.includes('3d')) return <Boxes size={14} />;
  if (action?.includes('separation')) return <GitCompareArrows size={14} />;
  if (action?.includes('deviation')) return <GitCompareArrows size={14} />;
  if (action?.includes('data')) return <Table2 size={14} />;
  if (action?.includes('excel')) return <Download size={14} />;
  if (action?.includes('profile') || action?.includes('design')) return <LineChart size={14} />;
  if (action?.includes('forecast')) return <BarChart2 size={14} />;
  if (action?.includes('well')) return <Route size={14} />;
  return <Layers size={14} />;
}

function actionLabel(action?: string | null): string {
  const labels: Record<string, string> = {
    'project-plan': 'Карта проекта',
    'project-3d': '3D группы',
    'project-separation': 'Сближение',
    'well-data': 'Инклинометрия',
    'well-plan': 'План',
    'well-profile': 'Профиль',
    'well-3d': '3D',
    'well-design': 'Проект',
    'well-deviation': 'Отклонение',
    'well-forecast': 'Прогноз',
    'well-excel': 'Excel-отчёт',
  };
  return action ? (labels[action] || action) : '';
}

function NodeView({ node, activeId, onSelect, level = 0 }: {
  node: TreeNode; activeId?: string; onSelect: (node: TreeNode) => void; level?: number;
}) {
  const [open, setOpen] = useState(true);
  const hasChildren = Boolean(node.children?.length);
  const isView = node.type === 'view';
  const isActive = activeId === node.id;

  const displayLabel = isView ? actionLabel(node.action) || node.label : node.label;

  return (
    <div className="nav-tree-node">
      <button
        type="button"
        className={`nav-tree-btn ${isActive ? 'active' : ''} ${isView ? 'view' : 'group'} depth-${level}`}
        style={{ paddingLeft: 12 + level * 14 }}
        onClick={() => (isView ? onSelect(node) : setOpen(v => !v))}
      >
        <span className="nav-tree-chevron">
          {hasChildren
            ? (open ? <ChevronDown size={12} /> : <ChevronRight size={12} />)
            : <span style={{ width: 12 }} />}
        </span>
        <span className="nav-tree-icon">{iconFor(node.action)}</span>
        <span className="nav-tree-label">{displayLabel}</span>
        {isActive && <span className="nav-tree-active-dot" />}
      </button>
      {open && hasChildren && node.children?.map(child => (
        <NodeView key={child.id} node={child} activeId={activeId} onSelect={onSelect} level={level + 1} />
      ))}
    </div>
  );
}

export function TrajectoryNavigator({ nodes, activeId, onSelect }: {
  nodes: TreeNode[];
  activeId?: string;
  onSelect: (node: TreeNode) => void;
}) {
  if (!nodes.length) {
    return (
      <div className="nav-tree-empty">
        <Route size={24} />
        <p>Нет данных.<br />Загрузите инклинометрию или запустите Demo.</p>
      </div>
    );
  }
  return (
    <nav className="nav-tree">
      {nodes.map(node => (
        <NodeView key={node.id} node={node} activeId={activeId} onSelect={onSelect} />
      ))}
    </nav>
  );
}
