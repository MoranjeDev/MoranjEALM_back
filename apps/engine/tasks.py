"""Tâches Celery du moteur de calcul ALM."""
from celery import shared_task

from .output_generators import regenerate_outputs
from .synthesis import compute_all_scenarios
from .lcr import compute_lcr_all
from .rate_gap import compute_rate_gap


@shared_task(name="engine.regenerate_outputs")
def task_regenerate_outputs():
    """Recalcule les outputs en arrière-plan."""
    return regenerate_outputs()


@shared_task(name="engine.compute_all")
def task_compute_all():
    """Calcule synthèses + LCR + gap de taux."""
    summary = regenerate_outputs()
    return {
        "outputs": summary,
        "synthesis": compute_all_scenarios(),
        "lcr": compute_lcr_all(),
        "rate_gap": compute_rate_gap(),
    }
