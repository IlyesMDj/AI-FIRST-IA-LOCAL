"""Masquage déterministe (regex) des données personnelles non utiles au poste.

Principe : on préfère masquer un peu trop que pas assez sur les catégories sensibles,
mais on protège explicitement les faux positifs classiques d'un CV (années de diplôme,
« 5 ans d'expérience », github, noms d'entreprises, technologies).
Le NOM est conservé. Idempotent : les marqueurs déjà posés ne sont jamais re-traités.
Toutes les répétitions sont bornées (pas de backtracking catastrophique).
"""
from __future__ import annotations

import re
from typing import Callable

from .types import RedactResult

PLACEHOLDER_RE = re.compile(r"\[[a-z_]+ retiré\(e\)\]")
# espaces insécables / fines / de largeur fixe → espace simple
_SPACES_RE = re.compile(r"[\u00a0\u202f\u2007\u2009\u200a\u2002\u2003\u2004\u2005\u2006\u2008\u205f\u3000]")


def _ph(cat: str) -> str:
    return f"[{cat} retiré(e)]"


_MOIS = (r"(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|"
         r"novembre|d[ée]cembre|janv?\.?|f[ée]vr?\.?|avr\.?|juil\.?|sept?\.?|oct\.?|nov\.?|d[ée]c\.?)")
_DATE = (rf"(?:(?:19|20)\d{{2}}[/.\-]\d{{1,2}}[/.\-]\d{{1,2}}"
         rf"|\d{{1,2}}[/.\-]\d{{1,2}}[/.\-]\d{{2,4}}"
         rf"|\d{{1,2}}(?:er)?[ \t]+(?i:{_MOIS})[ \t]+\d{{4}}"
         rf"|(?i:{_MOIS})[ \t]+\d{{4}}"
         rf"|(?:19|20)\d{{2}})")
_CAP_WORD = r"[A-ZÀ-ÖØ-Ý][\wÀ-ÿ'’\-]{0,40}"
_CITY = rf"(?:(?:Le|La|Les|L['’])[ \t]?)?{_CAP_WORD}"
_WORD = r"[A-Za-zÀ-ÖØ-öø-ÿ\-]{1,40}"
_REST = r"[^\s|;\[\]][^\n|;\[\]]{0,80}"     # reste de ligne après une étiquette (non vide)
_NUM_WORDS = r"(?:\d{1,2}|un|une|deux|trois|quatre|cinq|six|sept|huit)"

# --- Motifs --------------------------------------------------------------------
_EMAIL = re.compile(
    r"(?<![\w.+\-])[\w.+\-]{1,64}"
    r"(?:@|[ \t]?(?i:\(at\)|\[at\]|\{at\}|\(arobase\)|\[arobase\])[ \t]?)"
    r"[\w\-]{1,63}"
    r"(?:(?:\.|[ \t]?(?i:\(dot\)|\[dot\]|\{dot\}|\(point\)|\[point\])[ \t]?)[\w\-]{1,63}){1,8}"
)

_LIEN = re.compile(
    r"(?i:(?<![\w.\-/@])(?:https?://)?(?:[\w\-]{1,63}\.){0,4}"
    r"(?:linkedin\.com|lnkd\.in|facebook\.com|fb\.com|fb\.me|instagram\.com|twitter\.com|x\.com"
    r"|tiktok\.com|snapchat\.com|viadeo\.com|threads\.net)"
    r"(?:/[^\s,;)\]>]{0,200})?)"
)

# NIR : sexe(1) année(2) mois(2) département(2 ou 2A/2B) commune(3) ordre(3) [clé(2)]
_SECU = re.compile(
    r"(?<!\d)[12][ .]?\d{2}[ .]?(?:0[1-9]|1[0-2]|[2-9]\d)[ .]?(?:\d{2}|2[AaBb])[ .]?\d{3}[ .]?\d{3}"
    r"(?:[ .]?\d{2})?(?!\d)"
)

_TEL_FR = re.compile(
    r"(?<![\w+])(?:(?:\+|00)[ \t]?33[ \t.\-]?(?:\(0\)[ \t.\-]?)?[1-9]|0[1-9])(?:[ \t.\-]?\d{2}){4}(?!\d)"
)
_TEL_INTL = re.compile(r"(?<![\w+])(?:\+|00)[1-9]\d{0,2}(?:[ \t.\-]?\(?\d{1,4}\)?){2,6}(?!\d)")


def _tel_intl_ok(seg: str, m: re.Match) -> bool:
    digits = sum(c.isdigit() for c in m.group(0))
    return 8 <= digits <= 15


_LIEU = rf"(?:[ \t]+(?i:à)[ \t]+{_CAP_WORD}(?:[ \t]*\(\d{{2,3}}\))?)"
_NAISSANCE = re.compile(
    rf"\b(?i:né(?:e|\(e\))?){_LIEU}?[ \t]*\n?[ \t]*(?:(?i:le|en)[ \t]+)?{_DATE}{_LIEU}?(?!\w)"
    rf"|(?i:\b(?:date[ \t]+(?:et[ \t]+lieu[ \t]+)?|lieu[ \t]+)de[ \t]+naiss(?:ance|\.)?)[ \t]*:?[ \t]*{_REST}"
    rf"|(?i:\bnaissance|\bDDN\b)[ \t]*:[ \t]*{_REST}"
    rf"|\bDDN[ \t]+{_DATE}"
)

_AGE_NUM_WORDS = (r"(?:seize|dix-sept|dix-huit|dix-neuf|vingt|trente|quarante|cinquante|soixante)"
                  r"(?:[ \t\-]?(?:et[ \t\-]?)?(?:un|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze))?")
_AGE_LABEL = re.compile(
    rf"(?<!\w)(?:(?i:âge|age)[ \t]*:[ \t]*(?:\d{{1,3}}(?:[ \t]*ans)?\b|(?i:{_AGE_NUM_WORDS})(?:[ \t]+ans)?\b)"
    rf"|(?i:[âa]g[ée]e?(?:\(e\))?[ \t]+de[ \t]+(?:\d{{1,3}}|{_AGE_NUM_WORDS})[ \t]*ans)\b)"
)
_AGE = re.compile(r"(?<![\d,.])\b(?:1[6-9]|[2-6]\d|7[0-5])[ \t]?ans\b")
_AGE_AFTER_NOT = re.compile(
    r"^[ \t]*(?:d['’]|de\b|des\b|du\b|dans\b|en\b|chez\b|au\b|aux\b|à\b|comme\b|sur\b|pour\b|"
    r"plus\b|minimum\b|max|consécutifs|révolus|-)",
    re.IGNORECASE,
)
_AGE_BEFORE_NOT = re.compile(
    r"(?:\b(?:depuis|plus de|moins de|pendant|durant|environ|sur|de|en|après|avant|près de|presque|"
    r"il y a|soit|dont|pour|à|au bout de|tous les|toutes les|garantie|contrat de)[ \t]*"
    r"|(?:exp[ée]rience|exp\.|anciennet[ée]|s[ée]niorit[ée]|pratique|dur[ée]e)[ \t]*:?[ \t]*)$",
    re.IGNORECASE,
)


def _age_filter(text: str, m: re.Match) -> bool:
    before = text[max(0, m.start() - 25):m.start()]
    after = text[m.end():m.end() + 25]
    return not (_AGE_BEFORE_NOT.search(before) or _AGE_AFTER_NOT.match(after))


_STREET_TYPES = (r"rue|r\.|avenue|av\.|bd|boulevard|chemin|ch\.|all[ée]e|impasse|imp\.|place|pl\.|route|rte"
                 r"|quai|square|r[ée]sidence|lotissement|lieu-dit|voie|passage|chauss[ée]e|faubourg"
                 r"|cit[ée]|hameau|sentier|villa|mail|esplanade|parvis|rond-point")
_ADRESSE_LABEL = re.compile(
    rf"(?i:\b(?:adresse|domicile|lieu[ \t]+de[ \t]+r[ée]sidence|r[ée]sidence))[ \t]*:[ \t]*{_REST}"
)
_ADRESSE = re.compile(
    rf"\b\d{{1,4}}(?:[ \t]?(?i:bis|ter|quater|[a-d])\b)?,?[ \t]+"
    rf"(?:(?i:{_STREET_TYPES})|Cours)\.?[ \t]+"
    rf"(?:(?i:de la|de l['’]|des|du|de|d['’]|la|le|les|l['’])[ \t]*)?[A-ZÀ-ÖØ-Ý0-9]"
    rf"[^\n,;|\d\[\]]{{0,60}}"
    rf"(?:[, \t\-]{{0,4}}\d{{5}}(?:[ \t]+{_CITY}(?:[ \t]+(?i:cedex)(?:[ \t]*\d{{1,2}})?)?)?)?"
)
_BP = re.compile(
    rf"(?:\bB\.?P\.?|(?i:\bbo[iî]te[ \t]+postale)|\bCS)[ \t]*\d{{1,6}}\b"
    rf"(?:[, \t\-]{{0,4}}\d{{5}}(?:[ \t]+{_CITY})?)?"
)
_HABITE = re.compile(
    rf"(?i:\b(?:habite|vit|demeurant|r[ée]sidant|domicili[ée]e?))[ \t]+(?i:à|a|au|en|sur)[ \t]+"
    rf"{_CITY}(?:[ \t]+\d{{1,2}}(?:e|ème|er)\b)?"
)
_CP_VILLE = re.compile(
    rf"(?<![\d.,])\b(?:0[1-9]|[1-8]\d|9[0-8])\d{{3}}[ \t]+{_CITY}(?:[ \t]+(?i:cedex)(?:[ \t]*\d{{1,2}})?)?"
)
_KNOWN_CITIES = {
    "paris", "marseille", "lyon", "toulouse", "nice", "nantes", "montpellier", "strasbourg", "bordeaux",
    "lille", "rennes", "reims", "toulon", "grenoble", "dijon", "angers", "nîmes", "villeurbanne",
    "clermont-ferrand", "le havre", "aix-en-provence", "brest", "tours", "amiens", "limoges", "annecy",
    "perpignan", "metz", "besançon", "orléans", "rouen", "mulhouse", "caen", "nancy", "argenteuil",
    "montreuil", "roubaix", "tourcoing", "avignon", "poitiers", "versailles", "pau", "la rochelle",
    "nanterre", "créteil", "vannes", "lorient", "quimper", "saint-brieuc", "bayonne", "valence",
}
_ADDR_CONTEXT = re.compile(r"(?i:adresse|domicile|habite|r[ée]sid|demeur|cedex|\bbp\b|\bcs\b|,)[^\n]{0,40}$")


def _cp_ville_ok(seg: str, m: re.Match) -> bool:
    city = m.group(0)[5:].strip()
    low = city.lower()
    if low in _KNOWN_CITIES or re.search(r"(?i:^saint|^sainte|-sur-|-en-|-l[eè]s-|-le-|-la-|cedex)", city):
        return True
    line_start = seg.rfind("\n", 0, m.start()) + 1
    nl = seg.find("\n", m.end())
    before = seg[line_start:m.start()]
    after = seg[m.end():nl if nl != -1 else len(seg)]
    if not before.strip() and not after.strip():
        return True                                  # seul sur sa ligne : en-tête de CV
    return bool(_ADDR_CONTEXT.search(before))


_NATIONALITE = re.compile(
    rf"(?i:(?:\bde[ \t]+)?\bnationalit[ée]s?)[ \t]*:?[ \t]*{_WORD}"
    rf"(?:[ \t]*(?:/|,|\bet\b)[ \t]*{_WORD})?"
)
# Nationalité seule sur une ligne. Formes féminines (les formes masculines « Français »,
# « Espagnol »… sont des LANGUES) + masculines sans ambiguïté avec une langue.
_NAT_FEM = (r"française|belge|suisse|canadienne|marocaine|algérienne|tunisienne|sénégalaise|ivoirienne"
            r"|camerounaise|malienne|portugaise|espagnole|italienne|allemande|britannique|américaine"
            r"|chinoise|vietnamienne|turque|roumaine|polonaise|libanaise|brésilienne|congolaise|haïtienne"
            r"|guinéenne|comorienne|russe|ukrainienne|indienne")
_NAT_MASC = (r"belge|suisse|canadien|marocain|algérien|tunisien|sénégalais|ivoirien|camerounais|malien"
             r"|libanais|brésilien|américain|britannique|congolais|haïtien|guinéen|comorien|ukrainien")
_NAT = rf"(?:franco-|italo-|hispano-)?(?:{_NAT_FEM}|{_NAT_MASC})"
_NATIONALITE_SEULE = re.compile(
    rf"(?im:^[ \t]*{_NAT}(?:[ \t]*(?:/|et|,)[ \t]*{_NAT})?[ \t]*\.?[ \t]*$)"
)

_FAMILLE = re.compile(
    rf"(?i:\bsituation[ \t]+(?:familiale|de[ \t]+famille))[ \t]*:?[ \t]*{_REST}"
    rf"|(?i:\b(?:maman|papa)[ \t]+(?:de[ \t]+|d['’][ \t]*)[^\n,.;|\[\]]{{1,40}})"
    rf"|(?i:\b(?:m[èe]re|p[èe]re)[ \t]+(?:de[ \t]+|d['’][ \t]*)"
    rf"(?:famille|{_NUM_WORDS}[ \t]+(?:(?:petite?s?|jeunes?)[ \t]+)?"
    rf"(?:enfants?|fils|filles?|garçons?|bébés?|jumeaux|jumelles))\b)"
    rf"|(?<!de )(?<!d')(?<!d’)(?<!De )(?i:\b(?:\d{{1,2}}|un|deux|trois|quatre|cinq|six)[ \t]+enfants?\b)"
    rf"|(?i:\b(?:c[ée]libataire|en[ \t]+couple|concubinage|union[ \t]+libre)\b)"
)
_FAMILLE_STATUT = re.compile(r"(?i:\b(?:marié|pacsé|divorcé|séparé|fiancé|veuf|veuve)(?:\(e\)|e?s?\b))")
_STATUT_NOT_FOLLOWED = re.compile(
    r"^[ \t]+(?:les|la|le|l['’]|des|du|un|une|par|aux?|à|ses|leurs?|son|sa|nos|vos|ce|cette|ces)\b",
    re.IGNORECASE,
)


def _statut_ok(seg: str, m: re.Match) -> bool:
    return not _STATUT_NOT_FOLLOWED.match(seg[m.end():m.end() + 20])


_SANTE = re.compile(
    rf"(?i:\bsant[ée])[ \t]*:[ \t]*{_REST}"
    rf"|\bRQTH\b"
    rf"|(?i:\breconnaissance[ \t]+(?:de[ \t]+(?:la[ \t]+)?)?qualit[ée][ \t]+de[ \t]+travailleu(?:r|se)[ \t]+handicap[ée]e?)"
    rf"|(?i:\btravailleu(?:r|se)[ \t]+handicap[ée]e?)"
    rf"|(?i:\b(?:en[ \t]+)?situation[ \t]+de[ \t]+handicap)"
    rf"|(?i:\bhandicap(?:[ée]e?s?)?\b)"
    rf"|(?i:\bgroupe[ \t]+sanguin)[ \t]*:?[ \t]*(?:(?:AB|A|B|O)[ \t]?(?:[+\-]|(?i:positif|n[ée]gatif))?)?"
    rf"|(?i:\b(?:je[ \t]+suis|suis|actuellement|être|etre)[ \t]+enceinte\b(?:[ \t]+de[ \t]+\d{{1,2}}[ \t]+mois)?)"
    rf"|(?i:\benceinte[ \t]+de[ \t]+\d{{1,2}}[ \t]+mois)"
    rf"|(?im:^[ \t]*enceinte[ \t]*$)"
    rf"|(?i:\b(?:grossesse|cong[ée][ \t]+(?:de[ \t]+)?maternit[ée])\b)"
    rf"|(?i:\b(?:diab[èe]te|diab[ée]tique|[ée]pilep(?:sie|tique)|asthm(?:e|atique)|scl[ée]rose[ \t]+en[ \t]+plaques"
    rf"|s[ée]ropositi(?:f|ve)|VIH|dyslexi(?:e|que)|dyspraxi(?:e|que)|maladie[ \t]+chronique"
    rf"|affection[ \t]+de[ \t]+longue[ \t]+dur[ée]e|invalidit[ée])\b)"
)

_RELIGIONS = (r"catholique|musulmane?|juif|juive|protestante?|bouddhiste|hindoue?|orthodoxe|chrétienne?"
              r"|évangélique|athée|israélite|sikh")
_RELIGION = re.compile(
    rf"(?i:\b(?:religion|confession|culte))[ \t]*:[ \t]*{_REST}"
    rf"|(?i:\bde[ \t]+confession[ \t]+{_WORD})"
    rf"|(?i:(?:\b(?:{_RELIGIONS})[ \t]+)?\bpratiquant(?:e|\(e\))?s?(?!\w)(?:[ \t]+(?:{_RELIGIONS})\b)?)"
)

_PHOTO = re.compile(
    r"(?<!\w)(?i:photos?)(?:[ \t]+(?i:d['’][ \t]*identit[ée]))?(?:[ \t]+(?i:ci-?jointe?s?))?(?!\w)"
)
_PHOTO_AFTER_OK = re.compile(r"^[ \t]*(?:$|\n|[\])|:•\-–—]|(?i:ci-?jointe?|jointe?|en[ \t]+pi[èe]ce))")


def _photo_ok(seg: str, m: re.Match) -> bool:
    g = m.group(0).lower()
    if "identit" in g or "joint" in g:
        return True
    line_start = seg.rfind("\n", 0, m.start()) + 1
    before = seg[line_start:m.start()].rstrip()
    if before and before[-1] not in "[(|•:-–—":
        return False
    return bool(_PHOTO_AFTER_OK.match(seg[m.end():m.end() + 20]))


Rule = tuple[str, re.Pattern, Callable[[str, re.Match], bool] | None]

_RULES: list[Rule] = [
    ("email", _EMAIL, None),
    ("lien_perso", _LIEN, None),
    ("numero_secu", _SECU, None),
    ("telephone", _TEL_FR, None),
    ("telephone", _TEL_INTL, _tel_intl_ok),
    ("date_naissance", _NAISSANCE, None),
    ("age", _AGE_LABEL, None),
    ("age", _AGE, _age_filter),
    ("adresse", _ADRESSE_LABEL, None),
    ("adresse", _ADRESSE, None),
    ("adresse", _BP, None),
    ("adresse", _HABITE, None),
    ("adresse", _CP_VILLE, _cp_ville_ok),
    ("nationalite", _NATIONALITE, None),
    ("nationalite", _NATIONALITE_SEULE, None),
    ("sante", _SANTE, None),
    ("religion", _RELIGION, None),
    ("situation_familiale", _FAMILLE, None),
    ("situation_familiale", _FAMILLE_STATUT, _statut_ok),
    ("photo", _PHOTO, _photo_ok),
]


def _apply(text: str, cat: str, pattern: re.Pattern, keep: Callable | None, counts: dict[str, int]) -> str:
    """Applique un motif uniquement hors des marqueurs déjà posés (idempotence)."""
    out: list[str] = []
    pos = 0
    segments: list[tuple[str, bool]] = []
    for pm in PLACEHOLDER_RE.finditer(text):
        segments.append((text[pos:pm.start()], True))
        segments.append((pm.group(0), False))
        pos = pm.end()
    segments.append((text[pos:], True))

    for seg, active in segments:
        if not active or not seg:
            out.append(seg)
            continue

        def repl(m: re.Match, seg=seg) -> str:
            if not m.group(0).strip():
                return m.group(0)
            if keep is not None and not keep(seg, m):
                return m.group(0)
            counts[cat] = counts.get(cat, 0) + 1
            g = m.group(0)
            lead = g[:len(g) - len(g.lstrip())]       # conserve espaces / sauts de ligne de bord
            trail = g[len(g.rstrip()):]
            return lead + _ph(cat) + trail

        out.append(pattern.sub(repl, seg))
    return "".join(out)


def redact(text: str) -> RedactResult:
    text = _SPACES_RE.sub(" ", text)
    counts: dict[str, int] = {}
    for cat, pattern, keep in _RULES:
        text = _apply(text, cat, pattern, keep, counts)
    return RedactResult(text=text, removed=counts)
