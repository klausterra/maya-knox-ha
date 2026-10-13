"""Garante que todo item do menu de seções tem rótulo traduzido.

O HA resolve o rótulo de `async_show_menu` pela chave
`component.<dominio>.config.step.<step_id>.menu_options.<option>`
(confirmado no bundle do frontend). Sem essa chave, o menu abre com os
itens em branco.
"""
import json
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parent.parent
PASSOS = ["zonas", "campainha", "notificacoes", "automacao"]


def _traducao(nome):
    return json.loads((RAIZ / "translations" / nome).read_text(encoding="utf-8"))


def _descobrir_passos_do_flow():
    """Lê os step_ids registrados no config_flow, em vez de confiar numa lista fixa."""
    fonte = (RAIZ / "config_flow.py").read_text(encoding="utf-8")
    return sorted(set(re.findall(r"async def async_step_(\w+)\(", fonte)) - {"user", "init"})


def test_menu_tem_rotulo_para_cada_secao():
    descobertos = _descobrir_passos_do_flow()
    assert descobertos == sorted(PASSOS), f"passos mudaram no config_flow: {descobertos}"
    for idioma in ("pt-BR.json", "en.json"):
        menu = _traducao(idioma)["config"]["step"]["init"]["menu_options"]
        for passo in PASSOS:
            assert menu.get(passo), f"{idioma}: menu_options.{passo} sem rótulo"


def test_rotulos_sao_legiveis_e_unicos():
    for idioma in ("pt-BR.json", "en.json"):
        menu = _traducao(idioma)["config"]["step"]["init"]["menu_options"]
        valores = [menu[p] for p in PASSOS]
        assert len(set(valores)) == len(valores), f"{idioma}: rótulos repetidos"
        for v in valores:
            # um rótulo deve dizer o que a seção faz, não repetir o step_id cru
            assert len(v) > 8 and " " in v, f"{idioma}: rótulo raso -> {v!r}"


def test_cada_secao_existe_nos_dois_blocos():
    for idioma in ("pt-BR.json", "en.json"):
        d = _traducao(idioma)
        for bloco in ("config", "options"):
            passos = d[bloco]["step"]
            for passo in PASSOS:
                assert passo in passos, f"{idioma}/{bloco}: falta o passo {passo}"
                assert passos[passo].get("title"), f"{idioma}/{bloco}/{passo}: sem title"
