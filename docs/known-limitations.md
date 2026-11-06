# Known limitations

## AI quality

- 7–12B local models make mistakes: wrong dates, missed items, imprecise "partial" judgements. Evidence verification flags quotes that are not in the CV, but it cannot detect a **correct quote with a wrong interpretation**. Recruiters must check important facts against the CV ("show in CV").
- "Not found in the CV" means the CV is silent. It is never proof of absence.
- Long CVs are truncated to fit the context (≈12k characters at 8k context). A warning is shown. Chat retrieval still covers the whole CV.
- Extraction confidence is the share of items whose evidence is found in the text. It measures traceability, not correctness.
- Benchmark dataset is small (4 synthetic CVs, 7 matching cases). Use it to compare models on this machine, not as an absolute quality measure.
- Mainly tested on French and English CVs. Multi-column PDF layouts may produce interleaved text. OCR quality depends on the scan.
- Image files (JPG/PNG scans) are not accepted directly: convert them to PDF first. The vision model (moondream) is not used in the pipeline.

## Data minimisation

- Redaction is regex-based (common FR/EN wording such as "Date de naissance :", "Né le", "Nationalité :", "Situation familiale", street addresses). Unusual phrasings, other languages or information embedded in free text may not be detected.
- The **original document** (if kept) still contains everything, including any photo. Disable "Keep original documents" to delete it right after text extraction.
- Name, e-mail and phone are kept to identify the application.
- The model may still produce gender cues present in the CV wording (e.g. French feminine job titles). Prompts require neutral references.

## Deletion

- Files are overwritten with zeros before removal, and SQLite `secure_delete` zeroes freed pages. On **SSDs** (wear levelling, TRIM, over-provisioning), on journaling / copy-on-write filesystems, and with Windows features such as Volume Shadow Copies or File History, **physical data may persist**. This is not forensic erasure. Full-disk encryption (BitLocker) is the effective mitigation.
- Copies outside the application are not managed: the original e-mail attachment, the Downloads folder, Markdown exports, printouts, backups of the `data/` folder, antivirus quarantine, OS swap/hibernation files.
- Ollama does not write prompts to disk, but the model's KV cache stays in memory until the model is unloaded or its cache overwritten.
- Rotated application logs may contain the UUID of a deleted candidate (never content).
- Deleting a candidate deletes **every conversation that involved them**, including multi-candidate comparisons.
- Deletion reports keep the former UUID (pseudonymous, no remaining link) for audit.

## Security / organisation

- No authentication or role-based access: single-user tool for one Windows session.
- No encryption at rest inside the app (use BitLocker).
- No automatic retention policy: deletion is manual. The retention period is to be defined by the organisation.
- Backup/restore is not implemented. Backing up `data/` creates copies that must be managed under the same retention rules.
- Not a GDPR compliance guarantee: legal basis, candidate information, rights handling and DPIA (if required) are organisational decisions.

## Hardware

- With other heavy applications open, available RAM can drop below the configured floor (600 MB). Processing then stops with a clear message instead of swapping.
- `mistral-nemo` (12B) does not fit fully in 8 GB VRAM at 8k context and is noticeably slower.
- GPU metrics require `nvidia-smi`. Without it, GPU monitoring is hidden.

## UI

- The interface is available in French and English. AI-generated content (summaries, explanations) stays in the language of the CV or of the requirement, whatever the interface language.
- Word documents cannot be previewed before import (the extracted text is shown after import).
