# Unverifiable items and [DATA REQUIRED] placeholders

Application source was not changed to close any of these gaps.

| Item | Why it could not be verified | Chapter treatment |
|---|---|---|
| Original dissertation Word file | Not in the repository, attachments, or GitHub | Standalone Chapter 4; insertion into front matter not performed. **[DATA REQUIRED]** |
| Canonical 30-variable ZDT at 5,000 evaluations | Campaign used 5 variables and budget 200 to keep Bayesian/hybrid feasible at 10 seeds | Ranking not generalised. **[DATA REQUIRED]** for a literature-scale sweep |
| Temporal-orchestrated runs | Docker overlay2 failed; Temporal was not started | UI runs labelled in-process. **[DATA REQUIRED]** |
| MinIO durable artefact storage | MinIO not running | Local PDFs are not durable artefacts. **[DATA REQUIRED]** |
| Milvus live retrieval | Milvus not running | Evidence tab empty; embeddings fallback not live-tested. **[DATA REQUIRED]** |
| Python API integration (testcontainers) | `tests/test_api_crud.py` skipped | Table 4.2. **[DATA REQUIRED]** |
| Web lint | `next lint` prompted interactive ESLint setup | Not evaluated. **[DATA REQUIRED]** |
| Admin automated tests | No test files | Not evaluated beyond exit 1 |
| User study / analyst confirmation of formalised specs | None conducted | RQ1 bounded to unit tests and persisted `run_spec`. **[DATA REQUIRED]** |
| Judge HTTP service in the workflow | Service not started | In-process `DeterministicScorer` used. **[DATA REQUIRED]** |
| Live impersonation test of `GSIP_DEMO_AUTH` | Source inspection plus unit membership tests only | Q5 partially met |
| Post-completion mutation of a sealed run | `seal_run` does not write the database | Q1 not met; no experiment needed to see the missing write |
| Original page numbers in the bound dissertation | Base document missing | Standalone PAGE field only. **[DATA REQUIRED]** |
| Personal / institutional title-page fields | Base document missing | Not invented. **[DATA REQUIRED]** |
