from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErrorCodeInfo:
    code: str
    message: str
    http_status: int
    category: str
    recoverable: bool
    suggested_actions: list[str]


ERROR_CATALOG: dict[str, ErrorCodeInfo] = {
    "video_file_missing": ErrorCodeInfo(
        code="video_file_missing",
        message="Video file associated with this job is missing.",
        http_status=409,
        category="video",
        recoverable=True,
        suggested_actions=[
            "Restore the original video file or import it again.",
            "Verify the source path is still accessible.",
            "Retry the job after the video is available again.",
        ],
    ),
    "ffmpeg_not_available": ErrorCodeInfo(
        code="ffmpeg_not_available",
        message="FFmpeg is not available.",
        http_status=503,
        category="system",
        recoverable=True,
        suggested_actions=[
            "Install FFmpeg and ensure it is available in PATH.",
            "Restart the backend after FFmpeg is installed.",
        ],
    ),
    "ffprobe_not_available": ErrorCodeInfo(
        code="ffprobe_not_available",
        message="FFprobe is not available.",
        http_status=503,
        category="system",
        recoverable=True,
        suggested_actions=[
            "Install FFprobe together with FFmpeg.",
            "Verify PATH configuration and retry.",
        ],
    ),
    "ai_runtime_not_available": ErrorCodeInfo(
        code="ai_runtime_not_available",
        message="AI runtime is not available.",
        http_status=503,
        category="ai",
        recoverable=True,
        suggested_actions=[
            "Install PyTorch and Real-ESRGAN optional dependencies.",
            "Allow CPU fallback if GPU is not required.",
            "Verify CUDA drivers if GPU processing is expected.",
        ],
    ),
    "model_not_installed": ErrorCodeInfo(
        code="model_not_installed",
        message="Selected model is not installed.",
        http_status=409,
        category="ai",
        recoverable=True,
        suggested_actions=[
            "Copy the required model weights into storage/models.",
            "Refresh the model registry and validate the model again.",
        ],
    ),
    "cuda_not_available": ErrorCodeInfo(
        code="cuda_not_available",
        message="CUDA device was requested but is not available.",
        http_status=503,
        category="ai",
        recoverable=True,
        suggested_actions=[
            "Switch AI_DEVICE to auto or cpu.",
            "Verify GPU drivers and CUDA runtime availability.",
        ],
    ),
    "cuda_out_of_memory": ErrorCodeInfo(
        code="cuda_out_of_memory",
        message="CUDA ran out of memory while processing frames.",
        http_status=507,
        category="ai",
        recoverable=True,
        suggested_actions=[
            "Try using Real-ESRGAN x2 instead of x4.",
            "Reduce REALESRGAN_TILE_SIZE or enable tiling.",
            "Close other GPU-heavy applications.",
            "Retry with CPU only if processing time is acceptable.",
        ],
    ),
    "insufficient_temp_storage": ErrorCodeInfo(
        code="insufficient_temp_storage",
        message="Not enough temporary storage space is available.",
        http_status=400,
        category="storage",
        recoverable=True,
        suggested_actions=[
            "Free disk space in the temp storage volume.",
            "Clean old Oroya temporary files and retry.",
        ],
    ),
    "insufficient_export_storage": ErrorCodeInfo(
        code="insufficient_export_storage",
        message="Not enough export storage space is available.",
        http_status=400,
        category="storage",
        recoverable=True,
        suggested_actions=[
            "Free disk space in the exports volume.",
            "Delete old exports before retrying.",
        ],
    ),
    "frame_extraction_failed": ErrorCodeInfo(
        code="frame_extraction_failed",
        message="Video frames could not be extracted.",
        http_status=422,
        category="video",
        recoverable=True,
        suggested_actions=[
            "Validate the source video with ffprobe.",
            "Retry the job after checking FFmpeg output logs.",
        ],
    ),
    "frame_enhancement_failed": ErrorCodeInfo(
        code="frame_enhancement_failed",
        message="Frames could not be enhanced.",
        http_status=422,
        category="ai",
        recoverable=True,
        suggested_actions=[
            "Validate the selected AI model and runtime.",
            "Retry the job with mock engine or a smaller model.",
        ],
    ),
    "video_encoding_failed": ErrorCodeInfo(
        code="video_encoding_failed",
        message="Video could not be encoded from enhanced frames.",
        http_status=422,
        category="video",
        recoverable=True,
        suggested_actions=[
            "Verify enhanced frames are present and not corrupted.",
            "Retry the job after cleanup.",
        ],
    ),
    "audio_mux_failed": ErrorCodeInfo(
        code="audio_mux_failed",
        message="Audio could not be muxed into the encoded video.",
        http_status=422,
        category="export",
        recoverable=True,
        suggested_actions=[
            "Retry the job and review FFmpeg mux logs.",
            "Check whether the source video contains a valid audio stream.",
        ],
    ),
    "final_export_failed": ErrorCodeInfo(
        code="final_export_failed",
        message="Final export could not be created.",
        http_status=422,
        category="export",
        recoverable=True,
        suggested_actions=[
            "Check export storage free space.",
            "Retry the job or recreate the final export.",
        ],
    ),
    "job_cancelled": ErrorCodeInfo(
        code="job_cancelled",
        message="Job was cancelled.",
        http_status=409,
        category="job",
        recoverable=True,
        suggested_actions=[
            "Retry the job if processing should continue.",
            "Clean temporary files if they are no longer needed.",
        ],
    ),
    "job_interrupted": ErrorCodeInfo(
        code="job_interrupted",
        message="Job was interrupted during backend shutdown or restart.",
        http_status=409,
        category="job",
        recoverable=True,
        suggested_actions=[
            "Inspect diagnostics and retry the job.",
            "Clean temporary files if the previous run left partial outputs.",
        ],
    ),
    "job_preflight_failed": ErrorCodeInfo(
        code="job_preflight_failed",
        message="Job preflight checks failed.",
        http_status=409,
        category="job",
        recoverable=True,
        suggested_actions=[
            "Review the failed preflight checks.",
            "Fix missing dependencies or files before retrying.",
        ],
    ),
    "unknown_error": ErrorCodeInfo(
        code="unknown_error",
        message="Unexpected server error.",
        http_status=500,
        category="unknown",
        recoverable=False,
        suggested_actions=[
            "Review backend logs for the request_id.",
            "Retry only after inspecting the failure cause.",
        ],
    ),
}

ERROR_CODE_ALIASES = {
    "video_asset_file_missing": "video_file_missing",
    "ai_model_file_not_found": "model_not_installed",
    "realesrgan_job_not_ready": "job_preflight_failed",
    "realesrgan_frame_processing_failed": "frame_enhancement_failed",
    "realesrgan_model_load_failed": "frame_enhancement_failed",
    "torch_not_available": "ai_runtime_not_available",
    "job_invalid_state": "job_preflight_failed",
}


def resolve_error_code_info(error_code: str | None) -> ErrorCodeInfo:
    normalized_code = ERROR_CODE_ALIASES.get(error_code or "", error_code or "unknown_error")
    return ERROR_CATALOG.get(normalized_code, ERROR_CATALOG["unknown_error"])
