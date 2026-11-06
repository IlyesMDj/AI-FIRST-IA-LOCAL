# Contrats — Recruiter Copilot

Source de vérité partagée par tous les agents. Lire `CLAUDE.md` (règle d'or) avant tout.
Types Python : `backend/copilot/types.py`. Config : `backend/copilot/config.py`.

## Arborescence et propriétaires

| Chemin | Propriétaire | Rôle |
|---|---|---|
| `backend/copilot/types.py`, `config.py` | orchestrateur | contrat — ne pas modifier |
| `backend/copilot/extract.py` | A | PDF/TXT/image → `ExtractResult`. **Seul fichier qui importe `pymupdf`.** |
| `backend/copilot/redact.py` | A | texte → `RedactResult` (masquage déterministe, regex) |
| `backend/copilot/db.py` | A | SQLite : schéma + toutes les requêtes |
| `backend/copilot/erase.py` | A | effacement vérifiable → `ErasureProof` |
| `backend/copilot/llm.py` | B | client Ollama. **Seul fichier qui importe `ollama`.** |
| `backend/copilot/criteria.py` | B | critères depuis la fiche de poste |
| `backend/copilot/prompts.py` | B | prompts + `PROMPT_VERSION` |
| `backend/copilot/analysis.py` | B | analyse d'un CV + ancrage des citations |
| `backend/copilot/assist.py` | B | questions d'entretien, Q&A en streaming |
| `backend/copilot/api.py`, `worker.py` | D | FastAPI + file d'analyse en tâche de fond |
| `backend/tests/test_<module>.py` | propriétaire du module | pytest |
| `backend/fixtures/` | A et B (fichiers distincts, préfixés `a_` / `b_`) + `fiche-de-poste-demo.md` (B) | données **inventées** |
| `web/` | C | React + Vite + TS + Tailwind + shadcn/ui |
| `docs/` | orchestrateur | cycle de vie + registre |

Lancer les tests : `.venv\Scripts\python.exe -m pytest backend/tests -q` (depuis `hackathon/`). `backend/` est la racine d'import (`from copilot import ...`) : un `backend/conftest.py` vide l'assure.

## Module A — signatures

```python
# extract.py
def extract(filename: str, data: bytes) -> ExtractResult
#   .pdf avec couche texte → ok ; .pdf sans texte → needs_vision (pages rendues en PNG, en mémoire)
#   .pdf mixte (certaines pages sans texte) → ok + text + page_images des pages scannées + reason
#     "pages N,M scannées" : l'appelant transcrit ces images (vision) et AJOUTE le texte avant masquage.
#   .txt/.md → ok (utf-8, repli cp1252) ; .png/.jpg/.jpeg → needs_vision
#   autre / corrompu / > MAX_UPLOAD_BYTES → unsupported + reason (jamais un texte vide silencieux)

# redact.py
def redact(text: str) -> RedactResult
#   Catégories masquées : email, telephone, adresse, date_naissance, age, nationalite,
#   situation_familiale, lien_perso (linkedin/facebook/instagram…), numero_secu, photo (mention),
#   sante (RQTH, handicap, maladie, grossesse, groupe sanguin…), religion.
#   Espaces insécables (     ) normalisées en espace avant tout masquage.
#   Remplacement : "[<catégorie> retiré(e)]". Le NOM est conservé. Github/portfolio pro conservés.
#   Idempotent : redact(redact(t).text).text == redact(t).text

# db.py  — journal_mode=MEMORY + temp_store=MEMORY (aucun -journal/-wal ni temp sur disque : pas de copie
#          du CV hors du .db ; contrepartie assumée : un crash pendant une écriture peut corrompre la base),
#          foreign_keys=ON, secure_delete=ON
def connect(path: Path = DB_PATH) -> sqlite3.Connection     # check_same_thread=False, crée le dossier
def init(conn) -> None                                      # idempotent
def create_candidate(conn, display_name: str) -> str        # id = uuid4().hex, status='pending'
def set_status(conn, cid: str, status: Status, reason: str | None = None) -> None
def set_display_name(conn, cid: str, name: str) -> None
def save_document(conn, cid: str, redacted: RedactResult) -> None
def save_analysis(conn, cid: str, analysis: Analysis) -> None          # remplace l'existante ; écrit aussi evidence
def save_questions(conn, cid: str, qs: list[InterviewQuestion]) -> None # remplace les existantes
def candidate_exists(conn, cid: str) -> bool
def list_candidates(conn) -> list[dict]        # [{id, display_name, status, reason, created_at}] tri created_at
def get_candidate(conn, cid: str) -> dict | None
#   {id, display_name, status, reason, created_at, redacted_text, removed: {cat:n},
#    analysis: Analysis-as-dict | None, questions: [InterviewQuestion-as-dict]}
def get_job(conn) -> dict                      # {title, text, criteria: [Criterion-as-dict]}
def set_job(conn, title: str, text: str) -> None
def set_criteria(conn, criteria: list[Criterion]) -> None
def list_erasures(conn) -> list[dict]          # ErasureProof-as-dict, plus récent d'abord

# erase.py
def erase_candidate(conn, cid: str, db_path: Path = DB_PATH) -> ErasureProof
#   KeyError si id inconnu. Une transaction : DELETE candidates (CASCADE), puis VACUUM,
#   puis vérif : lignes restantes par table + recherche dans les octets du fichier .db
#   d'extraits (≥ 3 extraits de 24 car. du redacted_text + display_name, lus AVANT suppression).
#   Écrit dans erasure_log : hash, date, preuve. Jamais de texte ni de nom.
```

Tables : `job(id=1, title, text)`, `criteria(id PK, label, description, position)`,
`candidates(id PK, display_name, status, reason, created_at)`,
`documents(candidate_id PK FK CASCADE, redacted_text, removed_json)`,
`analyses(candidate_id PK FK CASCADE, json, model, prompt_version, created_at)`,
`evidence(id PK, candidate_id FK CASCADE, criterion_id, assessment, quote, start, end)`,
`questions(id PK, candidate_id FK CASCADE, question, rationale, criterion_id)`,
`erasure_log(id PK, candidate_id_hash, erased_at, proof_json)`.

## Module B — signatures

```python
# llm.py
def chat_json(model_key: str, system: str, user: str, schema: dict, images: list[bytes] | None = None) -> dict
#   format=<json schema> d'Ollama, temperature basse, think=False si supporté. LLMError si échec / JSON invalide.
def chat_stream(model_key: str, system: str, user: str) -> Iterator[str]
def vision_to_text(model_key: str, images: list[bytes]) -> str     # transcription fidèle, sans interprétation
def health() -> dict   # {ok: bool, models: [noms installés], missing: [clés de MODELS absentes]}
class LLMError(Exception)

# criteria.py
def load_job_text() -> tuple[str, str]                       # (title, text) depuis JOB_FILE_CANDIDATES
def suggest_criteria(job_text: str, model_key: str) -> list[Criterion]   # 4 à 8 critères, ids C1..Cn
DEFAULT_CRITERIA: list[Criterion]                            # repli si pas de LLM

# analysis.py
def analyze(redacted_text: str, criteria: list[Criterion], model_key: str) -> Analysis
#   1 seul appel LLM. Exactement 1 Evidence par critère (critère manquant → "non trouvé").
#   criterion_id hors liste → item écarté. Ancrage : quote re-cherchée dans redacted_text
#   (tolérance casse, espaces, apostrophes/guillemets typographiques, ligatures ; PAS de fuzzy) ;
#   introuvable → quote=None et dropped_quotes += 1 ; trouvée → quote = redacted_text[start:end].
#   Jamais de score global, de rang ni de recommandation.
def anchor(quote: str, text: str) -> tuple[int, int] | None

# assist.py
def interview_questions(redacted_text: str, analysis: Analysis, criteria: list[Criterion], model_key: str) -> list[InterviewQuestion]
#   5 à 8 questions, prioritairement sur critères "partiel"/"non trouvé" et points_to_clarify.
def answer_stream(redacted_text: str, question: str, model_key: str) -> Iterator[str]
#   Répond UNIQUEMENT à partir du CV fourni ; refuse de recommander/classer/décider.
```

Défense anti-injection (tous les prompts) : CV entre `<<<DEBUT_CV>>>` / `<<<FIN_CV>>>`, annoncé comme DONNÉE,
règle répétée après le bloc, tout texte `<<<...>>>` du CV remplacé par `[marqueur retiré]` dans la copie envoyée.

## API HTTP (module D ⇄ module C)

Base `http://127.0.0.1:8000/api`. Vite proxifie `/api`. JSON sauf mention. Erreurs : `{detail: str}`.

| Méthode | Route | Corps | Réponse |
|---|---|---|---|
| GET | `/health` | — | `{ok, models:[str], missing:[str], model_keys:{rapide,precis}}` |
| GET | `/job` | — | `{title, text, criteria:[Criterion]}` |
| PUT | `/job/criteria` | `{criteria:[Criterion]}` | `{criteria:[Criterion]}` |
| POST | `/job/criteria/suggest` | `{model?}` | `{criteria:[Criterion]}` (proposition, non enregistrée) |
| POST | `/candidates` | multipart : champ `files` répété (`files: list[UploadFile]`), champ `model?` | `[{id, display_name, status}]` — analyse en file, 1 à la fois |
| GET | `/candidates` | — | `[{id, display_name, status, reason, created_at}]` (ordre d'import, **jamais par score**) |
| GET | `/candidates/{id}` | — | voir `db.get_candidate` |
| POST | `/candidates/{id}/reanalyze` | `{model?}` | `{status}` |
| POST | `/candidates/{id}/questions` | `{model?}` | `{questions:[InterviewQuestion]}` |
| POST | `/candidates/{id}/ask` | `{question, model?}` | `text/event-stream` : `data: {"token": "..."}` … `data: {"done": true}` ; en cas d'échec `data: {"error": "..."}` — **non stocké** |
| GET | `/compare` | — | `{criteria:[Criterion], candidates:[{id, display_name, status, cells:{C1:{assessment, quote}}}]}` |
| DELETE | `/candidates/{id}` | — | `ErasureProof` |
| GET | `/erasures` | — | `[ErasureProof]` |

`model` ∈ `"rapide" | "precis"` (défaut `rapide`). Le front interroge `/candidates` toutes les 2 s tant qu'un statut est `pending`/`analyzing`.

## Règles transverses
- Aucune ressource réseau externe (polices, CDN, télémétrie) : tout doit marcher Wi-Fi coupé.
- Le front ne persiste aucune donnée candidat (pas de localStorage/sessionStorage/IndexedDB).
- Pas de nom, texte de CV ni question RH dans les logs (`print`, `logging`, logs uvicorn d'accès OK car ids opaques).
- Aucun tri, score, rang ou mot « recommandé / meilleur / à retenir » dans l'API ni l'UI.
