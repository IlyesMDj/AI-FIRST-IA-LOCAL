/**
 * Mode démo : back-end simulé EN MÉMOIRE (rien n'est persisté, tout disparaît au rechargement).
 * Toutes les personnes et tous les CV ci-dessous sont INVENTÉS.
 */
import type {
  Api,
  Assessment,
  CandidateDetail,
  CandidateSummary,
  Criterion,
  ErasureProof,
  Evidence,
  InterviewQuestion,
  Job,
  ModelKey,
  Status,
} from "./api";
import { ApiError } from "./api";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
const MODEL_NAMES: Record<ModelKey, string> = { rapide: "ministral-3:3b", precis: "ministral-3:8b" };
const PROMPT_VERSION = 3;

let job: Job = {
  title: "Développeur·se Python confirmé·e — Atelier Nova",
  text: `Atelier Nova (PME, 45 personnes, Lyon) conçoit des outils de planification pour les ateliers de fabrication.

Missions
- Concevoir et faire évoluer nos API métier en Python (FastAPI).
- Modéliser les données (PostgreSQL) et optimiser les requêtes.
- Écrire des tests automatisés et participer aux revues de code.
- Contribuer à l'industrialisation (Docker, intégration continue).

Profil recherché
- Au moins 4 ans d'expérience en développement Python.
- Maîtrise d'un framework web Python (FastAPI, Django ou Flask).
- Bonne pratique des tests (pytest) et de la qualité de code.
- À l'aise avec SQL.
- Goût pour le travail en équipe et la transmission.`,
  criteria: [
    { id: "C1", label: "Expérience Python ≥ 4 ans", description: "Développement Python en contexte professionnel." },
    { id: "C2", label: "Framework web Python", description: "FastAPI, Django ou Flask." },
    { id: "C3", label: "Tests automatisés", description: "pytest, couverture, TDD, qualité de code." },
    { id: "C4", label: "SQL / PostgreSQL", description: "Modélisation, requêtes, optimisation." },
    { id: "C5", label: "Docker / intégration continue", description: "Conteneurisation, pipelines CI/CD." },
    { id: "C6", label: "Travail en équipe", description: "Revues de code, transmission, collaboration." },
  ],
};

interface Template {
  text: string;
  removed: Record<string, number>;
  summary: string;
  ev: { id: string; a: Assessment; q?: string }[];
  clarify: string[];
  dropped: number;
}

const TEMPLATES: Template[] = [
  {
    text: `Camille Martin
Développeuse back-end Python
[email retiré] · [telephone retiré] · [adresse retiré]
github.com/cmartin-dev

EXPÉRIENCE
2021 – aujourd'hui · Développeuse Python senior — Logistika (Grenoble)
- Conception d'une API de suivi de colis en FastAPI (40 endpoints, 2 M requêtes/jour).
- Migration d'un schéma PostgreSQL de 120 tables, réécriture des requêtes lentes (gain ×4).
- Mise en place de pytest et d'une couverture de 85 % sur le cœur métier.
- Animation des revues de code hebdomadaires, accompagnement de deux alternants.

2018 – 2021 · Développeuse Python — Studio Mélusine (Lyon)
- Back-office Django pour un réseau de 30 boutiques.
- Scripts d'import de données et tâches planifiées (Celery).

FORMATION
Master informatique — Université Grenoble Alpes

COMPÉTENCES
Python, FastAPI, Django, PostgreSQL, pytest, Git, Linux
Langues : anglais courant

DIVERS
[situation_familiale retiré] · [age retiré]`,
    removed: { email: 1, telephone: 1, adresse: 1, situation_familiale: 1, age: 1 },
    summary:
      "Développeuse back-end avec environ 7 ans d'expérience Python (2018 à aujourd'hui), d'abord sur Django puis sur FastAPI. Le CV décrit une API à fort trafic, un travail approfondi sur PostgreSQL, une démarche de tests structurée et un rôle d'animation des revues de code. L'outillage Docker / CI n'est pas mentionné explicitement.",
    ev: [
      { id: "C1", a: "présent", q: "2018 – 2021 · Développeuse Python — Studio Mélusine (Lyon)" },
      { id: "C2", a: "présent", q: "Conception d'une API de suivi de colis en FastAPI (40 endpoints, 2 M requêtes/jour)." },
      { id: "C3", a: "présent", q: "Mise en place de pytest et d'une couverture de 85 % sur le cœur métier." },
      { id: "C4", a: "présent", q: "Migration d'un schéma PostgreSQL de 120 tables, réécriture des requêtes lentes (gain ×4)." },
      { id: "C5", a: "non trouvé" },
      { id: "C6", a: "présent", q: "Animation des revues de code hebdomadaires, accompagnement de deux alternants." },
    ],
    clarify: ["Pratique de Docker et de l'intégration continue non décrite.", "Taille de l'équipe chez Logistika non précisée."],
    dropped: 0,
  },
  {
    text: `Yanis Benali
Ingénieur logiciel
[email retiré] · [lien_perso retiré]
gitlab.com/ybenali

PARCOURS
2023 – aujourd'hui · Ingénieur logiciel — Datafleur (Paris, télétravail partiel)
- Développement de microservices Python (Flask) pour la tarification.
- Conteneurisation de 12 services avec Docker, pipelines GitLab CI.
- Quelques tests unitaires sur les modules de calcul.

2020 – 2023 · Développeur full-stack — Agence Pixelis
- Sites et applications en PHP / Symfony et JavaScript.
- Premiers scripts Python d'automatisation (extraction de rapports).

FORMATION
BUT informatique — IUT de Nantes

OUTILS
Python, Flask, Docker, GitLab CI, MySQL, Vue.js
[nationalite retiré] · [date_naissance retiré]`,
    removed: { email: 1, lien_perso: 1, nationalite: 1, date_naissance: 1 },
    summary:
      "Ingénieur logiciel dont l'expérience Python professionnelle principale démarre en 2023 (Flask, microservices), précédée de trois ans en PHP / JavaScript avec quelques scripts Python. Points solides sur Docker et GitLab CI. Les tests sont évoqués de manière limitée ; la base de données mentionnée est MySQL.",
    ev: [
      { id: "C1", a: "partiel", q: "Développement de microservices Python (Flask) pour la tarification." },
      { id: "C2", a: "présent", q: "Développement de microservices Python (Flask) pour la tarification." },
      { id: "C3", a: "partiel", q: "Quelques tests unitaires sur les modules de calcul." },
      { id: "C4", a: "partiel", q: "Python, Flask, Docker, GitLab CI, MySQL, Vue.js" },
      { id: "C5", a: "présent", q: "Conteneurisation de 12 services avec Docker, pipelines GitLab CI." },
      { id: "C6", a: "non trouvé" },
    ],
    clarify: [
      "Durée réelle de pratique Python avant 2023 (scripts d'automatisation).",
      "Expérience PostgreSQL éventuelle au-delà de MySQL.",
      "Mode de collaboration au sein de l'équipe Datafleur.",
    ],
    dropped: 1,
  },
  {
    text: `Lucie Fontaine
Développeuse Python / data
[email retiré] · [telephone retiré]

EXPÉRIENCES
2019 – aujourd'hui · Développeuse — Coopérative Agrinov
- Maintenance d'une application Django de gestion des adhérents.
- Écriture de requêtes SQL et de vues PostgreSQL pour les tableaux de bord.
- Binôme avec l'équipe produit, rédaction de la documentation technique.

2017 – 2019 · Analyste de données — Cabinet Orion
- Notebooks Python (pandas) et rapports automatisés.

FORMATION
École d'ingénieurs — option systèmes d'information

[photo retiré]`,
    removed: { email: 1, telephone: 1, photo: 1 },
    summary:
      "Profil mêlant développement et données : application Django maintenue depuis 2019, travail SQL / PostgreSQL pour des tableaux de bord, et deux années d'analyse de données en Python auparavant. Le CV mentionne une collaboration étroite avec l'équipe produit. Les tests automatisés et l'outillage Docker / CI ne sont pas décrits.",
    ev: [
      { id: "C1", a: "présent", q: "2019 – aujourd'hui · Développeuse — Coopérative Agrinov" },
      { id: "C2", a: "présent", q: "Maintenance d'une application Django de gestion des adhérents." },
      { id: "C3", a: "non trouvé" },
      { id: "C4", a: "présent", q: "Écriture de requêtes SQL et de vues PostgreSQL pour les tableaux de bord." },
      { id: "C5", a: "non trouvé" },
      { id: "C6", a: "partiel", q: "Binôme avec l'équipe produit, rédaction de la documentation technique." },
    ],
    clarify: ["Pratique des tests sur l'application Django.", "Part de développement vs analyse dans le poste actuel."],
    dropped: 0,
  },
];

interface MockCandidate {
  id: string;
  display_name: string;
  created_at: string;
  analyzingAt: number;
  readyAt: number;
  final: Status;
  reason: string | null;
  template: number;
  model: ModelKey;
  questions: InterviewQuestion[];
}

let seq = 0;
const newId = () => {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
};

const now = Date.now();
const candidates: MockCandidate[] = [
  { name: "Camille Martin", t: 0 },
  { name: "Yanis Benali", t: 1 },
  { name: "Lucie Fontaine", t: 2 },
].map(({ name, t }, i) => ({
  id: newId(),
  display_name: name,
  created_at: new Date(now - (10 - i) * 60_000).toISOString(),
  analyzingAt: 0,
  readyAt: 0,
  final: "ready" as Status,
  reason: null,
  template: t,
  model: "rapide" as ModelKey,
  questions: [],
}));
candidates.push({
  id: newId(),
  display_name: "scan-cv-07.png",
  created_at: new Date(now - 6 * 60_000).toISOString(),
  analyzingAt: 0,
  readyAt: 0,
  final: "unsupported",
  reason: "Image trop floue : la transcription n'a produit aucun texte exploitable.",
  template: 0,
  model: "rapide",
  questions: [],
});

const erasureLog: ErasureProof[] = [];

function statusOf(c: MockCandidate): Status {
  const t = Date.now();
  if (t < c.analyzingAt) return "pending";
  if (t < c.readyAt) return "analyzing";
  return c.final;
}

function find(id: string): MockCandidate {
  const c = candidates.find((x) => x.id === id);
  if (!c) throw new ApiError(404, "Candidat introuvable");
  return c;
}

function buildEvidence(tpl: Template, criteria: Criterion[]): Evidence[] {
  return criteria.map((cr) => {
    const e = tpl.ev.find((x) => x.id === cr.id);
    if (!e) return { criterion_id: cr.id, assessment: "non trouvé", quote: null, start: null, end: null };
    if (!e.q) return { criterion_id: cr.id, assessment: e.a, quote: null, start: null, end: null };
    const start = tpl.text.indexOf(e.q);
    if (start < 0) return { criterion_id: cr.id, assessment: e.a, quote: null, start: null, end: null };
    return { criterion_id: cr.id, assessment: e.a, quote: e.q, start, end: start + e.q.length };
  });
}

function summaryOf(c: MockCandidate): CandidateSummary {
  return { id: c.id, display_name: c.display_name, status: statusOf(c), reason: statusOf(c) === c.final ? c.reason : null, created_at: c.created_at };
}

function detailOf(c: MockCandidate): CandidateDetail {
  const status = statusOf(c);
  const tpl = TEMPLATES[c.template];
  const ready = status === "ready";
  return {
    ...summaryOf(c),
    redacted_text: ready ? tpl.text : null,
    removed: ready ? { ...tpl.removed } : {},
    analysis: ready
      ? {
          display_name: c.display_name,
          summary: tpl.summary,
          evidence: buildEvidence(tpl, job.criteria),
          points_to_clarify: [...tpl.clarify],
          dropped_quotes: tpl.dropped,
          model: MODEL_NAMES[c.model],
          prompt_version: PROMPT_VERSION,
        }
      : null,
    questions: clone(c.questions),
  };
}

async function sha256Hex(s: string): Promise<string> {
  if (crypto.subtle) {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
    return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
  }
  return newId() + newId();
}

const ANSWERS = [
  "D'après le CV, la personne mentionne explicitement les éléments suivants : ",
  "un travail sur des API Python en production, ",
  "ainsi qu'une pratique de bases de données relationnelles. ",
  "Le CV ne précise pas la taille des équipes ni la durée exacte de chaque mission ; ",
  "ce point pourrait être abordé en entretien. ",
  "Je ne peux pas me prononcer sur l'adéquation au poste : c'est à vous d'en juger.",
];

export const mockApi: Api = {
  async health() {
    await sleep(150);
    return {
      ok: true,
      models: ["ministral-3:3b", "ministral-3:8b"],
      missing: [],
      model_keys: { rapide: MODEL_NAMES.rapide, precis: MODEL_NAMES.precis },
    };
  },
  async getJob() {
    await sleep(120);
    return clone(job);
  },
  async saveCriteria(criteria) {
    await sleep(200);
    for (const c of criteria) {
      if (!/^C\d{1,2}$/.test(c.id)) throw new ApiError(422, `Identifiant de critère invalide : ${c.id}`);
      if (!c.label.trim()) throw new ApiError(422, "Chaque critère doit avoir un libellé.");
    }
    job = { ...job, criteria: clone(criteria) };
    return { criteria: clone(job.criteria) };
  },
  async suggestCriteria() {
    await sleep(1200);
    return {
      criteria: [
        { id: "C1", label: "Expérience Python ≥ 4 ans", description: "Développement Python en contexte professionnel." },
        { id: "C2", label: "Framework web Python", description: "FastAPI, Django ou Flask." },
        { id: "C3", label: "Tests automatisés (pytest)", description: "Écriture et maintien de tests, qualité de code." },
        { id: "C4", label: "SQL / PostgreSQL", description: "Modélisation de données et optimisation de requêtes." },
        { id: "C5", label: "Docker et intégration continue", description: "Conteneurisation, pipelines CI." },
        { id: "C6", label: "Revue de code et transmission", description: "Participation aux revues, partage de connaissances." },
      ],
    };
  },
  async uploadCandidates(files, model) {
    await sleep(300);
    const base = Math.max(Date.now(), ...candidates.map((c) => c.readyAt));
    return files.map((f, i) => {
      const lower = f.name.toLowerCase();
      const okExt = /\.(pdf|txt|md|png|jpe?g)$/.test(lower);
      const unreadable = !okExt || f.size === 0 || lower.includes("illisible");
      const start = base + i * 2500;
      const c: MockCandidate = {
        id: newId(),
        display_name: f.name.replace(/\.[^.]+$/, ""),
        created_at: new Date(Date.now() + i).toISOString(),
        analyzingAt: start,
        readyAt: start + 2500,
        final: unreadable ? "unsupported" : "ready",
        reason: unreadable
          ? !okExt
            ? "Format non pris en charge (formats acceptés : PDF, TXT, MD, PNG, JPG)."
            : "Aucun texte exploitable n'a pu être extrait du fichier."
          : null,
        template: seq++ % TEMPLATES.length,
        model,
        questions: [],
      };
      candidates.push(c);
      return { id: c.id, display_name: c.display_name, status: statusOf(c) };
    });
  },
  async listCandidates() {
    await sleep(80);
    return candidates.map(summaryOf);
  },
  async getCandidate(id) {
    await sleep(120);
    return detailOf(find(id));
  },
  async reanalyze(id, model) {
    await sleep(150);
    const c = find(id);
    if (c.final !== "ready") throw new ApiError(409, "Ce fichier ne peut pas être analysé.");
    c.model = model;
    c.analyzingAt = Date.now();
    c.readyAt = Date.now() + 3000;
    return { status: statusOf(c) };
  },
  async generateQuestions(id) {
    await sleep(1500);
    const c = find(id);
    const tpl = TEMPLATES[c.template];
    const weak = buildEvidence(tpl, job.criteria).filter((e) => e.assessment !== "présent");
    const qs: InterviewQuestion[] = weak.map((e) => {
      const cr = job.criteria.find((x) => x.id === e.criterion_id)!;
      return {
        question: `Pouvez-vous décrire une situation concrète où vous avez mis en œuvre : ${cr.label.toLowerCase()} ?`,
        rationale:
          e.assessment === "partiel"
            ? `Le CV évoque ce point de façon partielle (« ${e.quote ?? "…"} »).`
            : "Le CV ne mentionne pas ce point ; il peut s'agir d'un simple oubli.",
        criterion_id: cr.id,
      };
    });
    for (const p of tpl.clarify.slice(0, 2)) {
      qs.push({ question: `Pourriez-vous préciser ce point : ${p.charAt(0).toLowerCase()}${p.slice(1)}`, rationale: "Point à clarifier relevé lors de la lecture du CV.", criterion_id: null });
    }
    qs.push({
      question: "Quel projet récent vous a le plus appris, et pourquoi ?",
      rationale: "Question ouverte pour compléter la lecture du CV au-delà des critères.",
      criterion_id: null,
    });
    c.questions = qs.slice(0, 8);
    return { questions: clone(c.questions) };
  },
  async ask(id, _question, _model, onToken, signal) {
    find(id);
    await sleep(400);
    for (const chunk of ANSWERS) {
      for (const word of chunk.split(/(?<= )/)) {
        if (signal?.aborted) throw new DOMException("Abandon", "AbortError");
        onToken(word);
        await sleep(35);
      }
    }
  },
  async compare() {
    await sleep(150);
    return {
      criteria: clone(job.criteria),
      candidates: candidates
        .filter((c) => statusOf(c) === "ready")
        .map((c) => {
          const ev = buildEvidence(TEMPLATES[c.template], job.criteria);
          return {
            id: c.id,
            display_name: c.display_name,
            status: "ready" as Status,
            cells: Object.fromEntries(ev.map((e) => [e.criterion_id, { assessment: e.assessment, quote: e.quote }])),
          };
        }),
    };
  },
  async erase(id) {
    await sleep(900);
    const idx = candidates.findIndex((x) => x.id === id);
    if (idx < 0) throw new ApiError(404, "Candidat introuvable");
    candidates.splice(idx, 1);
    const proof: ErasureProof = {
      candidate_id_hash: await sha256Hex(id),
      erased_at: new Date().toISOString(),
      tables: { candidates: 0, documents: 0, analyses: 0, evidence: 0, questions: 0 },
      raw_file_hits: 0,
      extracts_checked: 6,
      vacuum_ok: true,
      verified: true,
    };
    erasureLog.unshift(proof);
    return clone(proof);
  },
  async erasures() {
    await sleep(100);
    return clone(erasureLog);
  },
};
