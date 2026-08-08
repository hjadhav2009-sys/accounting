# Template testing

Current-sample preview runs deterministic extraction and validation. “Test all” creates a durable PostgreSQL run before FastAPI schedules background work. Results persist per sample with extraction preview, validation, golden differences, outcome and duration; the UI polls progress and provides a clickable sample matrix. One sample failure is stored independently.

Golden outputs may specify normalized fields, item rows and separate tax buckets. Missing golden evidence yields REVIEW rather than false verification.
