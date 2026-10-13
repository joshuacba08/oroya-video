import { AsyncPipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { NAIPipeline } from '@neuralangular/angular-ui/ai-pipeline';
import { NButton } from '@neuralangular/angular-ui/button';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { NProgress } from '@neuralangular/angular-ui/progress';
import {
  BehaviorSubject,
  Subscription,
  catchError,
  combineLatest,
  firstValueFrom,
  map,
  of,
  switchMap,
  tap,
} from 'rxjs';

import type { CompareFrameResponse, JobPreflightResponse } from '../../core/api/api-types';
import { OroyaApiError } from '../../core/api/oroya-api-client';
import { OroyaDataService } from '../../core/data/oroya-data.service';
import { translate } from '../../core/i18n/i18n';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import { DialogService } from '../../core/dialogs/dialog.service';
import { DesktopService } from '../../core/desktop/desktop.service';
import type {
  ApiErrorVm,
  EncodingQuality,
  InterpolationTarget,
  ModelVm,
  PreviewFrameVm,
  QueueJobVm,
  VideoCodec,
  WorkspaceVm,
} from '../../core/models/oroya.models';
import { OvVideoPreviewComponent } from '../../shared/ui/ov-video-preview.component';
import { clampTrim, formatTrimTime, MIN_TRIM_SECONDS, parseTrimTime } from './trim-time';

type WorkspaceControls = {
  modelId: string;
  scale: WorkspaceVm['scale'];
  exportResolution: WorkspaceVm['exportResolution'];
  denoise: number;
  sharpen: number;
  compressionCleanup: boolean;
  faceRestore: boolean;
  /** 0-100 en la UI; el backend usa 0-1. */
  faceStrength: number;
  interpolation: boolean;
  interpolationTarget: InterpolationTarget;
  aiStrength: number;
  modelDenoise: number;
  keepAudio: boolean;
  codec: VideoCodec;
  quality: EncodingQuality;
  gpuEncoding: boolean;
  tenBit: boolean;
  /** Vacío: nombre por defecto ("<proyecto> (Oroya 2x)"). */
  exportFileName: string;
  /** Vacío: la carpeta de exportación de Ajustes (con una subcarpeta por proyecto). */
  exportDir: string;
  /** Procesar solo [trimStart, trimEnd] (segundos del original). */
  trimEnabled: boolean;
  trimStart: number;
  trimEnd: number;
  compareMode: WorkspaceVm['compareMode'];
  zoom: WorkspaceVm['zoom'];
};

/** Máximo de píxeles por segundo del nivel H.264 5.1 (983 040 macrobloques/s). */
const H264_LEVEL_51_PIXEL_RATE = 983_040 * 256;
/** H.265 nivel 5.1: 534 773 760 muestras de luma por segundo. */
const H265_LEVEL_51_PIXEL_RATE = 534_773_760;

type QualityPreset = {
  id: string;
  labelKey: string;
  modelSlug: string;
  scale: WorkspaceVm['scale'];
  aiStrength: number;
  modelDenoise: number;
  compressionCleanup: boolean;
};

/** Valores elegidos comparando en video real de DVD (piano, caras) y animación. */
const QUALITY_PRESETS: QualityPreset[] = [
  {
    id: 'old-video',
    labelKey: 'workspace.presetOldVideo',
    modelSlug: 'realesrgan-general',
    scale: '2x',
    aiStrength: 85,
    modelDenoise: 30,
    compressionCleanup: true,
  },
  {
    id: 'animation',
    labelKey: 'workspace.presetAnimation',
    modelSlug: 'realesrgan-x4',
    scale: '2x',
    aiStrength: 100,
    modelDenoise: 50,
    compressionCleanup: true,
  },
  {
    id: 'max-detail',
    labelKey: 'workspace.presetMaxDetail',
    modelSlug: 'realesrgan-x4',
    scale: '4x',
    aiStrength: 100,
    modelDenoise: 50,
    compressionCleanup: false,
  },
];

/** El progreso llega cada ~0,5 s (SSE); la vista previa en vivo basta con refrescarla cada 2 s. */
const LIVE_PREVIEW_REFRESH_MS = 2000;

@Component({
  selector: 'app-workspace-page',
  standalone: true,
  imports: [
    AsyncPipe,
    NAIPipeline,
    NButton,
    NIcon,
    NProgress,
    OvVideoPreviewComponent,
    RouterLink,
    TranslatePipe,
  ],
  templateUrl: './workspace.page.html',
  styleUrl: './workspace.page.css',
})
export class WorkspacePage {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly data = inject(OroyaDataService);
  private readonly desktop = inject(DesktopService);
  private readonly dialogs = inject(DialogService);
  private readonly destroyRef = inject(DestroyRef);
  private saveTimer: ReturnType<typeof setTimeout> | undefined;
  private hydratedProjectId: string | undefined;
  private liveSub: Subscription | undefined;
  private liveJobId: string | undefined;
  private lastEnhancedCount = 0;
  private lastPreviewRefresh = 0;
  private readonly reload$ = new BehaviorSubject<number>(0);

  readonly error = signal<ApiErrorVm | null>(null);
  readonly previewError = signal<ApiErrorVm | null>(null);
  readonly preflight = signal<JobPreflightResponse | null>(null);
  readonly activeJob = signal<QueueJobVm | null>(null);
  readonly liveJob = signal<QueueJobVm | null>(null);
  readonly followLive = signal(true);
  readonly jobActionBusy = signal(false);
  readonly processing = signal(false);
  readonly controls = signal<WorkspaceControls | null>(null);
  readonly saveState = signal<'idle' | 'saving' | 'saved' | 'error'>('idle');
  readonly previewFrames = signal<PreviewFrameVm[]>([]);
  readonly selectedPreview = signal<CompareFrameResponse | null>(null);
  readonly selectedFrameIndex = signal<number | null>(null);
  readonly collapsedSections = signal<ReadonlySet<string>>(new Set(['video']));

  readonly workspace$ = combineLatest([this.route.paramMap, this.reload$]).pipe(
    map(([params]) => params.get('id') ?? 'anime-episode-12'),
    switchMap((id) => this.data.workspace(id)),
    tap((workspace) => {
      this.hydrateControls(workspace);
      void this.loadPreviewData(workspace);
      this.syncLivePolling(workspace);
    }),
    catchError((error: unknown) => {
      this.error.set(this.data.toErrorVm(error));
      return of(null);
    }),
  );

  constructor() {
    this.data
      .encoders()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((response) => this.gpuEncoders.set(response?.hardware ?? {}));
  }

  backToProjects(): void {
    void this.router.navigateByUrl('/projects');
  }

  async startProcessing(workspace: WorkspaceVm): Promise<void> {
    const controls = this.ensureControls(workspace);
    const model = this.selectedModel(workspace) ?? workspace.selectedModel;
    this.processing.set(true);
    this.error.set(null);
    this.preflight.set(null);

    try {
      await this.persistControls(workspace);
      const created = await firstValueFrom(
        this.data.createJob({
          project_id: workspace.project.id,
          model_id: model.id,
          enhancement_config: {
            model_id: model.slug,
            scale: controls.scale,
            denoise: controls.denoise,
            sharpen: controls.sharpen,
            compression_cleanup: controls.compressionCleanup,
            face_restore: this.faceRestoreConfig(workspace, controls),
            interpolation: this.interpolationConfig(workspace, controls),
            ai_strength: controls.aiStrength,
            model_denoise: controls.modelDenoise,
          },
          export_config: this.exportConfig(controls),
        }),
      );
      const jobId = created.id;

      const preflight = await firstValueFrom(this.data.preflightJob(jobId));
      this.preflight.set(preflight);

      if (!preflight.ready) {
        // El banner de preflight muestra todos los errores, warnings y checks. El job creado
        // no llegó a encolarse: se borra para no dejar jobs `pending` huérfanos.
        await firstValueFrom(this.data.deleteJob(jobId)).catch(() => undefined);
        return;
      }

      const started = await firstValueFrom(this.data.startJob(jobId));
      this.activeJob.set(started);
      this.liveJob.set(started);
      this.followLive.set(true);
      this.startLivePolling(workspace, jobId);
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    } finally {
      this.processing.set(false);
    }
  }

  private syncLivePolling(workspace: WorkspaceVm): void {
    const activeStatuses = new Set(['running', 'queued', 'retrying']);
    // Estados en los que el último job admite una acción (reanudar/reintentar) al recargar.
    const actionableStatuses = new Set(['paused', 'failed', 'cancelled', 'interrupted']);
    const { latestJobId, latestJobStatus } = workspace;

    if (latestJobId && latestJobStatus && activeStatuses.has(latestJobStatus)) {
      if (this.liveJobId !== latestJobId) {
        this.startLivePolling(workspace, latestJobId);
      }
      return;
    }

    if (!this.liveJobId) {
      this.stopLivePolling();
    }

    if (
      latestJobId &&
      latestJobStatus &&
      actionableStatuses.has(latestJobStatus) &&
      this.liveJob()?.id !== latestJobId
    ) {
      void firstValueFrom(this.data.jobProgress(latestJobId, workspace.project.name))
        .then((job) => this.liveJob.set(job))
        .catch(() => undefined);
    }
  }

  /** Job cuyos frames se muestran: el que está en vivo o, si no hay, el último del proyecto. */
  private previewJobId(workspace: WorkspaceVm): string | undefined {
    return this.liveJob()?.id ?? workspace.latestJobId;
  }

  private startLivePolling(workspace: WorkspaceVm, jobId: string): void {
    this.stopLivePolling();
    this.liveJobId = jobId;
    this.lastEnhancedCount = 0;
    this.liveSub = this.data
      .pollJobProgress(jobId, workspace.project.name, 1500, (error) => {
        this.previewError.set(error ? this.data.toErrorVm(error) : null);
        if (error instanceof OroyaApiError && error.options.status === 404) {
          this.stopLivePolling();
        }
      })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((job) => void this.onLiveTick(workspace, job));
  }

  private stopLivePolling(): void {
    this.liveSub?.unsubscribe();
    this.liveSub = undefined;
    this.liveJobId = undefined;
  }

  private async onLiveTick(workspace: WorkspaceVm, job: QueueJobVm): Promise<void> {
    this.liveJob.set(job);

    const previewDue = Date.now() - this.lastPreviewRefresh >= LIVE_PREVIEW_REFRESH_MS;
    if (job.framesProcessed > this.lastEnhancedCount && job.status === 'running' && previewDue) {
      this.lastEnhancedCount = job.framesProcessed;
      this.lastPreviewRefresh = Date.now();
      // Streaming: solo hay pares de muestra (pocos, con índices dispersos) y el último procesado.
      const latestIndex = job.streaming ? job.previewFrameIndex : job.framesProcessed - 1;
      try {
        const frames = await firstValueFrom(
          this.data.previewFrames(
            job.id,
            job.streaming
              ? { limit: 100, offset: 0 }
              : { limit: 24, offset: Math.max(job.framesProcessed - 24, 0) },
          ),
        );
        this.previewFrames.set(frames);
        if (this.followLive() && latestIndex !== undefined && latestIndex >= 0) {
          const preview = await firstValueFrom(this.data.compareFrame(job.id, latestIndex));
          this.selectedPreview.set(preview);
          this.selectedFrameIndex.set(latestIndex);
        }
      } catch {
        // Los frames pueden desaparecer entre el poll y el fetch; el próximo tick lo corrige.
      }
    }

    const terminal = new Set(['completed', 'failed', 'cancelled', 'interrupted', 'paused']);
    if (terminal.has(job.status)) {
      this.stopLivePolling();
      if (job.status === 'completed') {
        this.reload$.next(Date.now());
      }
      if (job.status !== 'paused') {
        this.liveJob.set(job);
      }
    }
  }

  isCollapsed(section: string): boolean {
    return this.collapsedSections().has(section);
  }

  toggleSection(section: string): void {
    this.collapsedSections.update((current) => {
      const next = new Set(current);
      if (!next.delete(section)) {
        next.add(section);
      }
      return next;
    });
  }

  /** "Focus": muestra el comparador a pantalla completa (Esc para salir). */
  async toggleFullscreen(element: HTMLElement): Promise<void> {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await element.requestFullscreen();
      }
    } catch {
      // Fullscreen puede no estar permitido (iframe, políticas del webview): no es crítico.
    }
  }

  toggleFollowLive(): void {
    this.followLive.update((value) => !value);
  }

  hasActiveLiveJob(): boolean {
    const job = this.liveJob();
    return job !== null && ['running', 'queued', 'paused', 'retrying'].includes(job.status);
  }

  async pauseActiveJob(): Promise<void> {
    await this.runJobAction(() => this.data.pauseJob(this.liveJob()!.id));
  }

  async retryActiveJob(workspace: WorkspaceVm): Promise<void> {
    const job = this.liveJob();
    if (!job) {
      return;
    }
    await this.runJobAction(() => this.data.retryJob(job.id));
    if (this.liveJob()?.status === 'queued') {
      this.followLive.set(true);
      this.startLivePolling(workspace, job.id);
    }
  }

  async resumeActiveJob(workspace: WorkspaceVm): Promise<void> {
    const job = this.liveJob();
    if (!job) {
      return;
    }
    await this.runJobAction(() => this.data.resumeJob(job.id));
    this.startLivePolling(workspace, job.id);
  }

  async cancelActiveJob(): Promise<void> {
    await this.runJobAction(() => this.data.cancelJob(this.liveJob()!.id));
    this.stopLivePolling();
    this.reload$.next(Date.now());
  }

  private async runJobAction(action: () => ReturnType<OroyaDataService['pauseJob']>): Promise<void> {
    if (!this.liveJob() || this.jobActionBusy()) {
      return;
    }

    try {
      this.jobActionBusy.set(true);
      const updated = await firstValueFrom(action());
      this.liveJob.set(updated);
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    } finally {
      this.jobActionBusy.set(false);
    }
  }

  failingChecks(preflight: JobPreflightResponse): string[] {
    const checks = (preflight.checks ?? {}) as Record<string, unknown>;
    return Object.entries(checks)
      .filter(([, passed]) => passed === false)
      .map(([name]) => name.replaceAll('_', ' '));
  }

  selectedModel(workspace: WorkspaceVm): ModelVm | undefined {
    const modelId = this.ensureControls(workspace).modelId;
    return (
      workspace.alternateModels.find((model) => model.id === modelId || model.slug === modelId) ??
      workspace.selectedModel
    );
  }

  selectModel(workspace: WorkspaceVm, model: ModelVm): void {
    if (!model.enabled || this.processing()) {
      return;
    }

    this.updateControls(workspace, { modelId: model.id });
  }

  setScale(workspace: WorkspaceVm, scale: WorkspaceVm['scale']): void {
    this.updateControls(workspace, {
      scale,
      exportResolution: scale,
    });
  }

  /** Codificación por GPU que funciona en este equipo, por códec (null = aún sin saber). */
  readonly gpuEncoders = signal<Record<string, boolean> | null>(null);

  gpuEncodingAvailable(codec: VideoCodec): boolean {
    return this.gpuEncoders()?.[codec] === true;
  }

  setEncoding(workspace: WorkspaceVm, patch: Partial<Pick<WorkspaceControls, 'codec' | 'quality' | 'gpuEncoding' | 'tenBit'>>): void {
    this.updateControls(workspace, patch);
  }

  setAiStrength(workspace: WorkspaceVm, value: string): void {
    this.updateControls(workspace, { aiStrength: this.clampPercent(value) });
  }

  setModelDenoise(workspace: WorkspaceVm, value: string): void {
    this.updateControls(workspace, { modelDenoise: this.clampPercent(value) });
  }

  readonly presets = QUALITY_PRESETS;

  /** Ajustes recomendados por tipo de video (modelo, escala, intensidad y filtros). */
  applyPreset(workspace: WorkspaceVm, presetId: string): void {
    const preset = QUALITY_PRESETS.find((item) => item.id === presetId);
    if (!preset) {
      return;
    }
    const model = workspace.alternateModels.find((item) => item.slug === preset.modelSlug);
    this.updateControls(workspace, {
      ...(model?.enabled ? { modelId: model.id } : {}),
      scale: preset.scale,
      exportResolution: preset.scale,
      aiStrength: preset.aiStrength,
      modelDenoise: preset.modelDenoise,
      denoise: 0,
      sharpen: 0,
      compressionCleanup: preset.compressionCleanup,
    });
  }

  /** Salida que muchos reproductores (los de Windows, navegadores) no decodifican con fluidez:
   * por encima del nivel H.264 5.1 van a saltos y el audio parece desfasado. */
  heavyOutput(workspace: WorkspaceVm, controls: WorkspaceControls): string | null {
    const factor = controls.exportResolution === '4x' ? 4 : controls.exportResolution === '2x' ? 2 : 1;
    const width = workspace.videoWidth * factor;
    const height = workspace.videoHeight * factor;
    const fps = !controls.interpolation || !workspace.interpolationAvailable
      ? workspace.videoFps
      : controls.interpolationTarget === '2x'
        ? workspace.videoFps * 2
        : controls.interpolationTarget;
    const limit = controls.codec === 'h265' ? H265_LEVEL_51_PIXEL_RATE : H264_LEVEL_51_PIXEL_RATE;
    if (!width || !height || width * height * fps <= limit) {
      return null;
    }
    return `${width}×${height} · ${Math.round(fps)} fps`;
  }

  setDenoise(workspace: WorkspaceVm, value: string): void {
    this.updateControls(workspace, { denoise: this.clampPercent(value) });
  }

  setSharpen(workspace: WorkspaceVm, value: string): void {
    this.updateControls(workspace, { sharpen: this.clampPercent(value) });
  }

  setCompressionCleanup(workspace: WorkspaceVm, checked: boolean): void {
    this.updateControls(workspace, { compressionCleanup: checked });
  }

  setFaceRestore(workspace: WorkspaceVm, checked: boolean): void {
    this.updateControls(workspace, { faceRestore: checked });
  }

  setFaceStrength(workspace: WorkspaceVm, value: string): void {
    this.updateControls(workspace, { faceStrength: this.clampPercent(value) });
  }

  /** Sin GFPGAN instalado no se envía activada (el preflight fallaría). */
  private faceRestoreConfig(
    workspace: WorkspaceVm,
    controls: WorkspaceControls,
  ): { enabled: boolean; strength: number } {
    return {
      enabled: controls.faceRestore && workspace.faceRestoreAvailable,
      strength: controls.faceStrength / 100,
    };
  }

  /** Sin RIFE instalado no se envía activada (el preflight fallaría). */
  private interpolationConfig(
    workspace: WorkspaceVm,
    controls: WorkspaceControls,
  ): { enabled: boolean; target_fps: InterpolationTarget } {
    return {
      enabled: controls.interpolation && workspace.interpolationAvailable,
      target_fps: controls.interpolationTarget,
    };
  }

  /** Objetivos posibles: 2x siempre; los fijos solo si superan los fps del video. */
  interpolationTargets(workspace: WorkspaceVm): { value: string; label: string }[] {
    const fps = workspace.videoFps;
    return [
      { value: '2x', label: translate('workspace.interpolationDouble', { fps: Math.round(fps * 2) }) },
      ...([48, 50, 60] as const)
        .filter((target) => target > fps + 0.5)
        .map((target) => ({ value: String(target), label: `${target} fps` })),
    ];
  }

  setInterpolation(workspace: WorkspaceVm, checked: boolean): void {
    this.updateControls(workspace, { interpolation: checked });
  }

  setInterpolationTarget(workspace: WorkspaceVm, value: string): void {
    const target: InterpolationTarget = value === '2x' ? '2x' : (Number(value) as 48 | 50 | 60);
    this.updateControls(workspace, { interpolationTarget: target });
  }

  setKeepAudio(workspace: WorkspaceVm, checked: boolean): void {
    this.updateControls(workspace, { keepAudio: checked });
  }

  setCompareMode(workspace: WorkspaceVm, mode: WorkspaceVm['compareMode']): void {
    this.updateControls(workspace, { compareMode: mode });
  }

  setZoom(workspace: WorkspaceVm, zoom: WorkspaceVm['zoom']): void {
    this.updateControls(workspace, { zoom });
  }

  filtersActive(workspace: WorkspaceVm): boolean {
    const controls = this.ensureControls(workspace);
    return controls.denoise > 0 || controls.sharpen > 0 || controls.compressionCleanup;
  }

  async selectPreviewFrame(workspace: WorkspaceVm, frameIndex: number): Promise<void> {
    const jobId = this.previewJobId(workspace);
    if (!jobId) {
      return;
    }

    try {
      this.previewError.set(null);
      if (this.hasActiveLiveJob()) {
        // Elegir un frame durante el procesamiento fija la vista (deja de seguir en vivo).
        this.followLive.set(false);
      }
      const preview = await firstValueFrom(this.data.compareFrame(jobId, frameIndex));
      this.selectedPreview.set(preview);
      this.selectedFrameIndex.set(frameIndex);
      if (!this.hasActiveLiveJob()) {
        this.updateControls(workspace, undefined, frameIndex);
      }
    } catch (error) {
      this.previewError.set(this.data.toErrorVm(error));
    }
  }

  previewBefore(workspace: WorkspaceVm): string {
    return this.selectedPreview()?.original.url ?? workspace.previewBefore;
  }

  previewAfter(workspace: WorkspaceVm): string {
    const preview = this.selectedPreview();
    const frameIndex = preview?.frame_index ?? null;
    const jobId = this.previewJobId(workspace);
    if (
      preview &&
      frameIndex !== null &&
      jobId &&
      this.filtersActive(workspace) &&
      this.data.backendStatus().isApi
    ) {
      const controls = this.ensureControls(workspace);
      return this.data.filteredPreviewUrl(jobId, frameIndex, {
        denoise: controls.denoise,
        sharpen: controls.sharpen,
        compressionCleanup: controls.compressionCleanup,
      });
    }

    return preview?.enhanced.url ?? workspace.previewAfter;
  }

  afterLabel(workspace: WorkspaceVm): string {
    const scale = this.ensureControls(workspace).scale;
    return scale === 'original'
      ? translate('workspace.enhanced')
      : translate('workspace.enhancedScale', { scale });
  }

  hasPreview(workspace: WorkspaceVm): boolean {
    return Boolean(this.previewAfter(workspace));
  }

  async takeSnapshot(workspace: WorkspaceVm): Promise<void> {
    const preview = this.selectedPreview();
    const imageUrl = preview?.enhanced.url ?? workspace.previewAfter;

    if (!imageUrl) {
      return;
    }

    try {
      await this.desktop.openUrl(imageUrl);
    } catch (error) {
      this.previewError.set(this.data.toErrorVm(error));
    }
  }

  private hydrateControls(workspace: WorkspaceVm): void {
    if (this.hydratedProjectId === workspace.project.id && this.controls()) {
      return;
    }

    if (this.hydratedProjectId !== workspace.project.id) {
      // Otro proyecto: el job en vivo del anterior ya no aplica.
      this.stopLivePolling();
      this.liveJob.set(null);
      this.activeJob.set(null);
      this.preflight.set(null);
    }
    this.hydratedProjectId = workspace.project.id;
    this.controls.set(this.toControls(workspace));
    this.saveState.set('idle');
    this.selectedPreview.set(null);
    this.selectedFrameIndex.set(null);
    this.previewFrames.set([]);
    this.previewError.set(null);
  }

  private async loadPreviewData(workspace: WorkspaceVm): Promise<void> {
    if (!workspace.latestJobId || !this.data.backendStatus().isApi) {
      return;
    }

    try {
      this.previewError.set(null);
      const recommended = await firstValueFrom(this.data.previewRecommended(workspace.latestJobId));
      const frames = await firstValueFrom(
        this.data.previewFrames(
          workspace.latestJobId,
          workspace.previewSparse
            ? { limit: 100, offset: 0 }
            : { limit: 24, offset: Math.max(recommended.frame_index - 12, 0) },
        ),
      );
      this.selectedPreview.set(recommended);
      this.selectedFrameIndex.set(recommended.frame_index);
      this.previewFrames.set(frames);
    } catch (error) {
      this.previewError.set(this.data.toErrorVm(error));
    }
  }

  private updateControls(
    workspace: WorkspaceVm,
    patch?: Partial<WorkspaceControls>,
    selectedFrame = this.selectedFrameIndex(),
  ): void {
    const current = this.ensureControls(workspace);
    this.controls.set({
      ...current,
      ...(patch ?? {}),
    });
    this.scheduleSave(workspace, selectedFrame);
  }

  private scheduleSave(workspace: WorkspaceVm, selectedFrame: number | null): void {
    this.saveState.set('saving');
    if (this.saveTimer) {
      clearTimeout(this.saveTimer);
    }

    this.saveTimer = setTimeout(() => {
      void this.persistControls(workspace, selectedFrame);
    }, 450);
  }

  private async persistControls(
    workspace: WorkspaceVm,
    selectedFrame = this.selectedFrameIndex(),
  ): Promise<void> {
    const controls = this.ensureControls(workspace);
    const model = this.selectedModel(workspace) ?? workspace.selectedModel;

    try {
      this.saveState.set('saving');
      await firstValueFrom(
        this.data.updateProject(workspace.project.id, {
          enhancement_config: {
            model_id: model.slug,
            scale: controls.scale,
            denoise: controls.denoise,
            sharpen: controls.sharpen,
            compression_cleanup: controls.compressionCleanup,
            face_restore: this.faceRestoreConfig(workspace, controls),
            interpolation: this.interpolationConfig(workspace, controls),
            ai_strength: controls.aiStrength,
            model_denoise: controls.modelDenoise,
          },
          export_config: this.exportConfig(controls),
          workspace_state: {
            selected_frame: selectedFrame ?? 0,
            compare_mode: controls.compareMode,
            zoom: controls.zoom,
            active_panel: 'inspector',
            timeline_position: selectedFrame ?? 0,
            inspector_open: true,
          },
        }),
      );
      this.saveState.set('saved');
    } catch (error) {
      this.saveState.set('error');
      this.error.set(this.data.toErrorVm(error));
    }
  }

  private ensureControls(workspace: WorkspaceVm): WorkspaceControls {
    const controls = this.controls();
    if (controls) {
      return controls;
    }

    const initial = this.toControls(workspace);
    this.controls.set(initial);
    return initial;
  }

  private exportConfig(controls: WorkspaceControls) {
    return {
      format: 'mp4' as const,
      keep_audio: controls.keepAudio,
      output_resolution: controls.exportResolution,
      file_name: controls.exportFileName.trim(),
      output_dir: controls.exportDir,
      codec: controls.codec,
      encoding: {
        codec: controls.codec,
        quality: controls.quality,
        hardware: controls.gpuEncoding,
        ten_bit: controls.tenBit && controls.codec === 'h265',
      },
      trim: controls.trimEnabled
        ? { start_seconds: controls.trimStart, end_seconds: controls.trimEnd }
        : null,
    };
  }

  readonly formatTrimTime = formatTrimTime;

  setTrimEnabled(workspace: WorkspaceVm, enabled: boolean): void {
    const current = this.ensureControls(workspace);
    const range =
      current.trimEnd > current.trimStart
        ? clampTrim(current.trimStart, current.trimEnd, workspace.videoDurationSeconds)
        : { start: 0, end: workspace.videoDurationSeconds };
    this.updateControls(workspace, { trimEnabled: enabled, trimStart: range.start, trimEnd: range.end });
  }

  setTrimTime(workspace: WorkspaceVm, edge: 'start' | 'end', input: HTMLInputElement): void {
    const current = this.ensureControls(workspace);
    const seconds = parseTrimTime(input.value);
    if (seconds === null) {
      input.value = formatTrimTime(edge === 'start' ? current.trimStart : current.trimEnd);
      return;
    }
    this.applyTrimEdge(workspace, edge, seconds);
  }

  /** Segundos del original del fotograma seleccionado en la vista previa, si hay uno. */
  currentFrameSeconds(workspace: WorkspaceVm): number | null {
    const index = this.selectedFrameIndex();
    if (index === null || index < 0 || !workspace.videoFps) {
      return null;
    }
    return workspace.previewTimeOffset + index / workspace.videoFps;
  }

  setTrimFromFrame(workspace: WorkspaceVm, edge: 'start' | 'end', seconds: number): void {
    this.applyTrimEdge(workspace, edge, seconds);
  }

  private applyTrimEdge(workspace: WorkspaceVm, edge: 'start' | 'end', seconds: number): void {
    const current = this.ensureControls(workspace);
    const duration = workspace.videoDurationSeconds;
    // Al mover un extremo, el otro se aparta lo justo para mantener la longitud mínima.
    const range =
      edge === 'start'
        ? clampTrim(seconds, Math.max(current.trimEnd, seconds + MIN_TRIM_SECONDS), duration)
        : clampTrim(Math.min(current.trimStart, seconds - MIN_TRIM_SECONDS), seconds, duration);
    this.updateControls(workspace, { trimStart: range.start, trimEnd: range.end });
  }

  /** Nombre que tendrá el archivo si no se elige otro (mismo criterio que el backend). */
  defaultExportName(workspace: WorkspaceVm, controls: WorkspaceControls): string {
    const base = workspace.project.name.replace(/\.(mp4|mov|mkv|avi|webm|m4v)$/i, '');
    const scale = controls.scale === 'original' ? '' : ` ${controls.scale}`;
    return `${base} (Oroya${scale})`;
  }

  setExportFileName(workspace: WorkspaceVm, value: string): void {
    this.updateControls(workspace, { exportFileName: value });
  }

  async chooseExportDir(workspace: WorkspaceVm, current: string): Promise<void> {
    const folder = this.desktop.isDesktop()
      ? await this.desktop.pickFolder(current || undefined)
      : await this.dialogs.prompt({
          title: translate('workspace.exportFolder'),
          label: translate('settings.exportsFolderPrompt'),
          value: current,
          confirmLabel: translate('common.save'),
        });
    if (folder !== null && folder !== current) {
      this.updateControls(workspace, { exportDir: folder });
    }
  }

  resetExportDir(workspace: WorkspaceVm): void {
    this.updateControls(workspace, { exportDir: '' });
  }

  private toControls(workspace: WorkspaceVm): WorkspaceControls {
    return {
      modelId: workspace.selectedModel.id,
      scale: workspace.scale,
      exportResolution: workspace.exportResolution,
      denoise: workspace.denoise,
      sharpen: workspace.sharpen,
      compressionCleanup: workspace.compressionCleanup,
      faceRestore: workspace.faceRestore.enabled,
      faceStrength: Math.round(workspace.faceRestore.strength * 100),
      interpolation: workspace.interpolation.enabled,
      interpolationTarget: workspace.interpolation.targetFps,
      aiStrength: workspace.aiStrength,
      modelDenoise: workspace.modelDenoise,
      codec: workspace.encoding.codec,
      quality: workspace.encoding.quality,
      gpuEncoding: workspace.encoding.hardware,
      tenBit: workspace.encoding.tenBit,
      keepAudio: workspace.keepAudio,
      exportFileName: workspace.exportFileName,
      exportDir: workspace.exportDir,
      trimEnabled: workspace.trim !== null,
      trimStart: workspace.trim?.start ?? 0,
      trimEnd: workspace.trim?.end ?? workspace.videoDurationSeconds,
      compareMode: workspace.compareMode,
      zoom: workspace.zoom,
    };
  }

  private clampPercent(value: string): number {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return 0;
    }

    return Math.min(Math.max(Math.round(parsed), 0), 100);
  }
}
