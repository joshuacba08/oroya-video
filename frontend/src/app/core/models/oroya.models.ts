export type ProjectTone = 'violet' | 'green' | 'rose' | 'blue' | 'empty';
export type JobStatusTone = 'success' | 'processing' | 'warning' | 'danger' | 'neutral';
export type BackendState = 'checking' | 'api' | 'mock' | 'offline' | 'wrong-backend';

export interface ApiErrorVm {
  code: string;
  message: string;
  status?: number;
  requestId?: string;
  details?: Record<string, unknown>;
}

export interface BackendStatusVm {
  state: BackendState;
  isApi: boolean;
  isMock: boolean;
  isOffline: boolean;
  wrongBackend: boolean;
  service?: string;
  version?: string | null;
  message: string;
  warnings: string[];
  error?: ApiErrorVm;
}

export interface StartupVm {
  backend: BackendStatusVm;
  ready: boolean;
  appName: string;
  appVersion: string;
  queueCount: number;
  interruptedCount: number;
  warnings: string[];
  ffmpegAvailable: boolean;
  modelsInstalled: number;
  aiRuntimeAvailable: boolean;
}

export interface ProjectCardVm {
  id: string;
  videoAssetId?: string;
  latestJobId?: string;
  latestExportId?: string;
  name: string;
  model: string;
  duration: string;
  resolution: string;
  status: string;
  statusTone: JobStatusTone;
  updatedLabel: string;
  thumbnailTone: ProjectTone;
  progress?: number;
}

export interface SystemStatusVm {
  gpuName: string;
  gpuUsage: number;
  vramUsedGb: number;
  vramTotalGb: number;
  ready: boolean;
  warnings: string[];
}

export interface DashboardVm {
  subtitle: string;
  recentProjects: ProjectCardVm[];
  queueCount: number;
  activeJobs: QueueJobVm[];
  installedModels: ModelVm[];
  /** Modelos registrados que aún no están descargados. */
  availableModelsCount: number;
  system: SystemStatusVm;
  source: 'api' | 'mock';
}

export interface PipelineStepVm {
  id: string;
  title: string;
  description?: string;
  icon: string;
  status: 'success' | 'running' | 'pending' | 'error';
  progress?: number;
}

export interface QueueJobVm {
  id: string;
  projectId: string;
  projectName: string;
  status: string;
  statusTone: JobStatusTone;
  stage: string;
  progress: number;
  model: string;
  resolution: string;
  duration: string;
  framesLabel: string;
  pipeline: PipelineStepVm[];
  canStart: boolean;
  canCancel: boolean;
  canPause: boolean;
  canRetry: boolean;
  canCleanup: boolean;
  previewAvailable: boolean;
  exportAvailable: boolean;
  errorMessage?: string;
  device?: string;
  avgFrameTimeMs?: number;
  failedFrames: number;
  etaLabel?: string;
  framesProcessed: number;
  framesTotal: number;
}

export interface PreviewFrameVm {
  index: number;
  fileName: string;
  originalUrl?: string;
  enhancedUrl?: string;
  originalAvailable: boolean;
  enhancedAvailable: boolean;
}

export interface ModelVm {
  id: string;
  slug: string;
  name: string;
  version: string;
  description: string;
  installed: boolean;
  enabled: boolean;
  /** Tiers del backend (`metadata.quality_tier` / `speed_tier`), o '' si no se declaran. */
  qualityTier: string;
  speedTier: string;
  quality: number;
  speed: number;
  vramGb: number;
  category: string;
}

export interface ModelDownloadVm {
  status: 'idle' | 'downloading' | 'completed' | 'failed';
  percent: number;
  bytesDone: number;
  bytesTotal?: number;
  errorMessage?: string;
}

export interface ExportVm {
  id: string;
  projectId: string;
  jobId: string;
  fileName: string;
  filePath: string;
  dateLabel: string;
  resolution: string;
  codec: string;
  fpsLabel?: string;
  outputFolder?: string;
  sizeLabel: string;
  duration: string;
  canOpen?: boolean;
  mediaUrl?: string;
}

export interface ExportsPageVm {
  featured: ExportVm;
  history: ExportVm[];
}

export interface SettingsVm {
  language: string;
  theme: string;
  gpuName: string;
  frameEnhancerEngine: string;
  aiDevice: string;
  aiAllowCpu: boolean;
  aiHalfPrecision: boolean;
  realesrganTileSize: number;
  realesrganTilePad: number;
  realesrganPrePad: number;
  vramLimitGb: number;
  tempPath: string;
  modelsPath: string;
  exportsPath: string;
  autoSavePreviews: boolean;
  cleanupTempOnSuccess: boolean;
  cleanupKeepPreviewFrames: number;
  cleanupOlderThanHours: number;
}

export interface WorkspaceVm {
  project: ProjectCardVm;
  videoAssetId: string;
  latestJobId?: string;
  latestJobStatus?: string;
  latestExportId?: string;
  selectedModel: ModelVm;
  alternateModels: ModelVm[];
  denoise: number;
  sharpen: number;
  compressionCleanup: boolean;
  scale: 'original' | '2x' | '4x';
  exportResolution: 'original' | '2x' | '4x';
  keepAudio: boolean;
  compareMode: 'slider' | 'side_by_side';
  zoom: 'fit' | '100%';
  videoFps: number;
  previewTotalFrames: number;
  estimateTime: string;
  outputSize: string;
  previewBefore: string;
  previewAfter: string;
  timelineFrames: ProjectTone[];
  pipeline: PipelineStepVm[];
  actions: Record<string, boolean>;
  videoInfo: { label: string; value: string }[];
}

export type PickedVideo =
  | { kind: 'tauri'; path: string }
  | { kind: 'browser-path'; path: string };
