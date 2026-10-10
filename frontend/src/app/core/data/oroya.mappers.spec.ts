import type {
  DashboardResponse,
  ModelListResponse,
  QueueResponse,
} from '../api/api-types';
import { mapDashboard, mapModels, mapQueue } from './oroya.mappers';

describe('oroya mappers', () => {
  it('maps backend queue jobs into UI jobs and pipeline state', () => {
    const response = {
      items: [
        {
          job_id: 'job-1',
          project_id: 'project-1',
          project_name: 'Clip.mp4',
          status: 'running',
          current_stage: 'enhancing_frames',
          progress_percent: 42,
          model_slug: 'realesrgan-x2',
        },
      ],
    } as unknown as QueueResponse;

    const jobs = mapQueue(response);

    expect(jobs).toHaveLength(1);
    expect(jobs[0].projectName).toBe('Clip.mp4');
    expect(jobs[0].statusTone).toBe('processing');
    expect(jobs[0].pipeline.some((step) => step.status === 'running')).toBe(true);
  });

  it('takes queue actions from the backend instead of guessing from status', () => {
    const response = {
      items: [
        {
          job_id: 'job-paused',
          status: 'paused',
          current_stage: 'enhancing_frames',
          actions: { can_start: true, can_cancel: true, can_pause: false, can_retry: false },
        },
        { job_id: 'job-legacy', status: 'running', current_stage: 'extracting_frames' },
      ],
    } as unknown as QueueResponse;

    const [paused, legacy] = mapQueue(response);

    expect(paused.canStart).toBe(true);
    expect(paused.canPause).toBe(false);
    expect(paused.canCancel).toBe(true);
    expect(legacy.canPause).toBe(false);
    expect(legacy.canCancel).toBe(false);
  });

  it('keeps real dashboard project lists empty when the API is empty', () => {
    const response = {
      recent_projects: [],
      active_jobs: [{ id: 'job-1' }],
      system_status: {
        ready: false,
        warnings: ['GPU unavailable'],
      },
    } as unknown as DashboardResponse;

    const dashboard = mapDashboard(response);

    expect(dashboard.recentProjects.length).toBe(0);
    expect(dashboard.queueCount).toBe(1);
    expect(dashboard.system.ready).toBe(false);
    expect(dashboard.source).toBe('api');
  });

  it('keeps model uuid and slug separately', () => {
    const response = {
      items: [
        {
          id: '3b8c9e9c-379b-4666-b0d6-1f510b2003da',
          slug: 'realesrgan-x2',
          name: 'Real-ESRGAN x2',
          version: 'mvp',
          is_enabled: true,
          is_installed: true,
          scale_factor: 2,
        },
      ],
    } as unknown as ModelListResponse;

    const models = mapModels(response);

    expect(models[0].id).toBe('3b8c9e9c-379b-4666-b0d6-1f510b2003da');
    expect(models[0].slug).toBe('realesrgan-x2');
  });
});
