import importlib.util
import pathlib

_spec = importlib.util.spec_from_file_location(
    "presence", pathlib.Path(__file__).resolve().parent.parent / "presence.py"
)
presence = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(presence)


def test_alguem_em_casa_basta_um_home():
    assert presence.avaliar_presenca(["not_home", "home"]) == presence.ALGUEM_EM_CASA


def test_todos_fora_inclui_zonas():
    assert presence.avaliar_presenca(["not_home", "Trabalho"]) == presence.TODOS_FORA


def test_estado_desconhecido_nao_arma():
    assert presence.avaliar_presenca(["not_home", "unavailable"]) == presence.INCERTO
    assert presence.avaliar_presenca(["not_home", None]) == presence.INCERTO
    assert presence.avaliar_presenca(["unknown"]) == presence.INCERTO


def test_home_vence_desconhecido():
    assert presence.avaliar_presenca(["unavailable", "home"]) == presence.ALGUEM_EM_CASA


def test_sem_rastreadores_e_incerto():
    assert presence.avaliar_presenca([]) == presence.INCERTO


def test_disparo_so_em_off_para_on():
    assert presence.transicao_valida_para_disparo("off", "on")
    assert not presence.transicao_valida_para_disparo("unavailable", "on")
    assert not presence.transicao_valida_para_disparo(None, "on")
    assert not presence.transicao_valida_para_disparo("on", "on")
    assert not presence.transicao_valida_para_disparo("on", "off")


def test_camera_do_sensor_frigate():
    assert presence.camera_do_sensor("binary_sensor.garagem_person_occupancy") == "camera.garagem"
    assert presence.camera_do_sensor("binary_sensor.living_motion") == "camera.living"
    assert presence.camera_do_sensor("camera.esquerda") == "camera.esquerda"
    assert presence.camera_do_sensor("binary_sensor.porta_sala") is None
    assert presence.camera_do_sensor("switch.garagem_detect") is None
