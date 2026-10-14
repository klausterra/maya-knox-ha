# -*- coding: utf-8 -*-
import json
import logging
import os
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, Event
from homeassistant.helpers.event import async_track_state_change_event, async_call_later
from homeassistant.helpers.start import async_at_started
from homeassistant.const import STATE_ON, Platform
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.alarm_control_panel import AlarmControlPanelState
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import HomeAssistantError

from .presence import (
    ALGUEM_EM_CASA,
    TODOS_FORA,
    avaliar_presenca,
    transicao_valida_para_disparo,
)
from .options import entidades_repetidas

DOMAIN = 'maya_knox'
SERVICOS = ("test_campainha", "test_alarme")
PLATFORMS = [Platform.ALARM_CONTROL_PANEL, Platform.BUTTON]

_LOGGER = logging.getLogger(__name__)

CARD_PATH = '/maya_knox_www/maya-knox-card.js'


def _versao_para_cache() -> str:
    """Versão usada como query string no card.

    Sem isso o navegador guarda o módulo antigo por ETag/Last-Modified e serve
    304 após uma atualização, deixando o painel com o card velho em cache
    até um hard reload. Lê o manifest (mesma fonte que o HACS mostra).
    """
    try:
        caminho = os.path.join(os.path.dirname(__file__), 'manifest.json')
        with open(caminho, encoding='utf-8') as f:
            dados = json.load(f)
        versao = str(dados.get('version') or '').strip()
        if versao:
            return versao
    except Exception as e:
        _LOGGER.warning(f'Maya Knox: não consegui ler a versão do manifest: {e}')
    # Fallback: mtime do próprio card, muda a cada atualização de arquivo.
    try:
        return str(int(os.path.getmtime(os.path.join(os.path.dirname(__file__), 'www', 'maya-knox-card.js'))))
    except OSError:
        return '0'


def _card_url_com_versao() -> str:
    return f'{CARD_PATH}?v={_versao_para_cache()}'

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    '''Set up the Maya Knox component.'''
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    '''Set up Maya Knox from a config entry.'''
    config_data = {**entry.data, **entry.options}
    hass.data.setdefault(DOMAIN, {})

    # --- REGISTRO FRONTEND (uma vez por execução do HA; rotas não podem ser re-registradas) ---
    if not hass.data[DOMAIN].get('static_registrado'):
        try:
            component_path = os.path.dirname(__file__)
            www_path = os.path.join(component_path, 'www')
            brand_path = os.path.join(component_path, 'brand')
            _LOGGER.info(f'Maya Knox: Registrando caminhos estáticos em {www_path}')

            await hass.http.async_register_static_paths(
                [
                    StaticPathConfig(url_path='/maya_knox_www', path=www_path, cache_headers=False),
                    StaticPathConfig(url_path='/maya_knox_static', path=brand_path, cache_headers=False),
                ]
            )
            add_extra_js_url(hass, _card_url_com_versao())
            hass.data[DOMAIN]['static_registrado'] = True
        except Exception as e:
            _LOGGER.error(f'Maya Knox: Erro ao registrar recursos frontend: {e}')

    def _alarm_entity_id():
        registry = er.async_get(hass)
        return registry.async_get_entity_id(Platform.ALARM_CONTROL_PANEL, DOMAIN, f'{DOMAIN}_main_panel')

    sensores_perimetro = config_data.get('sensores_perimetro', [])
    sensores_pessoa_ausente = config_data.get('sensores_pessoa_ausente', [])

    # Vigia de Intrusão (Gatilho e Relatório de Zona)
    async def _verificar_intrusao(event: Event):
        entity_id = _alarm_entity_id()
        if not entity_id: return

        est_alarme = hass.states.get(entity_id)
        if not est_alarme or est_alarme.state not in [AlarmControlPanelState.ARMED_HOME, AlarmControlPanelState.ARMED_AWAY]:
            return

        antigo = event.data.get('old_state')
        novo = event.data.get('new_state')
        if not transicao_valida_para_disparo(antigo.state if antigo else None, novo.state if novo else None):
            return

        sensor_id = event.data.get('entity_id')
        if sensor_id in sensores_perimetro or est_alarme.state == AlarmControlPanelState.ARMED_AWAY:
            hass.data[DOMAIN]['ultimo_disparo'] = sensor_id
            await hass.services.async_call('alarm_control_panel', 'alarm_trigger', {'entity_id': entity_id})

    sensores = list(dict.fromkeys(
        sensores_perimetro + config_data.get('sensores_internos', []) + sensores_pessoa_ausente
    ))
    if sensores:
        entry.async_on_unload(async_track_state_change_event(hass, sensores, _verificar_intrusao))

    repetidas = entidades_repetidas(
        sensores_perimetro, config_data.get('sensores_internos', [])
    )
    if repetidas:
        # Config ambígua: a entidade é desligada em Casa e ligada em Rua ao mesmo tempo.
        _LOGGER.warning(
            "Maya Knox: entidades nas duas zonas (externa e interna): %s. "
            "O comportamento fica indefinido — escolha uma zona para cada uma.",
            ", ".join(repetidas),
        )

    sensores_campainha = config_data.get('sensor_campainha', [])
    
    async def _enviar_alexa(servicos, msg):
        if not servicos:
            return
        
        for servico in servicos:
            try:
                # O serviço pode ser um nome de serviço ou uma entidade notify.*
                if '.' in servico:
                    domain, service_name = servico.split('.', 1)
                else:
                    domain, service_name = "notify", servico
                
                _LOGGER.debug(f"Maya Knox: Tentando enviar para Alexa ({servico}): {msg}")
                
                # Se o domínio for notify e o nome do serviço não existir como serviço, 
                # mas existir como entidade, usamos notify.send_message (alexa_devices oficial)
                if domain == "notify" and not hass.services.has_service(domain, service_name):
                    _LOGGER.debug(f"Maya Knox: Usando notify.send_message para entidade: {servico}")
                    await hass.services.async_call(
                        "notify",
                        "send_message",
                        {
                            "entity_id": servico,
                            "message": msg
                        },
                        blocking=True
                    )
                else:
                    # Tenta serviço específico (alexa_media ou outro)
                    await hass.services.async_call(
                        domain, 
                        service_name, 
                        {"message": msg, "data": {"type": "announce"}},
                        blocking=True
                    )
                    _LOGGER.info(f"Maya Knox: Notificação enviada para {servico}")
            except Exception as e:
                _LOGGER.error(f"Maya Knox: Erro ao enviar para Alexa {servico}: {e}")

    async def _tocar_campainha(event=None):
        novo_state = event.data.get('new_state') if event else None
        if (novo_state and novo_state.state == STATE_ON) or event is None:
            _LOGGER.info('Maya Knox: Campainha acionada!')
            notify_services = config_data.get('notify_servicos_campainha', config_data.get('notify_service_name', []))
            if isinstance(notify_services, str): notify_services = [notify_services]
            if not notify_services: notify_services = ['notify.notify']

            alexa_services = config_data.get('alexa_notify_servicos_campainha', config_data.get('alexa_notify_service', []))
            if isinstance(alexa_services, str): alexa_services = [alexa_services] if alexa_services else []

            nome_zona = 'Campainha de Teste'
            if event:
                sensor_id = event.data.get('entity_id')
                s_state = hass.states.get(sensor_id)
                nome_zona = s_state.attributes.get('friendly_name', sensor_id) if s_state else sensor_id

            dados = {
                'title': ' CAMPAINHA!',
                'message': f'Movimento ou toque detectado em: {nome_zona}',
                'data': {
                    'push': {
                        'sound': {
                            'name': 'default',
                            'critical': 1,
                            'volume': 1.0
                        },
                        'category': 'DOORBELL'
                    },
                    'channel': 'Doorbell',
                    'ttl': 0,
                    'priority': 'high'
                }
            }
            
            for ns in notify_services:
                domain, service = ns.split('.', 1) if '.' in ns else ('notify', ns)
                await hass.services.async_call(domain, service, dados)

            if alexa_services:
                alexa_msg_template = config_data.get('alexa_msg_campainha', 'Atenção, campainha acionada.')
                mensagem_alexa = alexa_msg_template.replace('{zona}', nome_zona)
                await _enviar_alexa(alexa_services, mensagem_alexa)

            # Novo: Som de campainha na Alexa
            alexa_sound_id = config_data.get('alexa_campainha_som_id')
            alexa_sound_devices = config_data.get('alexa_campainha_som_dispositivos', [])
            if alexa_sound_id and alexa_sound_devices:
                registry = er.async_get(hass)
                for device_entity in alexa_sound_devices:
                    if device_entity.startswith('notify.'):
                        # Se for entidade notify, tentamos extrair o device_id ou usar o serviço speak se suportado?
                        # Se for uma entidade de notify direta (como alexa_devices)
                        # Vamos tentar pegar o device_id pelo entity_registry.
                        entry_reg = registry.async_get(device_entity)
                        if entry_reg and entry_reg.device_id:
                            await hass.services.async_call(
                                'alexa_devices', 
                                'send_sound', 
                                {
                                    'sound': alexa_sound_id,
                                    'device_id': entry_reg.device_id
                                }
                            )
                    else:
                        # Legado (config antiga que tinha media_player)
                        entry_reg = registry.async_get(device_entity)
                        if entry_reg and entry_reg.device_id:
                            await hass.services.async_call(
                                'alexa_devices', 
                                'send_sound', 
                                {
                                    'sound': alexa_sound_id,
                                    'device_id': entry_reg.device_id
                                }
                            )

            # Novo: Acionar Campainha Física (Chime)
            chime_entities = config_data.get('entidade_chime_campainha', [])
            if chime_entities:
                await hass.services.async_call('homeassistant', 'turn_on', {'entity_id': chime_entities})

    if sensores_campainha:
        entry.async_on_unload(async_track_state_change_event(hass, sensores_campainha, _tocar_campainha))

    # --- Serviços de Teste (Sempre disponíveis) ---
    async def test_campainha(call):
        _LOGGER.info("Maya Knox: Testando campainha...")
        await _tocar_campainha(None)
        
    async def test_alarme(call):
        _LOGGER.info("Maya Knox: Testando alarme...")
        hass.data[DOMAIN]["ultimo_disparo"] = "Teste de Sistema"
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(Platform.ALARM_CONTROL_PANEL, DOMAIN, f'{DOMAIN}_main_panel')
        if entity_id:
            await hass.services.async_call('alarm_control_panel', 'alarm_trigger', {'entity_id': entity_id})
        else:
            _LOGGER.error("Maya Knox: Entidade de alarme não encontrada para o teste.")

    hass.services.async_register(DOMAIN, "test_campainha", test_campainha)
    hass.services.async_register(DOMAIN, "test_alarme", test_alarme)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    if config_data.get('ativar_auto_armar'):
        _configurar_presenca(hass, entry, config_data)

    return True


def _configurar_presenca(hass: HomeAssistant, entry: ConfigEntry, config_data: dict) -> None:
    """Auto-armar (Rua) quando todos saem e desarmar na chegada se o armamento foi automático."""
    rastreadores = list(dict.fromkeys(config_data.get('moradores', []) + config_data.get('rastreadores_omada', [])))
    if not rastreadores:
        return

    atraso_s = max(0.0, float(config_data.get('atraso_auto_armar', 2))) * 60
    pendente = {'cancelar': None}

    def _cancelar_pendente():
        if pendente['cancelar']:
            pendente['cancelar']()
            pendente['cancelar'] = None

    def _situacao():
        estados = []
        for r in rastreadores:
            s = hass.states.get(r)
            estados.append(s.state if s else None)
        return avaliar_presenca(estados)

    async def _armar_se_continua_vazio(_agora=None):
        pendente['cancelar'] = None
        painel = hass.data[DOMAIN].get('painel')
        if not painel or _situacao() != TODOS_FORA:
            return
        if painel.alarm_state == AlarmControlPanelState.DISARMED:
            _LOGGER.info('Maya Knox: Todos fora há %.0f s. Armando (Rua) automático.', atraso_s)
            await painel.async_armar_automatico()

    async def _avaliar(_evento=None):
        painel = hass.data[DOMAIN].get('painel')
        if not painel:
            return
        situacao = _situacao()
        if situacao == TODOS_FORA:
            if painel.alarm_state == AlarmControlPanelState.DISARMED and not pendente['cancelar']:
                if atraso_s == 0:
                    await _armar_se_continua_vazio()
                else:
                    _LOGGER.info('Maya Knox: Todos saíram. Armando em %.0f s se ninguém voltar.', atraso_s)
                    pendente['cancelar'] = async_call_later(hass, atraso_s, _armar_se_continua_vazio)
        elif situacao == ALGUEM_EM_CASA:
            _cancelar_pendente()
            if painel.alarm_state == AlarmControlPanelState.ARMED_AWAY and painel.auto_armado:
                _LOGGER.info('Maya Knox: Morador chegou. Desarmando (armamento foi automático).')
                await painel.async_desarmar_automatico()

    async def _ao_iniciar(_hass):
        await _avaliar()

    entry.async_on_unload(async_track_state_change_event(hass, rastreadores, _avaliar))
    entry.async_on_unload(async_at_started(hass, _ao_iniciar))
    entry.async_on_unload(_cancelar_pendente)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        for servico in SERVICOS:
            hass.services.async_remove(DOMAIN, servico)
    return ok

async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
