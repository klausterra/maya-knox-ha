"""Config/Options flow do Maya Knox.

O formulário em um único passo (~18 campos) não cabia no dialog mobile e
escondia o botão de enviar — por isso as seções: zonas, campainha,
notificações, automação. A lógica de normalização/mesclagem vive em options.py.
"""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .options import como_lista, filtrar_dominio, mesclar_opcoes

DOMAIN = "maya_knox"

PASSOS = ("zonas", "campainha", "notificacoes", "automacao")


def _notify_selector(hass: HomeAssistant | None) -> selector.SelectSelector:
    opcoes = []
    if hass is not None:
        servicos = hass.services.async_services().get("notify", {})
        opcoes = [{"value": f"notify.{s}", "label": f"notify.{s}"} for s in servicos]
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=opcoes,
            custom_value=True,
            multiple=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _schema_zonas(hass: HomeAssistant | None, d: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                "sensores_perimetro", default=como_lista(d.get("sensores_perimetro"))
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True, domain=["binary_sensor", "camera"])
            ),
            vol.Required(
                "sensores_internos", default=como_lista(d.get("sensores_internos"))
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True, domain=["binary_sensor", "camera"])
            ),
            vol.Required(
                "entidade_sirene_alarme",
                default=como_lista(d.get("entidade_sirene_alarme", d.get("sirene"))),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True, domain=["switch", "siren", "light"])
            ),
            vol.Optional(
                "entidade_chime_campainha", default=como_lista(d.get("entidade_chime_campainha"))
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True, domain=["switch", "siren", "light"])
            ),
        }
    )


def _schema_campainha(hass: HomeAssistant | None, d: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                "sensor_campainha",
                default=filtrar_dominio(d.get("sensor_campainha"), "binary_sensor"),
            ): selector.EntitySelector(
                # Só binary_sensor: o gatilho reage a state == "on", que um
                # sensor.* comum nunca assume (a campainha ficava muda).
                selector.EntitySelectorConfig(multiple=True, domain="binary_sensor")
            ),
            vol.Optional(
                "notify_servicos_campainha",
                default=como_lista(d.get("notify_servicos_campainha", d.get("notify_service_name"))),
            ): _notify_selector(hass),
            vol.Optional(
                "alexa_notify_servicos_campainha",
                default=como_lista(
                    d.get("alexa_notify_servicos_campainha", d.get("alexa_notify_service"))
                ),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True, domain="notify", integration="alexa_devices")
            ),
            vol.Optional(
                "alexa_msg_campainha",
                default=d.get("alexa_msg_campainha", "Atenção, campainha acionada."),
            ): str,
            vol.Optional(
                "alexa_campainha_som_id",
                default=d.get("alexa_campainha_som_id", "amzn_sfx_doorbell_01"),
            ): str,
            vol.Optional(
                "alexa_campainha_som_dispositivos",
                default=como_lista(d.get("alexa_campainha_som_dispositivos")),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True, domain="notify", integration="alexa_devices")
            ),
        }
    )


def _schema_notificacoes(hass: HomeAssistant | None, d: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                "notify_servicos_sirene",
                default=como_lista(d.get("notify_servicos_sirene", d.get("notify_service_name"))),
            ): _notify_selector(hass),
            vol.Optional(
                "alexa_notify_servicos_alarme",
                default=como_lista(
                    d.get("alexa_notify_servicos_alarme", d.get("alexa_notify_service"))
                ),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True, domain="notify", integration="alexa_devices")
            ),
            vol.Optional(
                "alexa_msg_alarme",
                default=d.get("alexa_msg_alarme", "Atenção, o alarme foi disparado! {msg}"),
            ): str,
        }
    )


def _schema_automacao(hass: HomeAssistant | None, d: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("moradores", default=como_lista(d.get("moradores"))): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True, domain="person")
            ),
            vol.Optional(
                "rastreadores_omada", default=como_lista(d.get("rastreadores_omada"))
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True, domain="device_tracker")
            ),
            vol.Optional(
                "ativar_auto_armar", default=d.get("ativar_auto_armar", True)
            ): selector.BooleanSelector(),
            vol.Optional(
                "atraso_auto_armar", default=d.get("atraso_auto_armar", 2)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=60, step=1, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(
                "frigate_detect_ausente", default=como_lista(d.get("frigate_detect_ausente"))
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True, domain="switch")
            ),
            vol.Optional(
                "sensores_pessoa_ausente", default=como_lista(d.get("sensores_pessoa_ausente"))
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(multiple=True, domain="binary_sensor")
            ),
        }
    )


SCHEMAS = {
    "zonas": _schema_zonas,
    "campainha": _schema_campainha,
    "notificacoes": _schema_notificacoes,
    "automacao": _schema_automacao,
}


class MayaKnoxOptionsFlowHandler(OptionsFlow):
    """Edita uma seção por vez, preservando o restante da configuração."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry
        self._opcoes: dict = {**config_entry.data, **config_entry.options}

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=list(PASSOS))

    async def _passo(self, step_id: str, user_input):
        if user_input is not None:
            self._opcoes = mesclar_opcoes(self._opcoes, user_input)
            return self.async_create_entry(title="", data=self._opcoes)
        return self.async_show_form(
            step_id=step_id, data_schema=SCHEMAS[step_id](self.hass, self._opcoes)
        )

    async def async_step_zonas(self, user_input=None):
        return await self._passo("zonas", user_input)

    async def async_step_campainha(self, user_input=None):
        return await self._passo("campainha", user_input)

    async def async_step_notificacoes(self, user_input=None):
        return await self._passo("notificacoes", user_input)

    async def async_step_automacao(self, user_input=None):
        return await self._passo("automacao", user_input)


class MayaKnoxConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._dados: dict = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MayaKnoxOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return await self.async_step_zonas()

    async def _passo(self, step_id: str, proximo: str | None, user_input):
        if user_input is not None:
            self._dados = mesclar_opcoes(self._dados, user_input)
            if proximo:
                return await getattr(self, f"async_step_{proximo}")()
            return self.async_create_entry(title="Central Maya Knox", data=self._dados)
        return self.async_show_form(step_id=step_id, data_schema=SCHEMAS[step_id](self.hass, {}))

    async def async_step_zonas(self, user_input=None):
        return await self._passo("zonas", "campainha", user_input)

    async def async_step_campainha(self, user_input=None):
        return await self._passo("campainha", "notificacoes", user_input)

    async def async_step_notificacoes(self, user_input=None):
        return await self._passo("notificacoes", "automacao", user_input)

    async def async_step_automacao(self, user_input=None):
        return await self._passo("automacao", None, user_input)
