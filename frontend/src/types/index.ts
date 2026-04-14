export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: Date;
  // Multimodal support
  has_image?: boolean;
  image_data?: string;  // Base64 encoded image
  image_format?: string;  // Image format (png, jpeg, etc.)
  image_id?: string;
  image_ids?: string[];
  image_url?: string;
  image_urls?: string[];
  has_file?: boolean;
  file_name?: string;
  file_format?: string;
  has_audio?: boolean;
  audio_url?: string;
  audio_urls?: string[];
  has_video?: boolean;
  video_url?: string;
  video_urls?: string[];
  reasoning_content?: string;
  final_content?: string;
  tool_traces?: ToolTrace[];
}

export interface ToolTrace {
  id?: string;
  name?: string;
  arguments?: string;
  output?: string;
  elapsed_ms?: number;
  ts?: string;
}

export interface SourceDocument {
  content: string;
  source: string;
  score?: number;
}

export interface ChatResponse {
  content: string;
  session_id: string;
  sources: SourceDocument[];
  metadata: {
    model?: string;
    use_rag?: boolean;
    message_count?: number;
    has_file?: boolean;
    has_image?: boolean;
    has_audio?: boolean;
    has_video?: boolean;
    image_id?: string;
    image_ids?: string[];
    image_count?: number;
    audio_url?: string;
    audio_urls?: string[];
    audio_count?: number;
    audio_prefetched_count?: number;
    video_url?: string;
    video_urls?: string[];
    video_count?: number;
    multimodal_mode?: string;
    deploy_profile?: string;
    requested_deploy_profile?: string;
    profile_source?: string;
    enable_thinking?: boolean;
    enable_tool_calling?: boolean;
    enable_structured_output?: boolean;
    requested_enable_thinking?: boolean;
    requested_enable_tool_calling?: boolean;
    requested_structured_output?: boolean;
    response_format_type?: string;
    response_schema_name?: string;
    mode_warnings?: string[];
    reasoning_content?: string;
    final_content?: string;
    tool_traces?: ToolTrace[];
    tool_trace_count?: number;
  };
}

export interface DocumentUploadResponse {
  document_id: string;
  filename: string;
  status: string;
  chunk_count: number;
}

export interface ChatImageUploadResponse {
  image_id: string;
  image_format: string;
  size_bytes: number;
  width: number;
  height: number;
  expires_in_seconds: number;
}

export interface ChatAudioUploadResponse {
  audio_id: string;
  audio_format: string;
  media_type: string;
  size_bytes: number;
  file_name?: string;
  expires_in_seconds: number;
}

export interface ChatVideoUploadResponse {
  video_id: string;
  video_format: string;
  media_type: string;
  size_bytes: number;
  file_name?: string;
  expires_in_seconds: number;
}

export interface DocumentBatchUploadResponse {
  documents: DocumentUploadResponse[];
  total_files: number;
  success_count: number;
  failed_count: number;
  total_chunks: number;
}

export interface CapabilityCheckResult {
  name: string;
  passed: boolean;
  detail: string;
  latency_s: number;
}

export interface PerformanceBenchmarkSummary {
  run_id: string;
  generated_at?: string | null;
  model?: string | null;
  concurrency?: number | null;
  requests?: number | null;
  stream?: boolean | null;
  success_rate_percent: number;
  p95_latency_s: number;
  avg_latency_s: number;
  request_throughput_rps: number;
  completion_token_throughput_tps: number;
  p95_ttft_s: number;
}

export interface PerformanceStrictSuiteSummary {
  run_id: string;
  generated_at?: string | null;
  overall: string;
  pass_count: number;
  fail_count: number;
  total: number;
}

export interface PerformanceCapabilitySummary {
  run_id: string;
  generated_at?: string | null;
  passed: number;
  total: number;
  checks: CapabilityCheckResult[];
}

export interface PerformanceOverviewResponse {
  generated_at: string;
  provider: string;
  active_model: string;
  deploy_profile: string;
  vllm_connected: boolean;
  vllm_reason?: string | null;
  latest_benchmark?: PerformanceBenchmarkSummary | null;
  latest_strict_suite?: PerformanceStrictSuiteSummary | null;
  latest_capability_probe?: PerformanceCapabilitySummary | null;
}

export interface ChatModeConfigResponse {
  provider: string;
  deploy_profile: string;
  supports_image: boolean;
  supports_audio: boolean;
  supports_video: boolean;
  supports_thinking: boolean;
  supports_tool_calling: boolean;
  supports_structured_output: boolean;
  available_profiles: string[];
  configured_profile?: string | null;
  runtime_profile_override?: string | null;
  profile_source?: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  model_loaded: boolean;
  embedding_loaded: boolean;
  vector_db_ready: boolean;
}

export interface DocumentInfo {
  document_id: string;
  source: string;
  chunk_count: number;
  file_type: string | null;
  created_at: string | null;
}

export interface DocumentListResponse {
  documents: DocumentInfo[];
  total_count: number;
  total_chunks: number;
}

export interface DocumentDeleteResponse {
  deleted: boolean;
  document_id: string;
  chunks_removed: number;
}
