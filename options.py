"""Lógica pura do options flow do Maya Knox (sem dependência do Home Assistant).

Fica separada para poder ser testada direto (mesmo padrão do presence.py).
O ponto sensível: o flow salva uma seção por vez, então a mesclagem precisa
preservar as chaves das outras seções — nunca zerar o que já estava configurado.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

CAMPOS_LISTA = (
    "sensores_perimetro",
    "sensores_internos",
    "sensor_campainha",
    "entidade_sirene_alarme",
    "entidade_chime_campainha",
    "moradores",
    "rastreadores_omada",
    "notify_servicos_campainha",
    "notify_servicos_sirene",
    "alexa_notify_servicos_campainha",
    "alexa_notify_servicos_alarme",
    "alexa_campainha_som_dispositivos",
    "frigate_detect_ausente",
    "sensores_pessoa_ausente",
)


def como_lista(valor: Any) -> list:
    """Selectors multiple podem devolver string única quando só uma entidade é escolhida."""
    if valor is None:
        return []
    return [valor] if isinstance(valor, str) else list(valor)


def normalizar(user_input: dict) -> dict:
    for chave in CAMPOS_LISTA:
        if chave in user_input:
            user_input[chave] = como_lista(user_input[chave])
    return user_input


def mesclar_opcoes(base: dict, novo: dict) -> dict:
    """Aplica só as chaves do passo atual sobre a configuração existente."""
    return {**base, **normalizar(novo)}


def entidades_repetidas(perimetro: Iterable[str], internos: Iterable[str]) -> list:
    """Entidades listadas nas duas zonas ao mesmo tempo (config ambígua)."""
    return sorted(set(perimetro) & set(internos))


def filtrar_dominio(entidades: Iterable[Any], dominio: str) -> list:
    """Mantém só ids do domínio pedido.

    Config antiga aceitava sensor.* na campainha; o selector novo só aceita
    binary_sensor. Sem filtrar, o valor antigo seria padrão inválido no formulário.
    """
    prefixo = f"{dominio}."
    return [e for e in como_lista(entidades) if isinstance(e, str) and e.startswith(prefixo)]


def atraso_valido(valor: Any) -> Optional[float]:
    """Minutos de espera do auto-armar; None quando não é um número utilizável."""
    try:
        minutos = float(valor)
    except (TypeError, ValueError):
        return None
    return minutos if 0 <= minutos <= 60 else None
