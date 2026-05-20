from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Parameter


@admin.register(Parameter)
class ParameterAdmin(SimpleHistoryAdmin):
    list_display = ("id", "passwordDelay", "delayActivate", "dateMajCore",
                    "dateMajExtra", "updated_at")
    fieldsets = (
        ("Mot de passe", {
            "fields": ("passwordDelay", "delayActivate"),
        }),
        ("Dates", {
            "fields": ("dateMajCore", "dateMajExtra", "dateArrete"),
        }),
        ("Coefficients beta", {
            "fields": ("beta_cheque", "beta_courant", "beta_livret",
                       "beta_beac", "beta_corr"),
        }),
        ("Stables", {
            "fields": ("stable_cheque", "stable_courant", "stable_livret",
                       "stable_beac", "stable_corr"),
        }),
        ("Variations", {
            "fields": ("var_cheque", "var_courant", "var_livret",
                       "var_beac", "var_corr"),
        }),
        ("Stress test", {
            "fields": ("credMod", "credSev", "banMod", "banSev",
                       "retMod", "retSev", "guiMod", "guiSev"),
        }),
        ("Commentaires ALCO", {
            "classes": ("collapse",),
            "fields": ("commalcobase", "commalcomodere", "commalcosevere"),
        }),
        ("Commentaires DG", {
            "classes": ("collapse",),
            "fields": ("commdgbase", "commdgmodere", "commdgsevere"),
        }),
    )
