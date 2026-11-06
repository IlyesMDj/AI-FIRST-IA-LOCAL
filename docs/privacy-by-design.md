# Privacy by design

This document states what the application **actually guarantees**, how, and what it does not guarantee. It is not a GDPR compliance certificate: local processing is one technical measure. Purposes, legal basis, retention periods, information of candidates and access rights remain the organisation's responsibility (see [data/registre-simplifie.md](data/registre-simplifie.md)).

## Guarantees and how they are enforced

| Guarantee | Mechanism | Verified by |
|---|---|---|
| Inference is local | Ollama client refuses non-loopback hosts. No other AI SDK is installed or imported | `test_external_ai_endpoint_rejected`, `test_no_telemetry_dependencies`, `test_only_local_inference_endpoint_called` |
| Works offline | No runtime network dependency. Fonts are system fonts (no Google Fonts fetch). Next.js telemetry disabled | `test_full_pipeline_offline` (all non-loopback sockets and DNS blocked) |
| No telemetry / analytics | None included. `NEXT_TELEMETRY_DISABLED=1` + `next telemetry disable` | `test_no_telemetry_dependencies` |
| Servers not exposed on the network | Uvicorn and Next bind `127.0.0.1`. Docker publishes on `127.0.0.1` only | configuration |
| Data minimisation | Redaction of birth date, age, family status, nationality, gender, religion, health, social-security number, address and photo references **before** storage, embeddings and AI. The extraction schema has no field for these. Post-filter on extracted skills. Photos are never extracted from PDFs | `test_sensitive_data_redacted_before_storage_and_llm`, `test_redaction_keeps_professional_info` |
| No personal data in logs | Logs and lifecycle events carry ids, counts, durations and model names only (forbidden keys filtered) | `test_cv_content_not_in_logs` |
| Candidate isolation | Retrieval requires an explicit candidate set and filters in SQL before similarity. Conversations are bound to their candidates | `test_candidate_isolation_in_retrieval`, `test_search_requires_scope` |
| Human decision | No score, rank, winner or recommendation in any API or prompt output. Prompts forbid it. "Not found" is explicitly not proof of absence | `test_job_and_analysis` (payload scan), prompt rules |
| Explainability | Every extracted item and every assessment carries verbatim evidence verified against the CV, with section and offsets; "show in CV" highlight | `test_import_pdf_and_extract`, `test_job_and_analysis` |
| Verifiable deletion | Transaction + secure_delete + WAL checkpoint + file overwrite/removal + post-checks + report | `test_delete_candidate`, `test_deletion_removes_files_embeddings_and_retrieval` (incl. raw DB byte scan) |
| Protection against manipulation by CV content | Prompt-injection detection, nonce delimiters, schema-constrained output, evidence verification | `test_prompt_injection_detected_and_flagged`, `test_document_delimiters_cannot_be_spoofed`, real-model integration test |

## Data categories

| Kept | Why |
|---|---|
| Name, e-mail, phone | Identify the application and contact the candidate |
| Experience, education, skills, languages, certifications, projects | Job-related analysis |
| Original document (configurable) | Verification against the source, re-processing. Can be disabled (`keep_original_files=false`): the file is deleted right after text extraction |

| Removed / never extracted | How |
|---|---|
| Birth date, age, family status, children, nationality, gender, religion, health / disability, social-security number, home address, photo | Regex redaction before storage (FR/EN wording), schema without fields, prompt rules, skill post-filter |
| Protected characteristics inferred by the model | Prompt rules ("never infer"), neutral references (no gendered pronouns), interview question filter |

## Where data flows

See [data-lifecycle.md](data-lifecycle.md) and [data/data-flow.md](data/data-flow.md).

## Limitations (summary)

Full list: [known-limitations.md](known-limitations.md).

- Redaction is heuristic: unusual phrasings can slip through. The original document (if kept) still contains everything.
- No user accounts or role-based access in this version: anyone with access to the Windows session can open the app.
- Data at rest is not encrypted by the application. Enable BitLocker.
- Deletion is not forensic on SSDs. Copies outside the app (mail, Downloads, backups) are out of scope.
- The LLM can still make mistakes. Evidence verification reduces but does not eliminate them.
