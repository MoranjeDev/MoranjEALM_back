from django.contrib import admin
from .models import OffBalanceSheetItem


@admin.register(OffBalanceSheetItem)
class OffBalanceSheetItemAdmin(admin.ModelAdmin):
    list_display = [
        "date_arrete", "type_engagement", "reference",
        "client_name", "devise", "notionnel", "montant_utilise",
        "prob_tirage_pct", "maturite", "bucket_liquidite", "source",
    ]
    list_filter = ["date_arrete", "type_engagement", "devise", "source"]
    search_fields = ["reference", "client_id", "client_name", "description"]
    date_hierarchy = "date_arrete"
