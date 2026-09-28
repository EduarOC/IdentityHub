"""RF-11: puntaje de riesgo de 0 a 100 según alcance de permisos e inactividad."""
from datetime import datetime, timedelta, timezone

import pytest

AHORA = datetime.now(timezone.utc)


@pytest.mark.parametrize("alcance, base", [
    ("Acceso completo a Gmail", 70),
    ("Full access", 70),
    ("Permisos de administrador", 70),
    ("Solo lectura de perfil básico", 20),
    ("read user profile", 20),
    ("Calendario", 40),
    (None, 40),
])
def test_base_segun_alcance(inv, alcance, base):
    # Uso reciente: sin bonus de inactividad, el puntaje es solo la base.
    assert inv.calcular_puntaje_riesgo(alcance, AHORA) == base


@pytest.mark.parametrize("dias, bonus", [(5, 0), (31, 10), (91, 20), (181, 30)])
def test_bonus_por_inactividad(inv, dias, bonus):
    assert inv.calcular_puntaje_riesgo("Calendario", AHORA - timedelta(days=dias)) == 40 + bonus


def test_sin_fecha_de_uso_es_riesgo_medio_no_cero(inv):
    # HU-10, escenario 2: inactividad desconocida suma 15, no se trata como riesgo cero.
    assert inv.calcular_puntaje_riesgo("Calendario", None) == 55


def test_fecha_sin_zona_horaria(inv):
    naive = (AHORA - timedelta(days=200)).replace(tzinfo=None)
    assert inv.calcular_puntaje_riesgo("Calendario", naive) == 70


def test_puntaje_nunca_supera_100(inv):
    assert inv.calcular_puntaje_riesgo("Acceso completo", AHORA - timedelta(days=400)) == 100


def test_permiso_amplio_inactivo_supera_lectura_reciente(inv):
    # HU-10, escenario 1.
    amplio = inv.calcular_puntaje_riesgo("Acceso completo a Drive", AHORA - timedelta(days=200))
    lectura = inv.calcular_puntaje_riesgo("Solo lectura", AHORA - timedelta(days=2))
    assert amplio > lectura
