"""
Génère un fichier Excel template vierge pour l'import des engagements hors-bilan.
"""

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


COLUMNS = [
    ("date_arrete",       "Date d'arrêté (YYYY-MM-DD)",                                   "2026-05-12"),
    ("type_engagement",   "ligne_credit / garantie / lettre_credit / engagement_fin / swap / lfp / autre", "ligne_credit"),
    ("reference",         "Référence du dossier",                                          "ENG-TEST-001"),
    ("description",       "Description de l'engagement",                                   "Ligne de crédit confirmée"),
    ("client_id",         "Identifiant client",                                            "CL001"),
    ("client_name",       "Nom du client",                                                 "Entreprise ABC"),
    ("segment",           "Segment client",                                                "corporate"),
    ("secteur",           "Secteur économique",                                            "Commerce"),
    ("business_unit",     "Business Unit / Direction",                                     "Corporate"),
    ("entite",            "Entité du groupe",                                              "MORANJ BANK"),
    ("devise",            "Code ISO 4217 (ex: XAF, EUR)",                                 "XAF"),
    ("notionnel",         "Montant notionnel total (entier)",                              500_000_000),
    ("montant_utilise",   "Montant déjà tiré/utilisé (entier)",                           150_000_000),
    ("prob_tirage_pct",   "Probabilité de tirage en % (ex: 75.0)",                        75.0),
    ("taux",              "Taux d'intérêt ou de swap (%)",                                6.5),
    ("type_taux",         "fixe / variable / administre / indexe / revisable",            "fixe"),
    ("date_mise_place",   "Date de mise en place (YYYY-MM-DD)",                           "2026-01-15"),
    ("maturite",          "Date de maturité (YYYY-MM-DD)",                                "2026-12-15"),
    ("source",            "Système source",                                                "flexcube"),
]


SAMPLE_ROWS = [
    ["2026-05-12", "ligne_credit", "OBS-LC-XAF-001", "Ligne de credit confirmee industrie", "C100245", "SOCATEX INDUSTRIE SA", "corporate", "Industrie", "Corporate Banking", "MORANJ BANK", "XAF", 12_000_000_000, 2_500_000_000, 65.0, 7.25, "variable", "2025-08-15", "2027-08-15", "flexcube"],
    ["2026-05-12", "ligne_credit", "OBS-LC-XAF-002", "Ligne de decouvert confirmee retail pro", "C200118", "CLINIQUE DU CENTRE", "pme", "Sante", "SME Banking", "MORANJ BANK", "XAF", 3_500_000_000, 900_000_000, 55.0, 8.10, "fixe", "2026-01-10", "2026-12-31", "flexcube"],
    ["2026-05-12", "garantie", "OBS-GAR-EUR-001", "Garantie de bonne execution", "C300901", "BTP INTERNATIONAL SARL", "corporate", "BTP", "Corporate Banking", "MORANJ BANK", "EUR", 3_300_000_000, 0, 35.0, 2.50, "fixe", "2025-12-01", "2028-12-01", "flexcube"],
    ["2026-05-12", "garantie", "OBS-GAR-XAF-002", "Caution marche public", "C300455", "CAMEROUN SERVICES", "corporate", "Services", "Corporate Banking", "MORANJ BANK", "XAF", 5_000_000_000, 0, 30.0, 3.00, "fixe", "2026-03-01", "2027-03-01", "flexcube"],
    ["2026-05-12", "lettre_credit", "OBS-LC-USD-001", "Lettre de credit import biens equipement", "C400077", "IMPORT AFRICA SA", "corporate", "Commerce", "Trade Finance", "MORANJ BANK", "USD", 2_420_000_000, 605_000_000, 80.0, 5.40, "indexe", "2026-02-05", "2026-08-05", "trade"],
    ["2026-05-12", "engagement_fin", "OBS-FIN-XAF-001", "Engagement financement projet energie", "C500021", "ENERGIE CEMAC SA", "corporate", "Energie", "Corporate Banking", "MORANJ BANK", "XAF", 15_000_000_000, 4_000_000_000, 70.0, 7.80, "variable", "2025-10-30", "2029-10-30", "flexcube"],
    ["2026-05-12", "swap", "OBS-SWAP-EUR-001", "Swap de change EUR/XAF couverture client", "C600083", "EXPORT CACAO SA", "corporate", "Agriculture", "Tresorerie", "MORANJ BANK", "EUR", 6_600_000_000, 0, 100.0, 3.20, "indexe", "2026-04-15", "2026-10-15", "calypso"],
    ["2026-05-12", "swap", "OBS-SWAP-USD-001", "Swap USD/XAF position banque", "TREASURY", "Book Tresorerie", "institutionnel", "Banques", "Tresorerie", "MORANJ BANK", "USD", 4_840_000_000, 0, 100.0, 4.40, "indexe", "2026-05-01", "2026-11-01", "calypso"],
    ["2026-05-12", "lfp", "OBS-LFP-XAF-001", "Ligne de financement permanente non tiree", "C700330", "RESEAU DISTRIBUTION SA", "corporate", "Commerce", "Corporate Banking", "MORANJ BANK", "XAF", 8_000_000_000, 1_000_000_000, 50.0, 7.10, "variable", "2026-01-01", "2031-01-01", "flexcube"],
    ["2026-05-12", "autre", "OBS-OTHER-XAF-001", "Engagement documentaire divers", "C800120", "PME TRANSIT SARL", "pme", "Transport", "SME Banking", "MORANJ BANK", "XAF", 1_200_000_000, 0, 25.0, 4.00, "fixe", "2026-03-20", "2026-09-20", "trade"],
]


def generate_off_balance_template():
    """Retourne un Workbook openpyxl prêt à sauvegarder."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "hors_bilan"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(fill_type="solid", fgColor="1A5276")
    hint_fill = PatternFill(fill_type="solid", fgColor="D5D8DC")
    example_fill = PatternFill(fill_type="solid", fgColor="EAF2FF")

    # Ligne 1 : noms des colonnes
    for col_idx, (col_name, hint, example) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # Ligne 2 : aide (description)
    for col_idx, (col_name, hint, example) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=2, column=col_idx, value=hint)
        cell.fill = hint_fill
        cell.font = Font(italic=True, color="1A5276")
        cell.alignment = Alignment(wrap_text=True)

    # Ligne 3 : exemple
    for col_idx, (col_name, hint, example) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=3, column=col_idx, value=example)
        cell.fill = example_fill

    # Lignes 4+ : jeu de test réaliste et importable.
    sample_fill = PatternFill(fill_type="solid", fgColor="FFFFFF")
    for row_idx, row in enumerate(SAMPLE_ROWS, start=4):
        for col_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.fill = sample_fill

    # Ajuster la largeur des colonnes
    for col_idx, (col_name, hint, example) in enumerate(COLUMNS, start=1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = max(len(col_name), len(hint) // 2, 14)

    ws.row_dimensions[2].height = 45

    return wb
