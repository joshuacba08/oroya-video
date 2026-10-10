import { AsyncPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { NAIPipeline } from '@neuralangular/angular-ui/ai-pipeline';
import { NButton } from '@neuralangular/angular-ui/button';
import { NIcon } from '@neuralangular/angular-ui/icon';
import { NJobCard } from '@neuralangular/angular-ui/job-card';

import { Observable, firstValueFrom } from 'rxjs';

import { OroyaDataService } from '../../core/data/oroya-data.service';
import type { ApiErrorVm, QueueJobVm } from '../../core/models/oroya.models';

@Component({
  selector: 'app-queue-page',
  standalone: true,
  imports: [AsyncPipe, NAIPipeline, NButton, NIcon, NJobCard],
  templateUrl: './queue.page.html',
  styleUrl: './queue.page.css',
})
export class QueuePage {
  private readonly data = inject(OroyaDataService);
  private readonly router = inject(Router);

  readonly error = signal<ApiErrorVm | null>(null);
  readonly busyJobId = signal<string | null>(null);
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
