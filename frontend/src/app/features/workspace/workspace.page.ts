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
import { DesktopService } from '../../core/desktop/desktop.service';
import type {
  ApiErrorVm,
  ModelVm,
  PreviewFrameVm,
  QueueJobVm,
  WorkspaceVm,
} from '../../core/models/oroya.models';
import { OvVideoPreviewComponent } from '../../shared/ui/ov-video-preview.component';

type WorkspaceControls = {
  modelId: string;
  scale: WorkspaceVm['scale'];
  exportResolution: WorkspaceVm['exportResolution'];
  denoise: number;
  sharpen: number;
  compressionCleanup: boolean;
  keepAudio: boolean;
  compareMode: WorkspaceVm['compareMode'];
  zoom: WorkspaceVm['zoom'];
};

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
  private readonly destroyRef = inject(DestroyRef);
  private saveTimer: ReturnType<typeof setTimeout> | undefined;
  private hydratedProjectId: string | undefined;
  private liveSub: Subscription | undefined;
  private liveJobId: string | undefined;
  private lastEnhancedCount = 0;
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
          },
          export_config: {
            format: 'mp4',
            codec: 'h264',
            keep_audio: controls.keepAudio,
            output_resolution: controls.exportResolution,
          },
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

    if (job.framesProcessed > this.lastEnhancedCount && job.status === 'running') {
      this.lastEnhancedCount = job.framesProcessed;
      try {
        const frames = await firstValueFrom(
          this.data.previewFrames(job.id, {
            limit: 24,
            offset: Math.max(job.framesProcessed - 24, 0),
          }),
        );
        this.previewFrames.set(frames);
        if (this.followLive()) {
          const latestIndex = job.framesProcessed - 1;
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

  setDenoise(workspace: WorkspaceVm, value: string): void {
    this.updateControls(workspace, { denoise: this.clampPercent(value) });
  }

  setSharpen(workspace: WorkspaceVm, value: string): void {
    this.updateControls(workspace, { sharpen: this.clampPercent(value) });
  }

  setCompressionCleanup(workspace: WorkspaceVm, checked: boolean): void {
    this.updateControls(workspace, { compressionCleanup: checked });
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
      this.selectedFrameIndex.set(frameIndex);
      const preview = await firstValueFrom(this.data.compareFrame(jobId, frameIndex));
      this.selectedPreview.set(preview);
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
    const frameIndex = this.selectedFrameIndex();
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
      const frameOffset = Math.max(recommended.frame_index - 12, 0);
      const frames = await firstValueFrom(
        this.data.previewFrames(workspace.latestJobId, {
          limit: 24,
          offset: frameOffset,
        }),
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
          },
          export_config: {
            format: 'mp4',
            codec: 'h264',
            keep_audio: controls.keepAudio,
            output_resolution: controls.exportResolution,
          },
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

  private toControls(workspace: WorkspaceVm): WorkspaceControls {
    return {
      modelId: workspace.selectedModel.id,
      scale: workspace.scale,
      exportResolution: workspace.exportResolution,
      denoise: workspace.denoise,
      sharpen: workspace.sharpen,
      compressionCleanup: workspace.compressionCleanup,
      keepAudio: workspace.keepAudio,
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
