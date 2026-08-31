# Ingestion test fixtures

Small, synthetic files used by the ingestion adapter tests
(`tests/test_ingestion_*.py`). None of these contain real, confidential,
or copyrighted enterprise content — every file was generated fresh for
this repository using `python-docx`, `openpyxl`, `python-pptx`, `fpdf2`,
and plain text, with placeholder safety-procedure/incident-register style
content chosen only to exercise each format's structure (pages, headings,
tables, sheets/rows, slides/notes).

| File                              | Format | Purpose                                              |
|------------------------------------|--------|-------------------------------------------------------|
| `sample_procedure.pdf`             | PDF    | Two pages of real extractable text, for page/section preservation tests |
| `sample_blank.pdf`                 | PDF    | One page with no extractable text, for the quality-warning test |
| `sample_procedure.docx`            | DOCX   | Headings, paragraphs, and a table, for section/heading preservation tests |
| `sample_incident_register.xlsx`    | XLSX   | One sheet, header row, three data rows |
| `sample_incident_register.csv`     | CSV    | Same data as the XLSX fixture, as CSV |
| `sample_training.pptx`             | PPTX   | Two slides with titles, body text, and speaker notes |
| `sample_evacuation.rtf`            | RTF    | Minimal valid RTF with plain text |
| `sample_ppe_policy.txt`            | TXT    | Plain text |
| `unsupported.bin`                  | —      | Random bytes with an unrecognized extension, for the unsupported-type rejection test |

Regenerating them requires `fpdf2` (PDF only), which is not a project
dependency — it was used one-off to author `sample_procedure.pdf` and
`sample_blank.pdf` and is not needed to run the test suite.
