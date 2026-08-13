class RetryableIngestionError(RuntimeError):
    def __init__(self, message: str, *, retry_after_seconds: int = 30):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class UnsupportedPipelineError(RuntimeError):
    def __init__(self, pipeline_key: str):
        super().__init__(f"Unsupported ingestion pipeline: {pipeline_key}")
        self.pipeline_key = pipeline_key
