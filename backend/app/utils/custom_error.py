class CustomError(Exception):
    def __init__(self, message, status_code=400, code=None, issues=None, headers=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code or {
            400: "invalid_request",
            404: "not_found",
            422: "invalid_design",
        }.get(status_code, "internal_error")
        self.issues = issues or []
        self.headers = headers or {}

    def details(self):
        issues = [
            (
                {k: str(i[k])[:1000] for k in ("severity", "path", "message") if k in i}
                if isinstance(i, dict)
                else {"severity": "error", "message": str(i)[:1000]}
            )
            for i in self.issues[:50]
        ]
        return {
            "issues": issues,
            "total_count": len(self.issues),
            "truncated": len(self.issues) > 50,
        }
