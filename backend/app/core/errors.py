class OroyaVideoError(Exception):
    """Base application exception for predictable backend errors."""

    def __init__(
        self,
        message: str = "Oroya Video backend error",
        *,
        error_code: str = "oroya_video_error",
        status_code: int = 400,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}

    def to_response(self) -> dict[str, object]:
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details,
        }


class VideoFileNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Video file was not found.",
            error_code="video_file_not_found",
            status_code=404,
        )


class UnsupportedVideoFormatError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Only MP4, MOV and MKV files are supported in the MVP.",
            error_code="unsupported_video_format",
            status_code=400,
        )


class FFprobeNotAvailableError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "FFprobe is required to analyze video files.",
            error_code="ffprobe_not_available",
            status_code=503,
        )


class VideoProbeFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "The video metadata could not be analyzed.",
            error_code="video_probe_failed",
            status_code=422,
        )


class VideoStreamNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "No video stream was detected in the selected file.",
            error_code="video_stream_not_found",
            status_code=422,
        )


class VideoAssetNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Video asset was not found.",
            error_code="video_asset_not_found",
            status_code=404,
        )


class VideoImportFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Video could not be imported.",
            error_code="video_import_failed",
            status_code=500,
        )


class VideoCopyFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Video could not be copied to internal storage.",
            error_code="video_copy_failed",
            status_code=500,
        )


class InsufficientStorageSpaceError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Not enough storage space to copy the video.",
            error_code="insufficient_storage_space",
            status_code=400,
        )


class ProjectNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Project was not found.",
            error_code="project_not_found",
            status_code=404,
        )


class ProjectCreateFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Project could not be created.",
            error_code="project_create_failed",
            status_code=500,
        )


class ProjectUpdateFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Project could not be updated.",
            error_code="project_update_failed",
            status_code=500,
        )


class ProjectDeleteFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Project could not be deleted.",
            error_code="project_delete_failed",
            status_code=500,
        )


class VideoAssetFileMissingError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "The video file associated with this asset is missing.",
            error_code="video_asset_file_missing",
            status_code=409,
        )


class InvalidProjectConfigurationError(OroyaVideoError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="invalid_project_configuration",
            status_code=400,
        )


class AIModelNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "AI model was not found.",
            error_code="ai_model_not_found",
            status_code=404,
        )


class AIModelAlreadyExistsError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "AI model already exists.",
            error_code="ai_model_already_exists",
            status_code=409,
        )


class AIModelDisabledError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "AI model is disabled.",
            error_code="ai_model_disabled",
            status_code=409,
        )


class DefaultModelCannotBeDeletedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Default models cannot be deleted. Disable the model instead.",
            error_code="default_model_cannot_be_deleted",
            status_code=400,
        )


class AIModelCreateFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "AI model could not be created.",
            error_code="ai_model_create_failed",
            status_code=500,
        )


class AIModelUpdateFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "AI model could not be updated.",
            error_code="ai_model_update_failed",
            status_code=500,
        )


class JobNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Processing job was not found.",
            error_code="job_not_found",
            status_code=404,
        )


class JobInvalidStateError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "The job cannot perform this action in its current state.",
            error_code="job_invalid_state",
            status_code=409,
        )


class JobCreateFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Processing job could not be created.",
            error_code="job_create_failed",
            status_code=500,
        )


class JobStartFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Processing job could not be started.",
            error_code="job_start_failed",
            status_code=500,
        )


class JobCancelFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Processing job could not be cancelled.",
            error_code="job_cancel_failed",
            status_code=500,
        )


class JobDeleteFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Processing job could not be deleted.",
            error_code="job_delete_failed",
            status_code=500,
        )


class FFmpegNotAvailableError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "FFmpeg is required to extract video frames.",
            error_code="ffmpeg_not_available",
            status_code=503,
        )


class FrameExtractionFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Video frames could not be extracted.",
            error_code="frame_extraction_failed",
            status_code=422,
        )


class InsufficientTempStorageError(OroyaVideoError):
    def __init__(
        self,
        message: str = "Not enough temporary storage space to extract frames.",
    ) -> None:
        super().__init__(
            message,
            error_code="insufficient_temp_storage",
            status_code=400,
        )


class JobFramesNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "No extracted frames were found for this job.",
            error_code="job_frames_not_found",
            status_code=404,
        )


class JobPauseNotSupportedError(OroyaVideoError):
    def __init__(
        self,
        message: str = "Pausing during processing is not supported yet. Cancel the job instead.",
    ) -> None:
        super().__init__(
            message,
            error_code="job_pause_not_supported",
            status_code=409,
        )


class FrameEnhancerNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Frame enhancer was not found.",
            error_code="frame_enhancer_not_found",
            status_code=404,
        )


class FrameEnhancementFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Frames could not be enhanced.",
            error_code="frame_enhancement_failed",
            status_code=422,
        )


class OriginalFramesNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "No original frames were found for this job.",
            error_code="original_frames_not_found",
            status_code=404,
        )


class EnhancedFramesNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "No enhanced frames were found for this job.",
            error_code="enhanced_frames_not_found",
            status_code=404,
        )


class VideoEncodingFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Video could not be encoded from enhanced frames.",
            error_code="video_encoding_failed",
            status_code=422,
        )


class EnhancedFramesRequiredError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Enhanced frames are required before encoding video.",
            error_code="enhanced_frames_required",
            status_code=404,
        )


class EncodedVideoNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Encoded video was not found for this job.",
            error_code="encoded_video_not_found",
            status_code=404,
        )


class AudioMuxFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Audio could not be muxed into the encoded video.",
            error_code="audio_mux_failed",
            status_code=422,
        )


class MuxedVideoNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Muxed video was not found for this job.",
            error_code="muxed_video_not_found",
            status_code=404,
        )


class FinalExportFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Final export could not be created.",
            error_code="final_export_failed",
            status_code=422,
        )


class ExportAssetNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Export asset was not found.",
            error_code="export_asset_not_found",
            status_code=404,
        )


class InsufficientExportStorageError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Not enough storage space to create final export.",
            error_code="insufficient_export_storage",
            status_code=400,
        )


class PreviewNotAvailableError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Preview frames are not available for this job.",
            error_code="preview_not_available",
            status_code=404,
        )


class PreviewFrameNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Preview frame was not found.",
            error_code="preview_frame_not_found",
            status_code=404,
        )


class InvalidFrameIndexError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Frame index must be greater than or equal to zero.",
            error_code="invalid_frame_index",
            status_code=400,
        )


class PreviewFrameAccessDeniedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Preview frame path is outside the allowed job directory.",
            error_code="preview_frame_access_denied",
            status_code=403,
        )


class AIRuntimeNotAvailableError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "AI runtime is not available.",
            error_code="ai_runtime_not_available",
            status_code=503,
        )


class TorchNotAvailableError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "PyTorch is required to run Real-ESRGAN.",
            error_code="torch_not_available",
            status_code=503,
        )


class CUDANotAvailableError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "CUDA device was requested but is not available.",
            error_code="cuda_not_available",
            status_code=503,
        )


class AIModelFileNotFoundError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "AI model file was not found.",
            error_code="ai_model_file_not_found",
            status_code=404,
        )


class RealESRGANNotAvailableError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Real-ESRGAN dependencies are not available.",
            error_code="realesrgan_not_available",
            status_code=503,
        )


class RealESRGANDryRunFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Real-ESRGAN dry-run failed.",
            error_code="realesrgan_dry_run_failed",
            status_code=422,
        )


class RealESRGANEnhancementNotImplementedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Real-ESRGAN enhancement is not implemented for this operation yet.",
            error_code="realesrgan_enhancement_not_implemented",
            status_code=501,
        )


class RealESRGANModelLoadFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Real-ESRGAN model could not be loaded.",
            error_code="realesrgan_model_load_failed",
            status_code=422,
        )


class RealESRGANFrameProcessingFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "A frame could not be processed with Real-ESRGAN.",
            error_code="realesrgan_frame_processing_failed",
            status_code=422,
        )


class CUDAOutOfMemoryError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "CUDA ran out of memory while processing frames.",
            error_code="cuda_out_of_memory",
            status_code=507,
        )


class RealESRGANJobNotReadyError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Real-ESRGAN job requirements are not satisfied.",
            error_code="realesrgan_job_not_ready",
            status_code=409,
        )


class RealESRGANUnsupportedModelError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Selected Real-ESRGAN model is not supported by the current adapter.",
            error_code="realesrgan_unsupported_model",
            status_code=422,
        )


class JobPreflightFailedError(OroyaVideoError):
    def __init__(self, details: dict[str, object] | None = None) -> None:
        super().__init__(
            "Job preflight checks failed.",
            error_code="job_preflight_failed",
            status_code=409,
            details=details,
        )


class JobRetryNotAllowedError(OroyaVideoError):
    def __init__(self, details: dict[str, object] | None = None) -> None:
        super().__init__(
            "Job cannot be retried in its current state.",
            error_code="job_retry_not_allowed",
            status_code=409,
            details=details,
        )


class JobRecoveryFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Job recovery failed.",
            error_code="job_recovery_failed",
            status_code=500,
        )


class JobCleanupFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "Job temporary files could not be cleaned safely.",
            error_code="job_cleanup_failed",
            status_code=500,
        )


class ProcessTerminationFailedError(OroyaVideoError):
    def __init__(self) -> None:
        super().__init__(
            "The active process could not be terminated cleanly.",
            error_code="process_termination_failed",
            status_code=500,
        )
