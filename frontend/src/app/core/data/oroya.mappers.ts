import type {
  DashboardResponse,
  ExportListResponse,
  GPUResponse,
  JobControlResponse,
  JobDetailResponse,
  JobProgressResponse,
  ModelListResponse,
  ProjectDetailResponse,
  ProjectListResponse,
  ProjectWorkspaceResponse,
  QueueResponse,
  SettingsResponse,
} from '../api/api-types';
import type {
  DashboardVm,
  ExportVm,
  ExportsPageVm,
  JobStatusTone,
  ModelVm,
  PipelineStepVm,
  ProjectCardVm,
  ProjectTone,
  QueueJobVm,
  SettingsVm,
  SystemStatusVm,
  WorkspaceVm,
} from '../models/oroya.models';

type UnknownRecord = Record<string, unknown>;

const tones: ProjectTone[] = ['violet', 'green', 'rose', 'blue'];
const pipelineOrder = ['import', 'extract', 'enhance', 'encode', 'export'];
const pipelineTitles = ['Import', 'Extract', 'Enhance', 'Encode', 'Export'];
const pipelineIcons = ['upload', 'film', 'sparkles', 'box', 'download'];

function record(value: unknown): UnknownRecord {
  return value && typeof value === 'object' ? (value as UnknownRecord) : {};
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function numberValue(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function booleanValue(value: unknown, fallback = false): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function pickString(source: UnknownRecord, keys: string[], fallback = ''): string {
  for (const key of keys) {
    const value = stringValue(source[key]);
    if (value) {
      return value;
    }
  }

  return fallback;
}

function pickNumber(source: UnknownRecord, keys: string[], fallback = 0): number {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'number' && Number.isFinite(value)) {
      return value;
    }
  }

  return fallback;
}

/** Fechas del backend (UTC sin zona) a texto local legible. */
export function formatDateLabel(value: unknown, fallback = 'recent'): string {
  if (typeof value !== 'string' || !value) {
    return fallback;
  }
  const hasZone = /([zZ]|[+-]\d{2}:?\d{2})$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  const locale = typeof document !== 'undefined' ? document.documentElement.lang : '';
  return date.toLocaleString(locale || undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function formatSeconds(seconds: unknown, fallback = '--:--'): string {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds)) {
    return fallback;
  }

  const total = Math.max(Math.round(seconds), 0);
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

function formatBytes(bytes: unknown, fallback = '0 MB'): string {
  if (typeof bytes !== 'number' || !Number.isFinite(bytes)) {
    return fallback;
  }

  if (bytes >= 1024 ** 3) {
    return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  }

  return `${Math.max(bytes / 1024 ** 2, 0.1).toFixed(1)} MB`;
}

function parentPath(path: string): string {
  const normalized = path.replaceAll('\\', '/');
  const index = normalized.lastIndexOf('/');
  return index > 0 ? normalized.slice(0, index) : '';
}

function statusTone(status: string): JobStatusTone {
  const normalized = status.toLowerCase();

  if (normalized.includes('complete') || normalized.includes('ready') || normalized.includes('done')) {
    return 'success';
  }

  if (normalized.includes('fail') || normalized.includes('cancel') || normalized.includes('interrupt')) {
    return 'danger';
  }

  if (normalized.includes('queue') || normalized.includes('pending') || normalized.includes('wait')) {
    return 'warning';
  }

  if (normalized.includes('process') || normalized.includes('running') || normalized.includes('enhanc')) {
    return 'processing';
  }

  return 'neutral';
}

function stageToPipeline(stage: string, progress: number, status = ''): PipelineStepVm[] {
  const stageMap: Record<string, number> = {
    idle: 0,
    preflight: 0,
    queued: 0,
    extracting_frames: 1,
    enhancing_frames: 2,
    encoding_video: 3,
    muxing_audio: 3,
    exporting: 4,
    completed: 5,
    failed: 2,
    cancelled: 2,
    interrupted: 2,
  };
  const activeIndex = stageMap[stage] ?? (progress >= 100 ? 5 : 2);
  const failed = ['failed', 'cancelled', 'interrupted'].includes(status.toLowerCase());

  return pipelineOrder.map((id, index) => ({
    id,
    title: pipelineTitles[index],
    icon: pipelineIcons[index],
    status:
      failed && index === activeIndex
        ? 'error'
        : progress >= 100 || index < activeIndex
          ? 'success'
          : index === activeIndex
            ? 'running'
            : 'pending',
    progress: index === activeIndex ? progress : undefined,
  }));
}

function modelNameFromConfig(source: UnknownRecord): string {
  const config = record(source['enhancement_config']);
  return pickString(source, ['model', 'model_slug', 'ai_model_slug'], stringValue(config['model_id'], 'Real-ESRGAN x2'));
}

function resolutionFromConfig(source: UnknownRecord): string {
  const config = record(source['enhancement_config']);
  const exportConfig = record(source['export_config']);
  const scale = stringValue(config['scale'], stringValue(exportConfig['output_resolution'], '2x'));
  const label = scale === '4x' ? 'Original -> 4K' : scale === 'original' ? 'Original' : 'Original -> 2x';
  return pickString(source, ['resolution', 'resolution_label', 'target_resolution'], label);
}

export function mapUnknownProject(value: unknown, index = 0): ProjectCardVm {
  const item = record(value);
  const video = record(item['video']);
  const latestJob = record(item['latest_job']);
  const latestExport = record(item['latest_export']);
  const name = pickString(item, ['name', 'project_name', 'file_name', 'title'], stringValue(video['file_name'], `Project ${index + 1}`));
  const status = pickString(item, ['status', 'state'], stringValue(latestJob['status'], 'draft'));
  const progress = pickNumber(item, ['progress', 'progress_percent'], pickNumber(latestJob, ['progress_percent'], 0));

  return {
    id: pickString(item, ['id', 'project_id'], `project-${index}`),
    videoAssetId: pickString(item, ['video_asset_id'], stringValue(video['id'])) || undefined,
    latestJobId: stringValue(latestJob['id']) || undefined,
    latestExportId: stringValue(latestExport['id']) || undefined,
    name,
    model: modelNameFromConfig(item),
    duration: pickString(item, ['duration', 'duration_label'], stringValue(video['duration_label'], formatSeconds(video['duration_seconds']))),
    resolution: resolutionFromConfig(item),
    status,
    statusTone: statusTone(status),
    updatedLabel:
      stringValue(item['updated_label']) ||
      formatDateLabel(stringValue(item['updated_at']) || stringValue(item['created_at'])),
    thumbnailTone: tones[index % tones.length],
    progress: progress > 0 ? Math.round(progress) : undefined,
  };
}

export function mapProjectDetail(response: ProjectDetailResponse): ProjectCardVm {
  return mapUnknownProject({ ...response.project, video: response.video });
}

export function mapDashboard(response: DashboardResponse): DashboardVm {
  const recentProjects = response.recent_projects ?? [];
  const activeJobsResponse = response.active_jobs ?? [];
  const interruptedJobs = response.interrupted_jobs ?? [];
  const projects = recentProjects.map(mapUnknownProject);
  const activeJobs = activeJobsResponse.map((job, index) => mapUnknownQueueJob(job, index));

  return {
    recentProjects: projects,
    queueCount: activeJobsResponse.length + interruptedJobs.length,
    activeJobs,
    installedModels: [],
    availableModelsCount: numberValue(record(response.models)['missing'], 0),
    subtitle: `${projects.length} recent projects - ${
      response.system_status.ready ? 'System ready' : 'System needs setup'
    }`,
    system: {
      gpuName: 'Detecting GPU...',
      gpuUsage: 0,
      vramUsedGb: 0,
      vramTotalGb: 0,
      ready: response.system_status.ready,
      warnings: response.system_status.warnings,
    },
    source: 'api',
  };
}

export function mapGpu(response: GPUResponse | null, base: SystemStatusVm): SystemStatusVm {
  const gpu = response?.gpus?.[0];
  if (!response?.available || !gpu) {
    return {
      ...base,
      gpuName: 'GPU not detected',
      gpuUsage: 0,
      vramUsedGb: 0,
      vramTotalGb: 0,
    };
  }

  return {
    ...base,
    gpuName: gpu.name,
    gpuUsage: gpu.utilization_percent ?? 0,
    vramUsedGb: Math.round(((gpu.memory_used_mb ?? 0) / 1024) * 10) / 10,
    vramTotalGb: Math.round(((gpu.memory_total_mb ?? 0) / 1024) * 10) / 10,
  };
}

export function mapProjects(response: ProjectListResponse): ProjectCardVm[] {
  return response.items.map((project, index) => mapUnknownProject(project, index));
}

export function mapUnknownQueueJob(value: unknown, index = 0): QueueJobVm {
  const job = record(value);
  const actions = record(job['actions']);
  const progress = Math.round(pickNumber(job, ['progress_percent'], 0));
  const status = pickString(job, ['status'], 'queued');
  const stage = pickString(job, ['current_stage'], 'queued');
  const framesTotal = pickNumber(job, ['realesrgan_frames_total', 'frames_total'], 0);
  const framesDone = pickNumber(job, ['realesrgan_frames_processed', 'frames_processed'], 0);
  const avgFrameTimeMs = pickNumber(job, ['realesrgan_average_frame_time_ms'], 0);
  const etaSeconds =
    status === 'running' && stage === 'enhancing_frames' && avgFrameTimeMs > 0 && framesTotal > framesDone
      ? ((framesTotal - framesDone) * avgFrameTimeMs) / 1000
      : 0;

  return {
    id: pickString(job, ['job_id', 'id'], `job-${index}`),
    projectId: pickString(job, ['project_id']),
    projectName: pickString(job, ['project_name', 'name'], 'Untitled project'),
    status,
    statusTone: statusTone(status),
    stage: pickString(job, ['stage_label'], stage.replaceAll('_', ' ')),
    progress,
    model: pickString(job, ['model_slug', 'ai_model_slug'], 'Real-ESRGAN'),
    resolution: resolutionFromConfig(job),
    duration: formatSeconds(job['elapsed_time_seconds']),
    framesLabel: `${pickNumber(job, ['frames_processed', 'enhanced_frames'], 0)} / ${
      typeof job['frames_total'] === 'number' ? job['frames_total'] : '-'
    } frames`,
    pipeline: stageToPipeline(stage, progress, status),
    // Las acciones vienen del backend (job_contract_service); sin ellas no se ofrece nada.
    canStart: booleanValue(job['can_start'], booleanValue(actions['can_start'])),
    canCancel: booleanValue(job['can_cancel'], booleanValue(actions['can_cancel'])),
    canPause: booleanValue(job['can_pause'], booleanValue(actions['can_pause'])),
    canRetry: booleanValue(job['can_retry'], booleanValue(actions['can_retry'])),
    canCleanup: booleanValue(job['can_cleanup'], booleanValue(actions['can_cleanup'])),
    previewAvailable: booleanValue(job['preview_available']),
    exportAvailable: booleanValue(job['export_available'], booleanValue(actions['can_open_export'])),
    errorMessage: stringValue(job['error_message']),
    device: stringValue(job['realesrgan_device']) || undefined,
    avgFrameTimeMs: avgFrameTimeMs > 0 ? Math.round(avgFrameTimeMs) : undefined,
    failedFrames: pickNumber(job, ['realesrgan_failed_frames'], 0),
    etaLabel: etaSeconds > 0 ? `~${formatSeconds(etaSeconds)} left` : undefined,
    framesProcessed: pickNumber(job, ['enhanced_frames', 'frames_processed'], framesDone),
    framesTotal,
  };
}

export function mapQueue(response: QueueResponse): QueueJobVm[] {
  return response.items.map(mapUnknownQueueJob);
}

export function mapJobDetail(response: JobDetailResponse): QueueJobVm {
  return mapUnknownQueueJob({
    ...response.job,
    project_name: response.project.name,
  });
}

export function mapJobControl(response: JobControlResponse): QueueJobVm {
  return mapUnknownQueueJob(response.job);
}

export function mapJobProgress(response: JobProgressResponse, projectName = 'Active job'): QueueJobVm {
  return mapUnknownQueueJob({
    ...response,
    project_name: projectName,
  });
}

function mapModelLike(value: unknown, index = 0): ModelVm {
  const model = record(value);
  const installed = booleanValue(model['is_installed'], booleanValue(model['installed']));
  const scale = numberValue(model['scale_factor'], index === 1 ? 4 : 2);
  const slug = pickString(model, ['slug', 'id'], `model-${index}`);

  return {
    id: pickString(model, ['id', 'slug'], `model-${index}`),
    slug,
    name: pickString(model, ['name'], `Model ${index + 1}`),
    version: stringValue(model['version']) ? `v${model['version']}` : pickString(model, ['status'], installed ? 'installed' : 'available'),
    description: pickString(model, ['description'], 'AI video enhancement model.'),
    installed,
    enabled: booleanValue(model['is_enabled'], booleanValue(model['enabled'], true)),
    quality: scale === 4 ? 92 : 76,
    speed: scale === 4 ? 35 : 62,
    vramGb: Math.round((numberValue(model['estimated_vram_mb'], 4096) / 1024) * 10) / 10,
    category: pickString(model, ['category'], 'upscaling'),
  };
}

export function mapModels(response: ModelListResponse): ModelVm[] {
  return response.items.map(mapModelLike);
}

export function mapExports(response: ExportListResponse): ExportsPageVm {
  const history = response.items.map<ExportVm>((item) => ({
    id: item.id,
    projectId: item.project_id,
    jobId: item.job_id,
    fileName: item.file_name,
    filePath: item.file_path,
    dateLabel: new Date(item.created_at).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }),
    resolution: item.resolution_label ?? `${item.width ?? 3840}x${item.height ?? 2160}`,
    codec: item.video_codec ?? 'H.264',
    fpsLabel: typeof item.fps === 'number' ? `${Math.round(item.fps * 100) / 100}fps` : undefined,
    outputFolder: parentPath(item.file_path),
    sizeLabel: formatBytes(item.file_size_bytes, `${Math.max(item.file_size_mb / 1024, 0.1).toFixed(1)} GB`),
    duration: item.duration_label ?? formatSeconds(item.duration_seconds),
    canOpen: true,
  }));

  const emptyFeatured: ExportVm = {
    id: '',
    projectId: '',
    jobId: '',
    fileName: 'No exports yet',
    filePath: '',
    dateLabel: '-',
    resolution: '-',
    codec: '-',
    fpsLabel: undefined,
    outputFolder: undefined,
    sizeLabel: '-',
    duration: '-',
    canOpen: false,
  };

  return {
    featured: history[0] ?? emptyFeatured,
    history,
  };
}

export function mapSettings(response: SettingsResponse): SettingsVm {
  return {
    language: response.general.language,
    theme: response.general.theme,
    gpuName: '',
    frameEnhancerEngine: response.processing.frame_enhancer_engine,
    aiDevice: response.processing.ai_device,
    aiAllowCpu: response.processing.ai_allow_cpu,
    aiHalfPrecision: response.processing.ai_half_precision,
    realesrganTileSize: response.processing.realesrgan_tile_size,
    realesrganTilePad: response.processing.realesrgan_tile_pad,
    realesrganPrePad: response.processing.realesrgan_pre_pad,
    vramLimitGb: 0,
    tempPath: response.storage.temp_path,
    modelsPath: response.storage.models_path,
    exportsPath: response.storage.exports_path,
    autoSavePreviews: true,
    cleanupTempOnSuccess: response.cleanup.cleanup_temp_on_success,
    cleanupKeepPreviewFrames: response.cleanup.cleanup_keep_preview_frames,
    cleanupOlderThanHours: response.cleanup.cleanup_temp_older_than_hours,
  };
}

function mapVideoInfo(video: UnknownRecord): { label: string; value: string }[] {
  const fps = numberValue(video['fps'], 0);
  const audio = booleanValue(video['has_audio'])
    ? [stringValue(video['audio_codec']), video['audio_channels'] ? `${video['audio_channels']} ch` : '']
        .filter(Boolean)
        .join(' · ') || 'Yes'
    : 'None';
  const rows = [
    { label: 'File', value: stringValue(video['file_name']) },
    { label: 'Resolution', value: stringValue(video['resolution_label']) },
    { label: 'Duration', value: stringValue(video['duration_label']) },
    { label: 'Frame rate', value: fps > 0 ? `${Math.round(fps * 100) / 100} fps` : '' },
    { label: 'Codec', value: stringValue(video['video_codec']) },
    { label: 'Audio', value: audio },
    { label: 'Size', value: formatBytes(video['file_size_bytes'], '') },
  ];
  return rows.filter((row) => row.value);
}

export function mapWorkspace(response: ProjectWorkspaceResponse): WorkspaceVm {
  const project = mapUnknownProject({
    ...response.project,
    video: response.video,
    latest_job: response.latest_job,
    latest_export: response.latest_export,
  });
  const enhancement = record(response.project.enhancement_config);
  const exportConfig = record(response.project.export_config);
  const workspaceState = record(
    (response.project as unknown as UnknownRecord)['workspace_state'],
  );
  const modelsRecord = record(response.models);
  const available = Array.isArray(modelsRecord['available'])
    ? modelsRecord['available'].map(mapModelLike)
    : [];
  const selected = modelsRecord['selected']
    ? mapModelLike(modelsRecord['selected'])
    : (available[0] ?? emptyModelVm());
  const latestJob = record(response.latest_job);
  const latestExport = record(response.latest_export);
  const preview = record(response.preview);
  const recommended = record(preview['recommended']);
  const original = record(recommended['original']);
  const enhanced = record(recommended['enhanced']);

  return {
    project,
    videoAssetId: response.video.id,
    latestJobId: stringValue(latestJob['id']) || undefined,
    latestJobStatus: stringValue(latestJob['status']) || undefined,
    latestExportId: stringValue(latestExport['id']) || undefined,
    selectedModel: selected,
    alternateModels: available,
    denoise: numberValue(enhancement['denoise'], 0),
    sharpen: numberValue(enhancement['sharpen'], 0),
    compressionCleanup: booleanValue(enhancement['compression_cleanup']),
    scale: stringValue(enhancement['scale'], '2x') as WorkspaceVm['scale'],
    exportResolution: stringValue(exportConfig['output_resolution'], '2x') as WorkspaceVm['exportResolution'],
    keepAudio: booleanValue(exportConfig['keep_audio'], true),
    compareMode:
      stringValue(workspaceState['compare_mode']) === 'side_by_side' ? 'side_by_side' : 'slider',
    zoom: stringValue(workspaceState['zoom']) === '100%' ? '100%' : 'fit',
    videoFps: numberValue(record(response.video)['fps'], 30),
    previewTotalFrames: pickNumber(latestJob, ['enhanced_frames', 'frames_total'], 0),
    estimateTime: latestJob['estimated_time_seconds']
      ? `~${formatSeconds(latestJob['estimated_time_seconds'])}`
      : '--',
    videoInfo: mapVideoInfo(record(response.video)),
    outputSize: formatBytes(latestExport['file_size_bytes'], '--'),
    previewBefore: stringValue(original['url'], ''),
    previewAfter: stringValue(enhanced['url'], ''),
    timelineFrames: [],
    pipeline: latestJob['current_stage']
      ? stageToPipeline(
          stringValue(latestJob['current_stage']),
          numberValue(latestJob['progress_percent']),
          stringValue(latestJob['status']),
        )
      : idlePipeline(),
    actions: response.actions,
  };
}

function idlePipeline(): PipelineStepVm[] {
  return pipelineOrder.map((id, index) => ({
    id,
    title: pipelineTitles[index],
    icon: pipelineIcons[index],
    status: 'pending' as const,
  }));
}

function emptyModelVm(): ModelVm {
  return {
    id: '',
    slug: '',
    name: 'No models available',
    version: '',
    description: 'Install an AI model to start enhancing videos.',
    installed: false,
    enabled: false,
    quality: 0,
    speed: 0,
    vramGb: 0,
    category: 'upscaling',
  };
}
