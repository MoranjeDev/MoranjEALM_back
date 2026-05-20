from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    Branch, CollateralType, Currency, CustomerSegment, Entity, FxRate,
    OffBalanceCommitment, ProductMapping, RepricingBucket,
)


for model in [Currency, Entity, ProductMapping, OffBalanceCommitment]:
    cls = type(f"{model.__name__}Admin", (SimpleHistoryAdmin,), {
        "list_display": [f.name for f in model._meta.fields if f.name != "id"][:6],
    })
    admin.site.register(model, cls)


for model in [FxRate, Branch, RepricingBucket, CustomerSegment, CollateralType]:
    admin.site.register(model)
