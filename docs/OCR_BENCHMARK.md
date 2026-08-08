# OCR benchmark

Measured locally on 2026-08-08 with Tesseract 5.4.0.20240606 (`eng`), Windows x64, and five generated synthetic accounting pages: clean invoice, mixed GST, multiline description, table-like rows, and poorer JPEG scan.

| Measure | Result |
|---|---:|
| Engine startup/version query | 0.0295 s |
| Native extraction, five pages | 0.0143 s total |
| OCR page times | 1.5754, 1.6791, 1.7512, 1.6582, 1.6249 s |
| OCR average | 1.6578 s/page |
| OCR total | 8.2889 s |
| Critical numeric tokens | 13/13 exact (100%) |
| Table token set | 12/12 exact (100%) |
| Python-tracked peak allocation | 504,488 bytes |

Correct numeric confidence ranged from 0.9079 to 0.9684 and informs the review floor. This does not establish universal accuracy or claim Tesseract is best. A 90-degree synthetic page was not recognized correctly, so rotation correction is unsupported and routes to review.
