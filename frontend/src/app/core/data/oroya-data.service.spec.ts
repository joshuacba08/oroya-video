import { lastValueFrom } from 'rxjs';
import { vi } from 'vitest';

import { OroyaDataService } from './oroya-data.service';

describe('OroyaDataService', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('surfaces an offline error instead of falling back to mock data', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('offline')) as unknown as typeof fetch;
    const service = new OroyaDataService();

    await expect(lastValueFrom(service.dashboard())).rejects.toMatchObject({
      code: 'network_error',
    });
    expect(service.backendStatus().isOffline).toBe(true);
    expect(service.backendStatus().state).toBe('offline');
  });

  it('rejects a wrong backend instead of silently falling back to mock data', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          status: 'ok',
          service: 'argviz-api',
          version: '0.1.0',
        }),
        { status: 200 },
      ),
    ) as unknown as typeof fetch;
    const service = new OroyaDataService();

    await expect(lastValueFrom(service.dashboard())).rejects.toMatchObject({
      code: 'wrong_backend',
    });
    expect(service.backendStatus().wrongBackend).toBe(true);
  });

  it('imports a browser development path through probe, import, and project creation', async () => {
    const video = {
      id: 'video-1',
      file_name: 'local-test.mp4',
      duration_label: '00:10',
      duration_seconds: 10,
    };
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: 'ok',
            service: 'Oroya Video Backend',
            version: '0.1.0',
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            valid: true,
            file: { path: 'C:\\Videos\\local-test.mp4', name: 'local-test.mp4' },
            format: {},
            video: {},
            audio: { available: true },
            streams: [],
            warnings: [],
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            video,
            already_imported: false,
          }),
          { status: 201 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            project: {
              id: 'project-1',
              name: 'local-test.mp4',
              video_asset_id: 'video-1',
              status: 'draft',
              enhancement_config: { model_id: 'realesrgan-x2', scale: '2x' },
              export_config: { output_resolution: '2x' },
              workspace_state: {},
              created_at: '2026-06-25T00:00:00Z',
              updated_at: '2026-06-25T00:00:00Z',
              last_opened_at: null,
            },
            video,
          }),
          { status: 201 },
        ),
      ) as unknown as typeof fetch;
    const service = new OroyaDataService();

    const project = await lastValueFrom(
      service.importPickedVideo({ kind: 'browser-path', path: 'C:\\Videos\\local-test.mp4' }),
    );

    expect(project.id).toBe('project-1');
    expect(project.videoAssetId).toBe('video-1');
    expect(project.statusTone).toBe('neutral');
  });

  it('patches workspace controls on a project', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: 'ok',
            service: 'Oroya Video Backend',
            version: '0.1.0',
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            project: {
              id: 'project-1',
              name: 'local-test.mp4',
              video_asset_id: 'video-1',
              status: 'draft',
              enhancement_config: {
                model_id: 'realesrgan-x4',
                scale: '4x',
                denoise: 12,
                sharpen: 45,
                compression_cleanup: true,
              },
              export_config: {
                format: 'mp4',
                codec: 'h264',
                keep_audio: true,
                output_resolution: '4x',
              },
              workspace_state: {
                selected_frame: 10,
                compare_mode: 'slider',
                zoom: 'fit',
                active_panel: 'inspector',
                timeline_position: 10,
                inspector_open: true,
              },
              created_at: '2026-06-25T00:00:00Z',
              updated_at: '2026-06-25T00:00:00Z',
              last_opened_at: null,
            },
            video: {
              id: 'video-1',
              file_name: 'local-test.mp4',
              duration_label: '00:10',
              duration_seconds: 10,
            },
          }),
          { status: 200 },
        ),
      );
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    const service = new OroyaDataService();

    await lastValueFrom(
      service.updateProject('project-1', {
        enhancement_config: {
          model_id: 'realesrgan-x4',
          scale: '4x',
          denoise: 12,
          sharpen: 45,
          compression_cleanup: true,
        },
        export_config: {
          format: 'mp4',
          codec: 'h264',
          keep_audio: true,
          output_resolution: '4x',
        },
      }),
    );

    const [, patchCall] = fetchMock.mock.calls;
    expect(String(patchCall[0])).toContain('/projects/project-1');
    expect(patchCall[1]?.method).toBe('PATCH');
    expect(JSON.parse(String(patchCall[1]?.body))).toMatchObject({
      enhancement_config: {
        model_id: 'realesrgan-x4',
        scale: '4x',
      },
      export_config: {
        output_resolution: '4x',
      },
    });
  });

  it('resolves preview frame urls from the API', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: 'ok',
            service: 'Oroya Video Backend',
            version: '0.1.0',
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            job_id: 'job-1',
            items: [
              {
                index: 4,
                file_name: 'frame_00000004.png',
                original_available: true,
                enhanced_available: true,
                original_url: '/api/v1/jobs/job-1/preview/original/4',
                enhanced_url: '/api/v1/jobs/job-1/preview/enhanced/4',
              },
            ],
            total: 1,
            limit: 100,
            offset: 0,
          }),
          { status: 200 },
        ),
      ) as unknown as typeof fetch;
    const service = new OroyaDataService();

    const frames = await lastValueFrom(service.previewFrames('job-1'));

    expect(frames[0].index).toBe(4);
    expect(frames[0].enhancedUrl).toBe(
      'http://127.0.0.1:8001/api/v1/jobs/job-1/preview/enhanced/4',
    );
  });
});
