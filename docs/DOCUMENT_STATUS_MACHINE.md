# Document status machine

States are `UPLOADED`, `REGISTERED`, `DUPLICATE`, `EXTRACTING`, `OCR_REQUIRED`, `EXTRACTED`, `VALIDATING`, `VERIFIED`, `REVIEW`, `BLOCKED`, `FAILED`, and `ARCHIVED`. `DocumentStatusMachine` explicitly permits transitions; the repository also uses compare-and-set status updates to detect concurrent conflicts. Invalid jumps, such as UPLOADED directly to VERIFIED, fail.
