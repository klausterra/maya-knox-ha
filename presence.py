"""Regras de presença do Maya Knox (sem dependência do Home Assistant)."""
from __future__ import annotations

from typing import Iterable, Optional

ESTADOS_INCERTOS = {None, "unknown", "unavailable", ""}

ALGUEM_EM_CASA = "em_casa"
TODOS_FORA = "todos_fora"
INCERTO = "incerto"

SUFIXOS_FRIGATE = (
    "_person_occupancy",
    "_car_occupancy",
    "_all_occupancy",
    "_occupancy",
    "_motion",
    "_person",
)


def avaliar_presenca(estados: Iterable[Optional[str]]) -> str:
    """Classifica a casa a partir dos estados de person/device_tracker.

    Basta um "home" para haver alguém em casa. Só conclui que todos saíram
    quando nenhum rastreador está em estado desconhecido, para não armar
    durante o boot do HA ou quando um rastreador cai.
    """
    lista = list(estados)
    if not lista:
        return INCERTO
    if any(e == "home" for e in lista):
        return ALGUEM_EM_CASA
    if any(e in ESTADOS_INCERTOS for e in lista):
        return INCERTO
    return TODOS_FORA


def transicao_valida_para_disparo(estado_antigo: Optional[str], estado_novo: Optional[str]) -> bool:
    """Só dispara em off -> on real; ignora on vindo de unknown/unavailable (boot/reconexão)."""
    if estado_novo != "on":
        return False
    return estado_antigo not in ESTADOS_INCERTOS and estado_antigo != "on"


def camera_do_sensor(entity_id: str) -> Optional[str]:
    """binary_sensor.garagem_person_occupancy -> camera.garagem (convenção do Frigate)."""
    if entity_id.startswith("camera."):
        return entity_id
    if not entity_id.startswith("binary_sensor."):
        return None
    nome = entity_id.split(".", 1)[1]
    for sufixo in SUFIXOS_FRIGATE:
        if nome.endswith(sufixo):
            return f"camera.{nome[: -len(sufixo)]}"
    return None
