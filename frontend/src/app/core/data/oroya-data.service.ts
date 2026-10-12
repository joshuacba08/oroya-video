import { Injectable, signal } from '@angular/core';
import {
  Observable,
  catchError,
  defer,
  from,
  map,
  of,
  retry,
  switchMap,
  tap,
  throwError,
  timer,
} from 'rxjs';

import { environment } from '../../../environments/environment';
import { APP_VERSION } from '../app-version';
import { setLanguage, translate } from '../i18n/i18n';
import type {
  AIInstallProgressResponse,
  AIInstallStartResponse,
  AIRuntimeStatusResponse,
  AppStateResponse,
  BootstrapResponse,
  CompareFrameResponse,
  DashboardResponse,
  ExportDeleteResponse,
  ExportListResponse,
  ExportOpenResponse,
  FFmpegDownloadProgressResponse,
  FFmpegDownloadStartResponse,
  GPUResponse,
  HealthResponse,
  JobControlResponse,
  JobCreateRequest,
  JobDetailResponse,
  JobListResponse,
  JobPreflightResponse,
  JobProgressResponse,
  ModelDownloadProgressResponse,
  ModelDownloadStartResponse,
  ModelListResponse,
  ModelRefreshResponse,
  PreviewFrameListResponse,
  ProjectCreateRequest,
  ProjectDetailResponse,
  ProjectListResponse,
  ProjectUpdateRequest,
  ProjectWorkspaceResponse,
  QueueResponse,
  SettingsResponse,
  SettingsUpdateRequest,
  SettingsUpdateResponse,
  VideoImportResponse,
  VideoProbeResponse,
} from '../api/api-types';
import { OroyaApiClient, OroyaApiError } from '../api/oroya-api-client';
import type {
  ApiErrorVm,
  BackendStatusVm,
  DashboardVm,
  ExportsPageVm,
  ModelVm,
  PickedVideo,
  ProjectCardVm,
  QueueJobVm,
  PreviewFrameVm,
  SettingsVm,
  StartupVm,
  WorkspaceVm,
} from '../models/oroya.models';
import {
  MOCK_DASHBOARD,
  MOCK_EXPORTS,
  MOCK_MODELS,
  MOCK_PROJECTS,
  MOCK_QUEUE,
  MOCK_SETTINGS,
  MOCK_WORKSPACE,
} from './mock-data';
import {
  mapDashboard,
  mapExports,
  mapJobControl,
  mapJobDetail,
  mapJobProgress,
  mapModels,
  mapProjectDetail,
  mapProjects,
  mapQueue,
  mapSettings,
  mapWorkspace,
} from './oroya.mappers';

/** Polling: un error puntual (backend reiniciando, timeout) no debe terminar el stream. */
export type PollErrorHandler = (error: unknown | null) => void;

const MAX_POLL_BACKOFF_MS = 30000;
const SSE_FINAL_STATUSES = new Set(['completed', 'failed', 'cancelled', 'interrupted', 'paused']);

function resilientPoll<T>(
  intervalMs: number,
  request: () => Observable<T>,
  onError?: PollErrorHandler,
): Observable<T> {
  return timer(0, intervalMs).pipe(
    switchMap(() => request()),
    tap({ next: () => onError?.(null), error: (error: unknown) => onError?.(error) }),
    retry({
      delay: (_error, attempt) =>
        timer(Math.min(intervalMs * 2 ** (attempt - 1), MAX_POLL_BACKOFF_MS)),
      resetOnSuccess: true,
    }),
  );
}

const DEFAULT_ENHANCEMENT_CONFIG = {
  model_id: 'realesrgan-x2',
  scale: '2x',
  denoise: 0,
  sharpen: 0,
  compression_cleanup: false,
};

const DEFAULT_EXPORT_CONFIG = {
  format: 'mp4',
  codec: 'h264',
  keep_audio: true,
  output_resolution: '2x',
};

const CHECKING_STATUS: BackendStatusVm = {
  state: 'checking',
  isApi: false,
  isMock: false,
  isOffline: false,
  wrongBackend: false,
  message: translate('backend.checking'),
  warnings: [],
};

@Injectable({ providedIn: 'root' })
export class OroyaDataService {
  readonly dataSource = signal<'api' | 'mock'>('mock');
  readonly backendStatus = signal<BackendStatusVm>(CHECKING_STATUS);
  readonly lastError = signal<ApiErrorVm | null>(null);

  private readonly api = new OroyaApiClient();
  private apiVerifiedUntil = 0;

  startup(): Observable<StartupVm> {
    return defer(() => this.loadStartup());
  }

  dashboard(): Observable<DashboardVm> {
    return this.resolve<DashboardResponse, DashboardVm>(
      '/dashboard',
      mapDashboard,
      MOCK_DASHBOARD,
    ).pipe(
      map((dashboard) => ({
        ...dashboard,
        recentProjects: dashboard.recentProjects.map((project) => this.withThumbnail(project)),
      })),
    );
  }

  /** `onError` recibe el error de cada fallo y `null` cuando el polling se recupera. */
  pollDashboard(onError?: PollErrorHandler): Observable<DashboardVm> {
    return resilientPoll(10000, () => this.dashboard(), onError);
  }

  gpu(): Observable<GPUResponse | null> {
    if (environment.dataMode === 'mock' || !this.backendStatus().isApi) {
      return of(null);
    }

    return defer(() => this.api.get<GPUResponse>('/system/gpu')).pipe(
      catchError(() => of(null)),
    );
  }

  pollGpu(intervalMs = 5000): Observable<GPUResponse | null> {
    return timer(0, intervalMs).pipe(switchMap(() => this.gpu()));
  }

  downloadModel(slug: string): Observable<ModelDownloadStartResponse> {
    return this.command(() =>
      this.api.post<ModelDownloadStartResponse>(
        `/models/${encodeURIComponent(slug)}/download`,
      ),
    );
  }

  modelDownloadProgress(slug: string): Observable<ModelDownloadProgressResponse> {
    return this.command(() =>
      this.api.get<ModelDownloadProgressResponse>(
        `/models/${encodeURIComponent(slug)}/download/progress`,
      ),
    );
  }

  pollModelDownload(slug: string, intervalMs = 750): Observable<ModelDownloadProgressResponse> {
    return timer(0, intervalMs).pipe(switchMap(() => this.modelDownloadProgress(slug)));
  }

  downloadFfmpeg(): Observable<FFmpegDownloadStartResponse> {
    return this.command(() =>
      this.api.post<FFmpegDownloadStartResponse>('/system/ffmpeg/download'),
    );
  }

  ffmpegDownloadProgress(): Observable<FFmpegDownloadProgressResponse> {
    return this.command(() =>
      this.api.get<FFmpegDownloadProgressResponse>('/system/ffmpeg/download/progress'),
    );
  }

  pollFfmpegDownload(intervalMs = 750): Observable<FFmpegDownloadProgressResponse> {
    return timer(0, intervalMs).pipe(switchMap(() => this.ffmpegDownloadProgress()));
  }

  installAi(): Observable<AIInstallStartResponse> {
    return this.command(() => this.api.post<AIInstallStartResponse>('/system/ai/install'));
  }

  aiInstallProgress(): Observable<AIInstallProgressResponse> {
    return this.command(() =>
      this.api.get<AIInstallProgressResponse>('/system/ai/install/progress'),
    );
  }

  /** La instalación tarda minutos (PyTorch pesa >2 GB con CUDA): sondeo resistente a errores. */
  pollAiInstall(intervalMs = 1500): Observable<AIInstallProgressResponse> {
    return resilientPoll(intervalMs, () => this.aiInstallProgress());
  }

  filteredPreviewUrl(
    jobId: string,
    frameIndex: number,
    config: { denoise: number; sharpen: number; compressionCleanup: boolean },
  ): string {
    const url = new URL(
      this.api.resolveUrl(
        `/jobs/${encodeURIComponent(jobId)}/preview/filtered/${frameIndex}`,
      ),
    );
    url.searchParams.set('denoise', String(config.denoise));
    url.searchParams.set('sharpen', String(config.sharpen));
    url.searchParams.set('compression_cleanup', String(config.compressionCleanup));
    return url.toString();
  }

  projects(search?: string): Observable<ProjectCardVm[]> {
    return this.resolve<ProjectListResponse, ProjectCardVm[]>(
      '/projects',
      mapProjects,
      MOCK_PROJECTS,
      { search },
    ).pipe(map((projects) => projects.map((project) => this.withThumbnail(project))));
  }

  queue(): Observable<QueueJobVm[]> {
    return this.resolve<QueueResponse, QueueJobVm[]>('/queue', mapQueue, MOCK_QUEUE);
  }

  pollQueue(onError?: PollErrorHandler): Observable<QueueJobVm[]> {
    return resilientPoll(2000, () => this.queue(), onError);
  }

  models(): Observable<ModelVm[]> {
    return this.resolve<ModelListResponse, ModelVm[]>(
      '/models',
      mapModels,
      MOCK_MODELS,
    );
  }

  exports(): Observable<ExportsPageVm> {
    return this.resolve<ExportListResponse, ExportsPageVm>(
      '/exports',
      (response) => this.withResolvedExportUrls(mapExports(response)),
      MOCK_EXPORTS,
    );
  }

  private withResolvedExportUrls(page: ExportsPageVm): ExportsPageVm {
    const resolve = (item: ExportsPageVm['featured']): ExportsPageVm['featured'] =>
      item.id
        ? {
            ...item,
            mediaUrl: this.api.resolveUrl(`/exports/${encodeURIComponent(item.id)}/file`),
          }
        : item;

    return {
      featured: resolve(page.featured),
      history: page.history.map(resolve),
    };
  }

  settings(): Observable<SettingsVm> {
    return this.resolve<SettingsResponse, SettingsVm>(
      '/settings',
      mapSettings,
      MOCK_SETTINGS,
    ).pipe(tap((settings) => setLanguage(settings.language)));
  }

  workspace(projectId: string): Observable<WorkspaceVm> {
    const mock = {
      ...MOCK_WORKSPACE,
      project:
        MOCK_PROJECTS.find((project) => project.id === projectId) ??
        MOCK_WORKSPACE.project,
    };

    return this.resolve<ProjectWorkspaceResponse, WorkspaceVm>(
      `/projects/${encodeURIComponent(projectId)}/workspace`,
      (response) => this.withResolvedPreviewUrls(mapWorkspace(response)),
      mock,
    );
  }

  importPickedVideo(selection: PickedVideo): Observable<ProjectCardVm> {
    return this.importVideoPath(selection.path);
  }

  importVideoPath(path: string): Observable<ProjectCardVm> {
    return this.probeVideo(path).pipe(
      switchMap((probe) => {
        if (!probe.valid) {
          return throwError(
            () =>
              new OroyaApiError('video_probe_invalid', translate('errors.video_probe_invalid'), {
                details: { warnings: probe.warnings },
                method: 'POST',
                path: '/videos/probe',
              }),
          );
        }

        return this.importVideo(path);
      }),
      switchMap((imported) =>
        this.createProject({
          name: imported.video.file_name,
          video_asset_id: imported.video.id,
          enhancement_config: DEFAULT_ENHANCEMENT_CONFIG,
          export_config: DEFAULT_EXPORT_CONFIG,
        }),
      ),
      map(mapProjectDetail),
      catchError((error: unknown) => {
        this.captureError(error);
        return throwError(() => error);
      }),
    );
  }

  probeVideo(path: string): Observable<VideoProbeResponse> {
    return this.command(() =>
      this.api.post<VideoProbeResponse>('/videos/probe', { file_path: path }),
    );
  }

  importVideo(path: string): Observable<VideoImportResponse> {
    return this.command(() =>
      this.api.post<VideoImportResponse>('/videos/import', {
        file_path: path,
        source_mode: 'reference',
      }),
    );
  }

  createProject(payload: ProjectCreateRequest): Observable<ProjectDetailResponse> {
    return this.command(() => this.api.post<ProjectDetailResponse>('/projects', payload));
  }

  updateProject(projectId: string, payload: ProjectUpdateRequest): Observable<ProjectDetailResponse> {
    return this.command(() =>
      this.api.patch<ProjectDetailResponse>(`/projects/${encodeURIComponent(projectId)}`, payload),
    );
  }

  deleteProject(projectId: string): Observable<unknown> {
    return this.command(() => this.api.delete(`/projects/${encodeURIComponent(projectId)}`));
  }

  createJob(payload: JobCreateRequest): Observable<QueueJobVm> {
    return this.command(() => this.api.post<JobDetailResponse>('/jobs', payload)).pipe(
      map(mapJobDetail),
    );
  }

  preflightJob(jobId: string): Observable<JobPreflightResponse> {
    return this.command(() =>
      this.api.get<JobPreflightResponse>(`/jobs/${encodeURIComponent(jobId)}/preflight`),
    );
  }

  startJob(jobId: string): Observable<QueueJobVm> {
    return this.jobCommand(jobId, 'start');
  }

  pauseJob(jobId: string): Observable<QueueJobVm> {
    return this.jobCommand(jobId, 'pause');
  }

  resumeJob(jobId: string): Observable<QueueJobVm> {
    return this.jobCommand(jobId, 'resume');
  }

  cancelJob(jobId: string): Observable<QueueJobVm> {
    return this.jobCommand(jobId, 'cancel');
  }

  retryJob(jobId: string): Observable<QueueJobVm> {
    return this.command(() =>
      this.api.post<JobControlResponse>(`/jobs/${encodeURIComponent(jobId)}/retry`, {
        cleanup_before_retry: true,
        reset_progress: true,
        start: true,
      }),
    ).pipe(map(mapJobControl));
  }

  aiRuntime(): Observable<AIRuntimeStatusResponse> {
    return this.command(() => this.api.get<AIRuntimeStatusResponse>('/ai/runtime'));
  }

  deleteJob(jobId: string): Observable<unknown> {
    return this.command(() => this.api.delete(`/jobs/${encodeURIComponent(jobId)}`));
  }

  cleanupJobTemp(jobId: string): Observable<unknown> {
    return this.command(() =>
      this.api.delete(`/jobs/${encodeURIComponent(jobId)}/temp`, {
        include_original_frames: true,
        include_enhanced_frames: true,
        include_encoded: true,
        include_muxed: true,
      }),
    );
  }

  jobProgress(jobId: string, projectName?: string): Observable<QueueJobVm> {
    return this.command(() =>
      this.api.get<JobProgressResponse>(`/jobs/${encodeURIComponent(jobId)}/progress`),
    ).pipe(map((response) => mapJobProgress(response, projectName)));
  }

  /**
   * Progreso en vivo: SSE (`/jobs/{id}/events`) y, si no está disponible o se corta,
   * polling con backoff. Completa cuando el job llega a un estado terminal o pausado.
   */
  pollJobProgress(
    jobId: string,
    projectName?: string,
    intervalMs = 1000,
    onError?: PollErrorHandler,
  ): Observable<QueueJobVm> {
    const polling = resilientPoll(intervalMs, () => this.jobProgress(jobId, projectName), onError);
    if (environment.dataMode === 'mock' || typeof EventSource === 'undefined') {
      return polling;
    }
    return this.jobEvents(jobId, projectName).pipe(
      tap(() => onError?.(null)),
      catchError(() => polling),
    );
  }

  jobEvents(jobId: string, projectName?: string): Observable<QueueJobVm> {
    return new Observable<QueueJobVm>((subscriber) => {
      const source = new EventSource(
        this.api.resolveUrl(`/jobs/${encodeURIComponent(jobId)}/events`),
      );
      source.onmessage = (event: MessageEvent<string>) => {
        const response = JSON.parse(event.data) as JobProgressResponse;
        subscriber.next(mapJobProgress(response, projectName));
        if (SSE_FINAL_STATUSES.has(response.status)) {
          // Cerrar antes de que el servidor corte: EventSource reconectaría solo.
          source.close();
          subscriber.complete();
        }
      };
      source.onerror = () => {
        source.close();
        subscriber.error(new OroyaApiError('sse_unavailable', 'Live progress stream failed.'));
      };
      return () => source.close();
    });
  }

  previewRecommended(jobId: string): Observable<CompareFrameResponse> {
    return this.command(() =>
      this.api.get<CompareFrameResponse>(`/jobs/${encodeURIComponent(jobId)}/preview/recommended`),
    ).pipe(map((response) => this.resolveCompareFrame(response)));
  }

  compareFrame(jobId: string, frameIndex: number): Observable<CompareFrameResponse> {
    return this.command(() =>
      this.api.get<CompareFrameResponse>(
        `/jobs/${encodeURIComponent(jobId)}/preview/compare/${frameIndex}`,
      ),
    ).pipe(map((response) => this.resolveCompareFrame(response)));
  }

  previewFrames(jobId: string, options: { limit?: number; offset?: number } = {}): Observable<PreviewFrameVm[]> {
    return this.command(() =>
      this.api.get<PreviewFrameListResponse>(
        `/jobs/${encodeURIComponent(jobId)}/preview/frames`,
        {
          limit: options.limit,
          offset: options.offset,
        },
      ),
    ).pipe(
      map((response) =>
        response.items.map((item) => ({
          index: item.index,
          fileName: item.file_name,
          originalAvailable: item.original_available,
          enhancedAvailable: item.enhanced_available,
          originalUrl: item.original_url ? this.api.resolveUrl(item.original_url) : undefined,
          enhancedUrl: item.enhanced_url ? this.api.resolveUrl(item.enhanced_url) : undefined,
        })),
      ),
    );
  }

  openExport(exportId: string): Observable<ExportOpenResponse> {
    return this.command(() =>
      this.api.post<ExportOpenResponse>(`/exports/${encodeURIComponent(exportId)}/open`),
    );
  }

  openExportFolder(exportId: string): Observable<ExportOpenResponse> {
    return this.command(() =>
      this.api.post<ExportOpenResponse>(`/exports/${encodeURIComponent(exportId)}/open-folder`),
    );
  }

  deleteExport(exportId: string, deleteFile = true): Observable<ExportDeleteResponse> {
    return this.command(() =>
      this.api.delete<ExportDeleteResponse>(`/exports/${encodeURIComponent(exportId)}`, {
        delete_file: deleteFile,
      }),
    );
  }

  patchSettings(payload: SettingsUpdateRequest): Observable<SettingsVm> {
    return this.command(() =>
      this.api.patch<SettingsUpdateResponse>('/settings', payload),
    ).pipe(
      map((response) => mapSettings(response.settings)),
      tap((settings) => setLanguage(settings.language)),
    );
  }

  openStorageFolder(target: 'temp' | 'models' | 'exports'): Observable<unknown> {
    return this.command(() =>
      this.api.post(`/system/storage/open?target=${encodeURIComponent(target)}`),
    );
  }

  setModelEnabled(slug: string, enabled: boolean): Observable<unknown> {
    const action = enabled ? 'enable' : 'disable';
    return this.command(() =>
      this.api.post(`/models/${encodeURIComponent(slug)}/${action}`),
    );
  }

  refreshModels(): Observable<ModelRefreshResponse> {
    return this.command(() => this.api.post<ModelRefreshResponse>('/models/refresh'));
  }

  resolveMediaUrl(pathOrUrl: string): string {
    return this.api.resolveUrl(pathOrUrl);
  }

  toErrorVm(error: unknown): ApiErrorVm {
    if (error instanceof OroyaApiError) {
      return {
        code: error.code,
        // Mensaje traducido por error_code; si no hay traducción, el del backend.
        message: translate(`errors.${error.code}`, undefined, error.message),
        status: error.status,
        requestId: error.requestId,
        details: error.details,
      };
    }

    return {
      code: 'unknown_error',
      message: error instanceof Error ? error.message : translate('common.unknownError'),
    };
  }

  private jobCommand(jobId: string, command: 'start' | 'pause' | 'resume' | 'cancel'): Observable<QueueJobVm> {
    return this.command(() =>
      this.api.post<JobControlResponse>(`/jobs/${encodeURIComponent(jobId)}/${command}`),
    ).pipe(map(mapJobControl));
  }

  private resolve<TApi, TVm>(
    path: string,
    mapper: (value: TApi) => TVm,
    mock: TVm,
    query?: Record<string, string | number | boolean | null | undefined>,
  ): Observable<TVm> {
    if (environment.dataMode === 'mock') {
      this.useMockStatus(translate('backend.mockMode'));
      return of(mock);
    }

    return defer(async () => {
      await this.verifyBackend();
      const value = await this.api.get<TApi>(path, query);
      this.useApiStatus();
      return mapper(value);
    }).pipe(
      catchError((error: unknown) => {
        this.captureError(error);
        return throwError(() => error);
      }),
    );
  }

  private command<T>(task: () => Promise<T>): Observable<T> {
    if (environment.dataMode === 'mock') {
      return throwError(
        () =>
          new OroyaApiError(
            'mock_command_disabled',
            'This action needs the Oroya backend; mock mode cannot perform commands.',
          ),
      );
    }

    return defer(async () => {
      await this.verifyBackend();
      const result = await task();
      this.useApiStatus();
      return result;
    }).pipe(
      catchError((error: unknown) => {
        this.captureError(error);
        return throwError(() => error);
      }),
    );
  }

  private async verifyBackend(): Promise<HealthResponse> {
    if (Date.now() < this.apiVerifiedUntil) {
      return {
        status: 'ok',
        service: this.backendStatus().service ?? 'Oroya Video Backend',
        version: this.backendStatus().version,
      };
    }

    const health = await this.api.healthStrict();
    this.apiVerifiedUntil = Date.now() + 5000;
    this.useApiStatus(health);
    return health;
  }

  private async loadStartup(): Promise<StartupVm> {
    if (environment.dataMode === 'mock') {
      this.useMockStatus(translate('backend.mockMode'));
      return this.mockStartup(translate('backend.mockMode'));
    }

    try {
      const health = await this.verifyBackend();
      const [bootstrap, appState, settings, interrupted] = await Promise.all([
        this.api.get<BootstrapResponse>('/bootstrap'),
        this.api.get<AppStateResponse>('/app-state'),
        this.api.get<SettingsResponse>('/settings'),
        this.api.get<JobListResponse>('/jobs/interrupted'),
      ]);
      setLanguage(settings.general?.language);
      const warnings = [
        ...bootstrap.warnings,
        ...(!appState.system.ready ? [translate('backend.notReady')] : []),
      ];
      this.useApiStatus(health, warnings);
      return {
        backend: this.backendStatus(),
        ready: appState.system.ready,
        appName: bootstrap.app.name,
        appVersion: bootstrap.app.version,
        queueCount:
          appState.queue.running +
          appState.queue.queued +
          appState.queue.pending +
          appState.queue.interrupted,
        interruptedCount: interrupted.total,
        warnings,
        ffmpegAvailable: bootstrap.system.ffmpeg_available,
        modelsInstalled: bootstrap.counts.models_installed,
        aiRuntimeAvailable: bootstrap.system.ai_runtime_available,
      };
    } catch (error) {
      this.captureError(error);

      if (this.isWrongBackend(error)) {
        this.useWrongBackendStatus(error);
        return {
          backend: this.backendStatus(),
          ready: false,
          appName: 'Oroya Video',
          appVersion: APP_VERSION,
          queueCount: 0,
          interruptedCount: 0,
          warnings: [this.toErrorVm(error).message],
          ffmpegAvailable: false,
          modelsInstalled: 0,
          aiRuntimeAvailable: false,
        };
      }

      this.useOfflineStatus(error);
      throw error;
    }
  }

  private thumbnailPath(videoAssetId: string | undefined): string {
    if (!videoAssetId || environment.dataMode === 'mock') {
      return '';
    }
    return `/videos/${encodeURIComponent(videoAssetId)}/thumbnail`;
  }

  private withThumbnail(project: ProjectCardVm): ProjectCardVm {
    const path = this.thumbnailPath(project.videoAssetId);
    return path ? { ...project, thumbnailUrl: this.api.resolveUrl(path) } : project;
  }

  private withResolvedPreviewUrls(workspace: WorkspaceVm): WorkspaceVm {
    return {
      ...workspace,
      // Sin frames procesados todavía, se muestra un fotograma del video original.
      previewBefore: this.api.resolveUrl(
        workspace.previewBefore || this.thumbnailPath(workspace.videoAssetId),
      ),
      previewAfter: this.api.resolveUrl(workspace.previewAfter),
    };
  }

  private resolveCompareFrame(response: CompareFrameResponse): CompareFrameResponse {
    return {
      ...response,
      original: {
        ...response.original,
        url: this.api.resolveUrl(response.original.url),
      },
      enhanced: {
        ...response.enhanced,
        url: this.api.resolveUrl(response.enhanced.url),
      },
    };
  }

  private mockStartup(message: string): StartupVm {
    return {
      backend: this.backendStatus(),
      ready: false,
      appName: 'Oroya Video',
      appVersion: APP_VERSION,
      queueCount: MOCK_QUEUE.length,
      interruptedCount: 0,
      warnings: [message],
      ffmpegAvailable: true,
      modelsInstalled: 0,
      aiRuntimeAvailable: false,
    };
  }

  private useApiStatus(health?: HealthResponse, warnings: string[] = []): void {
    this.dataSource.set('api');
    this.backendStatus.set({
      state: 'api',
      isApi: true,
      isMock: false,
      isOffline: false,
      wrongBackend: false,
      service: health?.service ?? 'Oroya Video Backend',
      version: health?.version ?? null,
      message: translate('backend.connected'),
      warnings,
    });
  }

  private useMockStatus(message: string, error?: unknown): void {
    this.dataSource.set('mock');
    this.backendStatus.set({
      state: error ? 'offline' : 'mock',
      isApi: false,
      isMock: true,
      isOffline: Boolean(error),
      wrongBackend: false,
      message,
      warnings: [message],
      error: error ? this.toErrorVm(error) : undefined,
    });
  }

  private useWrongBackendStatus(error: unknown): void {
    this.dataSource.set('mock');
    this.backendStatus.set({
      state: 'wrong-backend',
      isApi: false,
      isMock: false,
      isOffline: false,
      wrongBackend: true,
      message: this.toErrorVm(error).message,
      warnings: [this.toErrorVm(error).message],
      error: this.toErrorVm(error),
    });
  }

  private captureError(error: unknown): void {
    const vm = this.toErrorVm(error);
    this.lastError.set(vm);

    if (this.isWrongBackend(error)) {
      this.useWrongBackendStatus(error);
      return;
    }

    if (this.isNetworkError(error)) {
      this.useOfflineStatus(error);
    }
  }

  private useOfflineStatus(error: unknown): void {
    if (this.isWrongBackend(error)) {
      this.useWrongBackendStatus(error);
      return;
    }

    const vm = this.toErrorVm(error);
    this.dataSource.set('api');
    this.backendStatus.set({
      state: 'offline',
      isApi: false,
      isMock: false,
      isOffline: true,
      wrongBackend: false,
      message: translate('backend.unreachable'),
      warnings: [vm.message],
      error: vm,
    });
  }

  private isNetworkError(error: unknown): boolean {
    if (!(error instanceof OroyaApiError)) {
      return false;
    }
    return ['network_error', 'request_timeout'].includes(error.code);
  }

  private isWrongBackend(error: unknown): boolean {
    return error instanceof OroyaApiError && error.code === 'wrong_backend';
  }
}
