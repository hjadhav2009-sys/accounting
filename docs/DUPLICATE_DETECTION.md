# Duplicate detection

Hard duplicates use SHA-256 scoped to organization and company and return the existing document before a second file is stored. Business duplicates run only after supplier, type, invoice/reference number, date, and total exist; normalized values plus company ID form a SHA-256 accounting signature. A different file with a matching signature becomes REVIEW with `POSSIBLE_DUPLICATE` and the matching document ID.
