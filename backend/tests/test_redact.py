"""Tests du masquage déterministe. Toutes les données sont inventées."""
from pathlib import Path

import pytest

from copilot.redact import redact

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "a_cv_fictif.txt"


def ph(cat: str) -> str:
    return f"[{cat} retiré(e)]"


# --- Positifs -----------------------------------------------------------------
@pytest.mark.parametrize(
    "text,cat,leak",
    [
        ("Contact : zephyrine.quintal@exemple-fictif.fr", "email", "exemple-fictif"),
        ("Mail: z.q+cv@mail.example.org", "email", "mail.example"),
        ("Tél : 06 12 34 56 78", "telephone", "34 56"),
        ("Tél : +33 6 12 34 56 78", "telephone", "34 56"),
        ("Tél : +33 (0)6 12 34 56 78", "telephone", "34 56"),
        ("Tél : 06.12.34.56.78", "telephone", "34.56"),
        ("Tél : 0612345678", "telephone", "0612345678"),
        ("Tél : 06-12-34-56-78", "telephone", "34-56"),
        ("Tél : +33612345678", "telephone", "612345678"),
        ("Né le 12/03/1990", "date_naissance", "1990"),
        ("Née le 1er mars 1991 à Saint-Brieuc", "date_naissance", "Brieuc"),
        ("Né(e) le 12/03/1990", "date_naissance", "1990"),
        ("né le 12 mars 1990", "date_naissance", "1990"),
        ("Date de naissance : 12/03/1990", "date_naissance", "1990"),
        ("Date de naissance: 3 juillet 1985", "date_naissance", "1985"),
        ("Né en 1988", "date_naissance", "1988"),
        ("Née à Rennes le 3 mai 1990", "date_naissance", "Rennes"),
        ("Né à Saint-Malo (35) le 01/02/1989", "date_naissance", "1989"),
        ("Âgée de 34 ans", "age", "34"),
        ("Âgé(e) de 41 ans", "age", "41"),
        ("Zéphyrine Quintal, 34 ans, Rennes", "age", "34"),
        ("Âge : 41 ans", "age", "41"),
        ("Développeuse — 29 ans", "age", "29"),
        ("14 bis rue des Glycines, 35000 Rennes", "adresse", "Glycines"),
        ("3 avenue du Général Fictif 75011 Paris", "adresse", "Fictif"),
        ("12 bd Imaginaire, 69003 Lyon", "adresse", "Imaginaire"),
        ("7, chemin des Lilas Bleus", "adresse", "Lilas"),
        ("Adresse : 44000 Nantes", "adresse", "Nantes"),
        ("Domicile 78100 Saint-Germain-en-Laye", "adresse", "Germain"),
        ("Nationalité : française", "nationalite", "française"),
        ("Nationalité: franco-marocaine", "nationalite", "marocaine"),
        ("de nationalité française", "nationalite", "française"),
        ("Mariée, 2 enfants", "situation_familiale", "Mariée"),
        ("Marié(e)", "situation_familiale", "Marié"),
        ("Célibataire", "situation_familiale", "Célibataire"),
        ("Pacsé", "situation_familiale", "Pacsé"),
        ("Divorcée", "situation_familiale", "Divorcée"),
        ("Mère de deux enfants", "situation_familiale", "enfants"),
        ("Père de 3 enfants", "situation_familiale", "enfants"),
        ("Situation familiale : en couple", "situation_familiale", "couple"),
        ("N° sécu : 1 90 03 35 238 123 45", "numero_secu", "238 123"),
        ("NIR 190033523812345", "numero_secu", "190033523812345"),
        ("https://www.linkedin.com/in/zq-fictive", "lien_perso", "zq-fictive"),
        ("linkedin.com/in/zq-fictive", "lien_perso", "zq-fictive"),
        ("facebook.com/zq.fictive", "lien_perso", "zq.fictive"),
        ("instagram.com/zq_fictive", "lien_perso", "zq_fictive"),
        ("https://twitter.com/zqfictive", "lien_perso", "zqfictive"),
        ("https://x.com/zqfictive", "lien_perso", "zqfictive"),
        ("[Photo]", "photo", "Photo"),
        ("Photo d'identité ci-jointe", "photo", "Photo"),
    ],
)
def test_masque(text, cat, leak):
    r = redact(text)
    assert ph(cat) in r.text, r.text
    assert leak not in r.text, r.text
    assert r.removed.get(cat, 0) >= 1


# --- Négatifs (faux positifs à éviter) ----------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "2018-2022 : Ingénieure données",
        "5 ans d'expérience en Python",
        "12 ans d'expérience en gestion de projet",
        "Plus de 20 ans dans le secteur bancaire",
        "Pendant 18 ans, responsable d'équipe",
        "github.com/zquintal-fictive",
        "https://github.com/zquintal-fictive/projet",
        "Portfolio : zquintal-fictive.dev",
        "Nébuleuse Logicielle SARL (Python, PostgreSQL, Airflow)",
        "Kubernetes, dbt, FastAPI, Docker, Terraform",
        "Marie Durand-Fictive, développeuse",
        "Master Informatique 2017",
        "Budget de 30000 euros géré",
        "Photoshop, Illustrator, InDesign",
        "Équipe de 12 personnes, 3 projets livrés",
        "TOEIC 945",
        "Animatrice de groupes de 12 enfants en colonie",
        "Version 3.12, SIRET non communiqué",
        "Disponible le 01/09/2026",
        "Réduction de 20 % des coûts sur 2 ans",
    ],
)
def test_ne_masque_pas(text):
    r = redact(text)
    assert r.text == text, r.text
    assert r.removed == {}


def test_nom_conserve():
    r = redact("Zéphyrine Quintal-Ardoise\nzq@exemple-fictif.fr")
    assert "Zéphyrine Quintal-Ardoise" in r.text


def test_comptage():
    r = redact("a@b-fictif.fr et c@d-fictif.fr, tél 06 11 22 33 44")
    assert r.removed["email"] == 2
    assert r.removed["telephone"] == 1


def test_fixture_complete():
    raw = FIXTURE.read_text(encoding="utf-8")
    r = redact(raw)
    for leak in ["34 ans", "1990", "Saint-Brieuc", "française", "Mariée", "2 enfants",
                 "Glycines", "35000", "06 12 34 56 78", "exemple-fictif.fr",
                 "linkedin", "\nPhoto\n"]:
        assert leak not in r.text, leak
    for keep in ["Zéphyrine Quintal-Ardoise", "github.com/zquintal-fictive", "2018-2022",
                 "8 ans d'expérience", "Nébuleuse Logicielle SARL", "Kubernetes",
                 "Master Informatique", "TOEIC 945"]:
        assert keep in r.text, keep
    for cat in ["email", "telephone", "adresse", "date_naissance", "age", "nationalite",
                "situation_familiale", "lien_perso", "photo"]:
        assert r.removed.get(cat, 0) >= 1, cat


@pytest.mark.parametrize(
    "text",
    [
        FIXTURE.read_text(encoding="utf-8"),
        "Nationalité : française / Photo / Célibataire / 34 ans",
        "[photo retiré(e)] [nationalite retiré(e)] [age retiré(e)]",
        "",
    ],
)
def test_idempotent(text):
    once = redact(text).text
    twice = redact(once)
    assert twice.text == once
    assert twice.removed == {}


# --- Corrections après relecture (espaces insécables, santé, religion, variantes) ---
NBSP = " "
NNBSP = " "


@pytest.mark.parametrize(
    "text,cat,leak",
    [
        (f"Nationalité{NBSP}: Française", "nationalite", "Française"),
        (f"Âge{NBSP}: 34{NBSP}ans", "age", "34"),
        (f"Développeuse, 34{NNBSP}ans", "age", "34"),
        (f"12{NBSP}rue des Lilas, 69003{NBSP}Lyon", "adresse", "Lilas"),
        ("RQTH", "sante", "RQTH"),
        ("Reconnaissance de la qualité de travailleur handicapé", "sante", "handicapé"),
        ("Travailleuse handicapée", "sante", "handicapée"),
        ("En situation de handicap", "sante", "handicap"),
        ("Santé : diabète de type 1", "sante", "diabète"),
        ("Santé: asthme léger", "sante", "asthme"),
        ("Actuellement enceinte de 5 mois", "sante", "enceinte"),
        ("Grossesse en cours", "sante", "Grossesse"),
        ("Groupe sanguin : O+", "sante", "O+"),
        ("Religion : catholique", "religion", "catholique"),
        ("Musulmane pratiquante", "religion", "pratiquante"),
        ("Catholique pratiquant", "religion", "pratiquant"),
        ("Profil\nFrançaise\nPermis B", "nationalite", "Française"),
        ("Naissance : 1991-06-03", "date_naissance", "1991"),
        ("DDN : 03/06/1991", "date_naissance", "1991"),
        ("Date de naiss. : 03/06/1991", "date_naissance", "1991"),
        ("Née\nle 3 juin 1991", "date_naissance", "1991"),
        ("Née le 1991-06-03", "date_naissance", "06-03"),
        ("Âge: trente-quatre ans", "age", "trente"),
        ("BP 1234", "adresse", "1234"),
        ("Boîte postale 45", "adresse", "45"),
        ("Habite à Villeurbanne", "adresse", "Villeurbanne"),
        ("Domicile : Lyon 3e", "adresse", "Lyon"),
        ("3 r. Victor Hugo", "adresse", "Victor"),
        ("Maman d'un petit garçon", "situation_familiale", "garçon"),
        ("Papa de deux filles", "situation_familiale", "filles"),
        ("Mère d'une fille", "situation_familiale", "fille"),
        ("Tél : +32 470 12 34 56", "telephone", "470 12"),
        ("Tél : +41 79 123 45 67", "telephone", "123 45"),
        ("Contact : jeanne(at)exemple-fictif.com", "email", "jeanne"),
        ("Contact : jeanne [at] exemple-fictif [dot] com", "email", "jeanne"),
    ],
)
def test_masque_v2(text, cat, leak):
    r = redact(text)
    assert ph(cat) in r.text, r.text
    assert leak not in r.text, r.text
    assert r.removed.get(cat, 0) >= 1


@pytest.mark.parametrize(
    "text",
    [
        "Expérience : 20 ans",
        "10000 Utilisateurs actifs",
        "Traitement de 35000 Tickets par an",
        "Intégration Google Photos et Drive",
        "Analyse de photos satellite",
        "Séparé les responsabilités front et back",
        "Enceinte connectée : firmware embarqué",
        "Langues\nFrançais\nAnglais\nEspagnol – B2",
        "Travail chez Acme at scale",
        "Projet de recherche santé publique",
        "Langage Python, 6 ans d'expérience",
    ],
)
def test_ne_masque_pas_v2(text):
    r = redact(text)
    assert r.text == text, r.text


def test_cp_ville_seul_sur_sa_ligne():
    r = redact("Zéphyrine Fictive\n75011 Paris\nDéveloppeuse")
    assert "75011" not in r.text and r.removed.get("adresse") == 1


@pytest.mark.parametrize(
    "bad",
    [
        "a" * 5000 + "@",
        ("a" * 5000 + "@") * 40,
        "a." * 100_000,
        "1 " * 100_000,
        "0" * 200_000,
        ("x" * 50 + " ") * 4000,
        "+3" * 100_000,
        ("Né le " * 10 + "1") * 3000,
        "[" * 200_000,
    ],
)
def test_perf_pathologique(bad):
    import time
    bad = bad[:200_000]
    t = time.perf_counter()
    redact(bad)
    assert time.perf_counter() - t < 1.0


def test_idempotent_v2():
    t = (f"Âge{NBSP}: 34{NBSP}ans\nRQTH\nReligion : catholique\nFrançaise\nBP 1234\n"
         "Habite à Villeurbanne\njeanne(at)exemple-fictif.com\n+32 470 12 34 56\nPhoto")
    once = redact(t).text
    assert redact(once).text == once and redact(once).removed == {}
