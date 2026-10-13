import { AsyncPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { NAIPipeline } from '@neuralangular/angular-ui/ai-pipeline';
import { NButton } from '@neuralangular/angular-ui/button';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { NJobCard } from '@neuralangular/angular-ui/job-card';

import { Observable, firstValueFrom } from 'rxjs';

import { OroyaDataService } from '../../core/data/oroya-data.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';
import type { ApiErrorVm, QueueJobVm } from '../../core/models/oroya.models';

@Component({
  selector: 'app-queue-page',
  standalone: true,
  imports: [AsyncPipe, NAIPipeline, NButton, NIcon, NJobCard, TranslatePipe],
  templateUrl: './queue.page.html',
  styleUrl: './queue.page.css',
})
export class QueuePage {
  private readonly data = inject(OroyaDataService);
  private readonly router = inject(Router);

  readonly error = signal<ApiErrorVm | null>(null);
  readonly busyJobId = signal<string | null>(null);
  readonly pausingAll = signal(false);
  readonly queue$ = this.data.pollQueue((error) =>
    this.error.set(error ? this.data.toErrorVm(error) : null),
  );

  badgeTone(job: QueueJobVm): 'primary' | 'success' | 'warning' | 'danger' | 'neutral' {
    return job.statusTone === 'processing' ? 'primary' : job.statusTone;
  }

  openJob(job: QueueJobVm): void {
    if (job.projectId) {
      void this.router.navigate(['/projects', job.projectId]);
    }
  }

  async pause(job: QueueJobVm): Promise<void> {
    await this.runJobAction(job.id, () => this.data.pauseJob(job.id));
  }

  async startOrResume(job: QueueJobVm): Promise<void> {
    await this.runJobAction(job.id, () =>
      job.status === 'paused' ? this.data.resumeJob(job.id) : this.data.startJob(job.id),
    );
  }

  resumableJobs(jobs: QueueJobVm[]): QueueJobVm[] {
    return jobs.filter((job) => job.status === 'paused' && job.canStart);
  }

  /** Reanuda en orden todos los pausados (vuelven al final de la cola). */
  async resumeAll(jobs: QueueJobVm[]): Promise<void> {
    const targets = this.resumableJobs(jobs);
    if (!targets.length || this.pausingAll()) {
      return;
    }
    this.pausingAll.set(true);
    this.error.set(null);
    try {
      for (const job of targets) {
        await firstValueFrom(this.data.resumeJob(job.id));
      }
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    } finally {
      this.pausingAll.set(false);
    }
  }

  pausableJobs(jobs: QueueJobVm[]): QueueJobVm[] {
    return jobs.filter((job) => job.canPause);
  }

  /** Pausa todos los jobs que el backend permite pausar (mejora en curso o en cola). */
  async pauseAll(jobs: QueueJobVm[]): Promise<void> {
    const targets = this.pausableJobs(jobs);
    if (!targets.length || this.pausingAll()) {
      return;
    }
    this.pausingAll.set(true);
    this.error.set(null);
    try {
      const results = await Promise.allSettled(
        targets.map((job) => firstValueFrom(this.data.pauseJob(job.id))),
      );
      const failure = results.find((result) => result.status === 'rejected');
      if (failure) {
        this.error.set(this.data.toErrorVm(failure.reason));
      }
    } finally {
      this.pausingAll.set(false);
    }
  }

  async cancel(job: QueueJobVm): Promise<void> {
    await this.runJobAction(job.id, () => this.data.cancelJob(job.id));
  }

  async retry(job: QueueJobVm): Promise<void> {
    await this.runJobAction(job.id, () => this.data.retryJob(job.id));
  }

  async cleanup(job: QueueJobVm): Promise<void> {
    await this.runJobAction(job.id, () => this.data.cleanupJobTemp(job.id));
  }

  private async runJobAction(jobId: string, action: () => Observable<unknown>): Promise<void> {
    try {
      this.error.set(null);
      this.busyJobId.set(jobId);
      await firstValueFrom(action());
    } catch (error) {
      this.error.set(this.data.toErrorVm(error));
    } finally {
      this.busyJobId.set(null);
    }
  }
}
