from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasHabilitation
from .concentration import compute_concentration
from .eve import compute_eve_sensitivity
from .nii import compute_nii_sensitivity


class NIISensitivityView(APIView):
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "NII Sensitivity"

    def get(self, request):
        horizon = int(request.query_params.get("horizon_days", 365))
        return Response(compute_nii_sensitivity(horizon_days=horizon))


class EVESensitivityView(APIView):
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "EVE Sensitivity"

    def get(self, request):
        return Response(compute_eve_sensitivity())


class EVEEnrichedView(APIView):
    """GET : EVE enrichi — table Bucket×Scénario + breaches IRRBB + hors-bilan."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "EVE Sensitivity"

    def get(self, request):
        from .eve_enriched import compute_eve_enriched
        tier1 = float(request.query_params.get("tier1_capital", 10_000_000_000))
        threshold = float(request.query_params.get("breach_threshold_pct", 15.0))
        include_ob = request.query_params.get("include_off_balance", "1") == "1"
        return Response(compute_eve_enriched(
            tier1_capital=tier1,
            breach_threshold_pct=threshold,
            include_off_balance=include_ob,
        ))


class ConcentrationView(APIView):
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Concentration"

    def get(self, request):
        n = int(request.query_params.get("n", 20))
        return Response(compute_concentration(n=n))


class NIMView(APIView):
    """GET ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD : NIM et WAR/COF."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "NII Sensitivity"

    def get(self, request):
        from .nim import compute_nim
        return Response(compute_nim(
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
        ))


class ProfitabilityRatiosView(APIView):
    """GET : ratios de profitabilité complets (NIM, WAR, COF, LDR, spread, leverage)."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "NII Sensitivity"

    def get(self, request):
        from .nim import compute_profitability_ratios
        return Response(compute_profitability_ratios(
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
        ))


class ConcentrationEnrichedView(APIView):
    """GET : concentration par secteur, segment et BU (depuis le bilan GL)."""
    permission_classes = [IsAuthenticated, HasHabilitation]
    required_habilitation = "Concentration"

    def get(self, request):
        from .concentration_enriched import compute_concentration_enriched, _concentration_by_dimension
        mode = request.query_params.get("by")          # secteur | segment | business_unit | None (=all)
        date_arrete = request.query_params.get("date_arrete")
        n = int(request.query_params.get("n", 10))
        include_ob = request.query_params.get("include_off_balance", "1") == "1"
        if mode in ("secteur", "segment", "business_unit"):
            return Response(_concentration_by_dimension(
                mode, sens=request.query_params.get("sens", "both"),
                include_off_balance=include_ob,
                date_arrete=date_arrete, n_top=n,
            ))
        return Response(compute_concentration_enriched(
            date_arrete=date_arrete, n_top=n, include_off_balance=include_ob,
        ))
