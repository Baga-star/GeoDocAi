export type AppMode = 'documents' | 'trajectories';
export type TrajectoryStatus = 'ok' | 'warning' | 'invalid' | 'needs_approval' | 'needs_domain_rules';
export type TrajectoryAction =
  | 'project-plan'
  | 'project-3d'
  | 'project-separation'
  | 'well-data'
  | 'well-plan'
  | 'well-profile'
  | 'well-3d'
  | 'well-design'
  | 'well-deviation'
  | 'well-forecast'
  | 'well-excel';

export type SourceProvenance = {
  document_id?: string | null;
  document_name?: string | null;
  page?: number | null;
  artifact_id?: string | null;
  table_title?: string | null;
  row_index?: number | null;
  raw?: Record<string, unknown>;
};

export type TrajectoryPoint = {
  md: number;
  inc: number;
  azi: number;
  tvd: number;
  northing: number;
  easting: number;
  vertical_section?: number | null;
  layer: 'actual' | 'design' | 'forecast';
  provenance?: SourceProvenance | null;
};

export type TreeNode = {
  id: string;
  label: string;
  type: 'project' | 'group' | 'well' | 'view';
  action?: TrajectoryAction | null;
  children?: TreeNode[];
  meta?: Record<string, string>;
};

export type TrajectoryTreeResponse = {
  status: TrajectoryStatus;
  project_id?: string | null;
  nodes: TreeNode[];
  warnings: string[];
};

export type TrajectorySeriesResponse = {
  status: TrajectoryStatus;
  project_id?: string | null;
  well_id?: string | null;
  series: TrajectoryPoint[];
  warnings: string[];
};

export type ProjectSeries = {
  well_id: string;
  well_name: string;
  layer: 'actual' | 'design' | 'forecast';
  points: TrajectoryPoint[];
};

export type ProjectTrajectoryResponse = {
  status: TrajectoryStatus;
  project_id: string;
  series: ProjectSeries[];
  warnings: string[];
};

export type SurveyStation = {
  md: number;
  inc: number;
  azi: number;
  magnetic_declination?: number | null;
  approved: boolean;
  provenance?: SourceProvenance | null;
};

export type DesignSegment = {
  start_md?: number | null;
  end_md?: number | null;
  length?: number | null;
  start_inc?: number | null;
  end_inc?: number | null;
  start_azi?: number | null;
  end_azi?: number | null;
  tolerance_m?: number | null;
  circle_radius_m?: number | null;
  approved: boolean;
  provenance?: SourceProvenance | null;
};

export type SurveyDataResponse = {
  status: TrajectoryStatus;
  well_id: string;
  stations: SurveyStation[];
  segments: DesignSegment[];
  validation: { status: TrajectoryStatus; warnings: string[]; errors: string[] };
};

export type DeviationRow = {
  md: number;
  tvd: number;
  northing: number;
  easting: number;
  nearest_design_md?: number | null;
  distance_m?: number | null;
  delta_tvd?: number | null;
  delta_northing?: number | null;
  delta_easting?: number | null;
};

export type DeviationResponse = {
  status: TrajectoryStatus;
  well_id: string;
  rows: DeviationRow[];
  max_distance_m?: number | null;
  warnings: string[];
};

export type SeparationRow = {
  well_a_id: string;
  well_a_name: string;
  well_b_id: string;
  well_b_name: string;
  min_distance_m?: number | null;
  md_a?: number | null;
  md_b?: number | null;
  method: string;
};

export type SeparationResponse = {
  status: TrajectoryStatus;
  project_id: string;
  rows: SeparationRow[];
  warnings: string[];
};

export type ForecastResponse = {
  status: TrajectoryStatus;
  well_id: string;
  series: TrajectoryPoint[];
  warnings: string[];
};


export type AutoImportTrajectoryResponse = {
  status: TrajectoryStatus;
  project_id?: string | null;
  well_id?: string | null;
  survey_imported: number;
  design_imported: number;
  validation: { status: TrajectoryStatus; warnings: string[]; errors: string[] };
  warnings: string[];
};
