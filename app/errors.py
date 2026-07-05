from app.models import ValidationIssue


class ProcessingError(Exception):
    def __init__(self, issues: tuple[ValidationIssue, ...]):
        if not issues:
            raise ValueError("ProcessingError requires at least one issue")
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))
