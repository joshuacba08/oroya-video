import type { components, paths } from './oroya-api.types';

export type ApiComponents = components;
export type ApiPaths = paths;

export type AIInstallProgressResponse = components['schemas']['AIInstallProgressResponse'];
export type AIInstallStartResponse = components['schemas']['AIInstallStartResponse'];
export type AIRuntimeStatusResponse = components['schemas']['AIRuntimeStatusResponse'];
export type AppStateResponse = components['schemas']['AppStateResponse'];
export type BootstrapResponse = components['schemas']['BootstrapResponse'];
export type CompareFrameResponse = components['schemas']['CompareFrameResponse'];
export type DashboardResponse = components['schemas']['DashboardResponse'];
export type DiagnosticsResponse = components['schemas']['DiagnosticsResponse'];
export type ExportDeleteResponse = components['schemas']['ExportDeleteResponse'];
export type GPUResponse = components['schemas']['GPUResponse'];
export type FFmpegDownloadStartResponse = components['schemas']['FFmpegDownloadStartResponse'];
export type FFmpegDownloadProgressResponse =
  components['schemas']['FFmpegDownloadProgressResponse'];
export type QueueItemResponse = components['schemas']['QueueItemResponse'];
export type ExportListResponse = components['schemas']['ExportListResponse'];
export type ExportOpenResponse = components['schemas']['ExportOpenResponse'];
export type HealthResponse = components['schemas']['HealthResponse'];
export type JobControlResponse = components['schemas']['JobControlResponse'];
export type JobCreateRequest = components['schemas']['JobCreateRequest'];
export type JobDetailResponse = components['schemas']['JobDetailResponse'];
export type JobListResponse = components['schemas']['JobListResponse'];
export type JobPreflightResponse = components['schemas']['JobPreflightResponse'];
export type JobProgressResponse = components['schemas']['JobProgressResponse'];
export type ModelRefreshResponse = components['schemas']['AIModelRefreshResponse'];
export type ModelListResponse = components['schemas']['AIModelListResponse'];
export type ModelDownloadStartResponse = components['schemas']['AIModelDownloadStartResponse'];
export type ModelDownloadProgressResponse =
  components['schemas']['AIModelDownloadProgressResponse'];
export type PreviewFrameListResponse = components['schemas']['PreviewFrameListResponse'];
export type ProjectCreateRequest = components['schemas']['ProjectCreateRequest'];
export type ProjectDetailResponse = components['schemas']['ProjectDetailResponse'];
export type ProjectListResponse = components['schemas']['ProjectListResponse'];
export type ProjectUpdateRequest = components['schemas']['ProjectUpdateRequest'];
export type ProjectWorkspaceResponse = components['schemas']['ProjectWorkspaceResponse'];
export type QueueResponse = components['schemas']['QueueResponse'];
export type SettingsResponse = components['schemas']['SettingsResponse'];
export type SettingsUpdateRequest = components['schemas']['SettingsUpdateRequest'];
export type SettingsUpdateResponse = components['schemas']['SettingsUpdateResponse'];
export type VideoImportResponse = components['schemas']['VideoImportResponse'];
export type VideoProbeResponse = components['schemas']['VideoProbeResponse'];
