import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "options", pathlib.Path(__file__).resolve().parent.parent / "options.py"
)
options = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(options)


def test_string_unica_vira_lista():
    assert options.como_lista("camera.living") == ["camera.living"]
    assert options.como_lista(["a", "b"]) == ["a", "b"]
    assert options.como_lista(None) == []


def test_normalizar_so_converte_campos_de_lista():
    entrada = {"moradores": "person.klaus", "atraso_auto_armar": 2, "alexa_msg_alarme": "oi"}
    saida = options.normalizar(entrada)
    assert saida["moradores"] == ["person.klaus"]
    assert saida["atraso_auto_armar"] == 2
    assert saida["alexa_msg_alarme"] == "oi"


def test_mesclagem_preserva_outras_secoes():
    """Editar a campainha não pode zerar as zonas nem a automação."""
    base = {
        "sensores_perimetro": ["camera.direita"],
        "sensores_internos": ["binary_sensor.living_all_occupancy"],
        "moradores": ["person.klaus"],
        "atraso_auto_armar": 2,
        "sensor_campainha": [],
    }
    novo = {"sensor_campainha": "binary_sensor.garagem_all_occupancy", "alexa_msg_campainha": "Tocou!"}
    resultado = options.mesclar_opcoes(base, novo)
    assert resultado["sensores_perimetro"] == ["camera.direita"]
    assert resultado["moradores"] == ["person.klaus"]
    assert resultado["atraso_auto_armar"] == 2
    assert resultado["sensor_campainha"] == ["binary_sensor.garagem_all_occupancy"]
    assert resultado["alexa_msg_campainha"] == "Tocou!"


def test_mesclagem_nao_altera_entrada_original():
    base = {"moradores": ["person.klaus"]}
    options.mesclar_opcoes(base, {"moradores": "person.outro"})
    assert base["moradores"] == ["person.klaus"]


def test_entidade_em_duas_zonas_e_reportada():
    repetidas = options.entidades_repetidas(
        ["camera.living", "camera.direita"], ["binary_sensor.living_motion", "camera.living"]
    )
    assert repetidas == ["camera.living"]
    assert options.entidades_repetidas(["camera.a"], ["camera.b"]) == []


def test_atraso_valido():
    assert options.atraso_valido(2) == 2.0
    assert options.atraso_valido("0") == 0.0
    assert options.atraso_valido(None) is None
    assert options.atraso_valido("abc") is None
    assert options.atraso_valido(61) is None


def test_filtrar_dominio_remove_valor_invalido_de_config_antiga():
    antigo = ["sensor.portao", "binary_sensor.portao", None]
    assert options.filtrar_dominio(antigo, "binary_sensor") == ["binary_sensor.portao"]
    assert options.filtrar_dominio("binary_sensor.unico", "binary_sensor") == ["binary_sensor.unico"]
    assert options.filtrar_dominio(None, "binary_sensor") == []
