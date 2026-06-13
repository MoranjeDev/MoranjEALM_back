from django.contrib import admin
from .models import BalanceSheetLine


@admin.register(BalanceSheetLine)
class BalanceSheetLineAdmin(admin.ModelAdmin):
    list_display = [
        "date_arrete", "compte_gl", "libelle", "sens",
        "devise", "montant_lcy", "montant_fcy", "taux_moyen",
        "maturite", "bucket_liquidite", "entite", "agence", "source",
    ]
    list_filter = ["date_arrete", "sens", "devise", "source", "entite"]
    search_fields = ["compte_gl", "libelle", "client_id", "client_name"]
    date_hierarchy = "date_arrete"
