"""
Génère un fichier Excel template vierge pour l'import des lignes de bilan GL.
"""

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter


COLUMNS = [
    ("date_arrete",       "Date d'arrêté (YYYY-MM-DD)",         "2026-05-12"),
    ("compte_gl",         "Numéro de compte GL",                 "101001"),
    ("libelle",           "Libellé du compte",                   "Caisse XAF"),
    ("product_code",      "Code produit Flexcube",               "CASH"),
    ("client_id",         "Identifiant client",                  "CL001"),
    ("client_name",       "Nom du client",                       "Entreprise ABC"),
    ("business_unit",     "Business Unit / Direction",           "Retail"),
    ("segment",           "Segment client",                      "corporate"),
    ("sous_segment",      "Sous-segment",                        "PME"),
    ("secteur",           "Secteur économique",                  "Commerce"),
    ("devise",            "Code ISO 4217 (ex: XAF, EUR)",        "XAF"),
    ("montant_lcy",       "Montant en devise locale (entier)",   1_000_000),
    ("montant_fcy",       "Montant en devise étrangère (entier)", 0),
    ("sens",              "actif / passif / hors_bilan",         "actif"),
    ("type_taux",         "fixe / variable / administre / indexe / revisable", "fixe"),
    ("taux_moyen",        "Taux moyen pondéré (%)",              5.5),
    ("maturite",          "Date de maturité (YYYY-MM-DD)",       "2026-12-15"),
    ("bucket_liquidite",  "Code bucket liquidité",               "1M-3M"),
    ("bucket_repricing",  "Code bucket repricing",               "3M-6M"),
    ("entite",            "Entité du groupe",                    "MORANJ BANK"),
    ("agence",            "Code agence Flexcube",                "001"),
    ("source",            "Système source",                      "flexcube"),
]


SAMPLE_ROWS = [
    ["2026-05-12", "101001", "Caisse et billets XAF", "CASH", "TREASURY", "Caisse centrale", "Tresorerie", "institutionnel", "banque", "Tresorerie", "XAF", 6_500_000_000, 0, "actif", "administre", 0.00, "2026-05-12", "call", "call", "MORANJ BANK", "001", "flexcube"],
    ["2026-05-12", "121001", "Avoirs BEAC", "BEAC", "BEAC", "Banque Centrale", "Tresorerie", "institutionnel", "banque centrale", "Banque centrale", "XAF", 69_893_401_198, 0, "actif", "administre", 0.00, "2026-05-12", "call", "call", "MORANJ BANK", "001", "flexcube"],
    ["2026-05-12", "141001", "BTA souverains", "BTA", "CMR-TRESOR", "Etat du Cameroun", "Tresorerie", "souverain", "etat", "Souverain", "XAF", 15_000_000_000, 0, "actif", "fixe", 5.78, "2026-11-08", "3M-6M", "3M-6M", "MORANJ BANK", "001", "calypso"],
    ["2026-05-12", "142001", "OTA souveraines", "OTA", "CEMAC-TRESOR", "Portefeuille titres CEMAC", "Tresorerie", "souverain", "etat", "Souverain", "XAF", 41_460_000_000, 0, "actif", "fixe", 6.03, "2029-06-18", "1Y-3Y", "1Y-3Y", "MORANJ BANK", "001", "calypso"],
    ["2026-05-12", "203001", "Credits clientele retail", "CREDIT", "RET-PORT", "Portefeuille retail", "Retail Banking", "retail", "salaries", "Particuliers", "XAF", 31_777_951_325, 0, "actif", "fixe", 8.11, "2029-05-12", "1Y-3Y", "1Y-3Y", "MORANJ BANK", "020", "flexcube"],
    ["2026-05-12", "204001", "Credits entreprises", "CREDIT_CORP", "CORP-PORT", "Portefeuille corporate", "Corporate Banking", "corporate", "large corporate", "Industrie", "XAF", 48_000_000_000, 0, "actif", "variable", 7.65, "2028-05-12", "1Y-3Y", "3M-6M", "MORANJ BANK", "030", "flexcube"],
    ["2026-05-12", "225001", "Nostro EUR", "NOSTRO", "BANK-EUR", "Correspondant EUR", "Tresorerie", "institutionnel", "banque", "Banques", "EUR", 8_580_000_000, 13_000_000, "actif", "indexe", 3.10, "2026-06-12", "call", "1M-3M", "MORANJ BANK", "001", "swift"],
    ["2026-05-12", "226001", "Placement USD interbancaire", "PLACEMENT_IB", "BANK-USD", "Correspondant USD", "Tresorerie", "institutionnel", "banque", "Banques", "USD", 6_050_000_000, 10_000_000, "actif", "indexe", 4.20, "2026-08-10", "1M-3M", "1M-3M", "MORANJ BANK", "001", "swift"],
    ["2026-05-12", "371001", "Comptes courants clientele", "DDA", "RET-DEP", "Depot clientele retail", "Retail Banking", "retail", "mass market", "Particuliers", "XAF", 125_000_000_000, 0, "passif", "administre", 1.10, "2026-06-12", "call", "call", "MORANJ BANK", "020", "flexcube"],
    ["2026-05-12", "372001", "Comptes cheques clientele", "CHECKING", "RET-CHK", "Depot comptes cheques", "Retail Banking", "retail", "premium", "Particuliers", "XAF", 49_392_123_881, 0, "passif", "administre", 1.25, "2026-06-12", "call", "call", "MORANJ BANK", "025", "flexcube"],
    ["2026-05-12", "373001", "Comptes livrets clientele", "SAVINGS", "RET-SAV", "Depot livrets", "Retail Banking", "retail", "epargne", "Particuliers", "XAF", 72_827_507_841, 0, "passif", "administre", 2.00, "2026-06-12", "call", "call", "MORANJ BANK", "030", "flexcube"],
    ["2026-05-12", "381001", "Depots a terme entreprises", "DAT", "CORP-DAT", "Depots corporate", "Corporate Banking", "corporate", "pme", "Services", "XAF", 66_031_808_504, 0, "passif", "fixe", 4.11, "2027-01-26", "6M-1Y", "6M-1Y", "MORANJ BANK", "040", "flexcube"],
    ["2026-05-12", "382001", "Depots EUR clientele", "DDA_FCY", "FCY-EUR", "Depot EUR clientele", "Corporate Banking", "corporate", "import export", "Commerce", "EUR", 7_920_000_000, 12_000_000, "passif", "indexe", 1.80, "2026-06-12", "call", "1M-3M", "MORANJ BANK", "001", "flexcube"],
    ["2026-05-12", "383001", "Emprunt USD interbancaire", "BORROW_IB", "BANK-USD-LIAB", "Emprunt USD syndique", "Tresorerie", "institutionnel", "banque", "Banques", "USD", 4_235_000_000, 7_000_000, "passif", "indexe", 5.25, "2026-11-12", "3M-6M", "3M-6M", "MORANJ BANK", "001", "swift"],
    ["2026-05-12", "901001", "Lignes de credit confirmees", "COMMITMENT", "OBS-LC", "Engagements confirmes", "Corporate Banking", "corporate", "large corporate", "Industrie", "XAF", 18_000_000_000, 0, "hors_bilan", "variable", 7.00, "2027-05-12", "6M-1Y", "6M-1Y", "MORANJ BANK", "030", "flexcube"],
    ["2026-05-12", "902001", "Garanties donnees", "GUARANTEE", "OBS-GAR", "Garanties commerciales", "Corporate Banking", "corporate", "pme", "BTP", "EUR", 3_300_000_000, 5_000_000, "hors_bilan", "fixe", 2.50, "2028-05-12", "1Y-3Y", "1Y-3Y", "MORANJ BANK", "030", "flexcube"],
]


def generate_balance_sheet_template():
    """Retourne un Workbook openpyxl prêt à sauvegarder."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "bilan"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(fill_type="solid", fgColor="1F4E79")
    hint_fill = PatternFill(fill_type="solid", fgColor="D6E4F0")
    example_fill = PatternFill(fill_type="solid", fgColor="EBF5FB")

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
        cell.font = Font(italic=True, color="1F4E79")
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

    ws.row_dimensions[2].height = 40

    return wb
