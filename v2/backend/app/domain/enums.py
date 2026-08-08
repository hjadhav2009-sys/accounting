from enum import StrEnum


class ValidationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    REVIEW = "REVIEW"
    BLOCKED = "BLOCKED"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    ACCOUNTANT = "ACCOUNTANT"
    OPERATOR = "OPERATOR"
    REVIEWER = "REVIEWER"
    VIEWER = "VIEWER"


class Permission(StrEnum):
    DOCUMENT_UPLOAD = "document.upload"
    DOCUMENT_VIEW = "document.view"
    DOCUMENT_REVIEW = "document.review"
    TEMPLATE_CREATE = "template.create"
    TEMPLATE_APPROVE = "template.approve"
    BANK_PROCESS = "bank.process"
    MARKETPLACE_PROCESS = "marketplace.process"
    XML_EXPORT = "xml.export"
    EXCEL_EXPORT = "excel.export"
    MAPPING_EDIT = "mapping.edit"
    COMPANY_ADMIN = "company.admin"
    USER_ADMIN = "user.admin"


class ProcessingMode(StrEnum):
    LOCAL_ONLY = "LOCAL_ONLY"
    HYBRID_PRIVATE = "HYBRID_PRIVATE"
    FULL_CLOUD_ADMIN_OPT_IN = "FULL_CLOUD_ADMIN_OPT_IN"
