from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import (
    EarlyWithdrawalModel, EmbeddedOption, NmdModel, PrepaymentModel, RolloverModel,
)


for model in [NmdModel, PrepaymentModel, EarlyWithdrawalModel, RolloverModel, EmbeddedOption]:
    cls = type(f"{model.__name__}Admin", (SimpleHistoryAdmin,), {
        "list_display": [f.name for f in model._meta.fields if f.name != "id"][:7],
    })
    admin.site.register(model, cls)
