"""Cache-bust do card: a URL registrada precisa mudar quando o card muda.

Sem versão na URL, o navegador guarda o módulo por ETag/Last-Modified e serve
304 após uma atualização do HACS — o painel fica com o card antigo até um hard
reload ("Custom element doesn't exist").
"""
import importlib.util
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def _carregar_modulo():
    """Importa __init__.py sem tocar nas dependências do Home Assistant."""
    fonte = (RAIZ / "__init__.py").read_text(encoding="utf-8")
    # Recorta só as duas funções puras de versão de cache.
    inicio = fonte.index("def _versao_para_cache")
    fim = fonte.index("async def async_setup")
    trecho = fonte[inicio:fim]
    espaco = {
        "os": __import__("os"),
        "json": json,
        "_LOGGER": None,
        "__file__": str(RAIZ / "__init__.py"),
        "CARD_PATH": "/maya_knox_www/maya-knox-card.js",
    }
    exec(trecho, espaco)
    return espaco


def test_url_do_card_tem_versao():
    espaco = _carregar_modulo()
    url = espaco["_card_url_com_versao"]()
    assert url.startswith("/maya_knox_www/maya-knox-card.js?v="), url
    versao = url.split("?v=", 1)[1]
    assert versao and versao != "0", f"versão vazia na URL: {url!r}"


def test_versao_casa_com_o_manifest():
    espaco = _carregar_modulo()
    espaco["_LOGGER"] = type("L", (), {"warning": staticmethod(lambda *a, **k: None)})()
    esperado = json.loads((RAIZ / "manifest.json").read_text(encoding="utf-8"))["version"]
    assert espaco["_versao_para_cache"]() == esperado


def test_versao_muda_quando_o_manifest_muda(tmp_path, monkeypatch):
    """Simula um arquivo de manifest diferente e confere que a URL acompanha."""
    espaco = _carregar_modulo()
    espaco["_LOGGER"] = type("L", (), {"warning": staticmethod(lambda *a, **k: None)})()
    original = espaco["_versao_para_cache"]()
    falso = tmp_path / "manifest.json"
    falso.write_text('{"version": "9.9.9"}', encoding="utf-8")
    espaco["__file__"] = str(tmp_path / "qualquer.py")
    assert espaco["_versao_para_cache"]() == "9.9.9"
    assert espaco["_versao_para_cache"]() != original
