"""
Génère un template Excel pour l'import de ClientMapping.

Colonnes : client_id, client_name, business_unit, segment, sous_segment,
           secteur, secteur_code, agence, entite.
Inclut un jeu de test couvrant Retail, Corporate, Trésorerie et institutions.
"""
from __future__ import annotations

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment


HEADERS = [
    "client_id",
    "client_name",
    "business_unit",
    "segment",
    "sous_segment",
    "secteur",
    "secteur_code",
    "agence",
    "entite",
]

EXAMPLE_ROWS = [
    [
        "C00012345", "JEAN DUPONT", "Retail Banking", "retail",
        "salarie", "Commerce de détail", "G47", "AG001", "SIEGE",
    ],
    [
        "C00067890", "ENTREPRISE ALPHA SARL", "Corporate", "corporate",
        "pme", "Bâtiment et travaux publics", "F41", "AG003", "SIEGE",
    ],
    [
        "C100245", "SOCATEX INDUSTRIE SA", "Corporate Banking", "corporate",
        "large corporate", "Industrie manufacturiere", "C10", "AG010", "MORANJ BANK",
    ],
    [
        "C200118", "CLINIQUE DU CENTRE", "SME Banking", "pme",
        "professionnels", "Sante", "Q86", "AG020", "MORANJ BANK",
    ],
    [
        "C300901", "BTP INTERNATIONAL SARL", "Corporate Banking", "corporate",
        "large corporate", "Construction", "F43", "AG030", "MORANJ BANK",
    ],
    [
        "C400077", "IMPORT AFRICA SA", "Trade Finance", "corporate",
        "import export", "Commerce de gros", "G46", "AG030", "MORANJ BANK",
    ],
    [
        "C500021", "ENERGIE CEMAC SA", "Corporate Banking", "corporate",
        "large corporate", "Energie", "D35", "AG040", "MORANJ BANK",
    ],
    [
        "C600083", "EXPORT CACAO SA", "Corporate Banking", "corporate",
        "exportateur", "Agriculture", "A01", "AG050", "MORANJ BANK",
    ],
    [
        "C700330", "RESEAU DISTRIBUTION SA", "Corporate Banking", "corporate",
        "distributeur", "Commerce de detail", "G47", "AG060", "MORANJ BANK",
    ],
    [
        "C800120", "PME TRANSIT SARL", "SME Banking", "pme",
        "transport", "Transport et logistique", "H49", "AG070", "MORANJ BANK",
    ],
    [
        "CMR-TRESOR", "ETAT DU CAMEROUN", "Tresorerie", "souverain",
        "etat", "Administration publique", "O84", "SIEGE", "MORANJ BANK",
    ],
    [
        "BEAC", "BANQUE CENTRALE", "Tresorerie", "institutionnel",
        "banque centrale", "Institutions financieres", "K64", "SIEGE", "MORANJ BANK",
    ],
    [
        "BANK-EUR", "CORRESPONDANT EUR", "Tresorerie", "institutionnel",
        "banque correspondante", "Institutions financieres", "K64", "SIEGE", "MORANJ BANK",
    ],
    [
        "BANK-USD", "CORRESPONDANT USD", "Tresorerie", "institutionnel",
        "banque correspondante", "Institutions financieres", "K64", "SIEGE", "MORANJ BANK",
    ],
]


def generate_client_mapping_template() -> openpyxl.Workbook:
    """
    Retourne un openpyxl.Workbook contenant le template MIS vierge.
    La feuille s'appelle 'mapping' pour correspondre au nom attendu à l'import.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "mapping"

    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True)
    center = Alignment(horizontal="center")

    # En-têtes
    for col, header in enumerate(HEADERS, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center

    # Lignes d'exemple
    for row_idx, example in enumerate(EXAMPLE_ROWS, 2):
        for col, val in enumerate(example, 1):
            ws.cell(row=row_idx, column=col, value=val)

    # Largeurs de colonnes
    col_widths = [16, 35, 25, 14, 22, 35, 14, 10, 16]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

    return wb
