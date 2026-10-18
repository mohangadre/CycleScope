class CycleScopeError(Exception):
    status_code = 422
    code = "invalid_data"


class UnknownSymbol(CycleScopeError):
    status_code = 404
    code = "unknown_symbol"


class InsufficientData(CycleScopeError):
    code = "insufficient_data"


class ProviderUnavailable(CycleScopeError):
    status_code = 503
    code = "provider_unavailable"


class InvalidProviderData(CycleScopeError):
    status_code = 502
    code = "invalid_provider_data"


class AnalysisBusy(CycleScopeError):
    status_code = 503
    code = "analysis_busy"


class AnalysisNotFound(CycleScopeError):
    status_code = 404
    code = "analysis_not_found"


class ReplayMismatch(CycleScopeError):
    status_code = 409
    code = "replay_environment_mismatch"
