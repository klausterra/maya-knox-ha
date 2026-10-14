const VERSION = "1.3.2";

console.info(
  `%c MAYA KNOX PORTAL %c ${VERSION} `,
  "color: white; background: #00d4ff; font-weight: 700;",
  "color: #00d4ff; background: #1c1c1c; font-weight: 700;",
);

const LOGO_FALLBACK = `/maya_knox_static/security_robot.png?v=${VERSION}`;

/** Estados do alarm_control_panel → rótulo/cores. Fora do mapa = desconhecido (cinza). */
const ESTADOS = {
  disarmed: { texto: "DESARMADO", cor: "#4caf50" },
  armed_home: { texto: "ARMADO (CASA)", cor: "#ffa500" },
  armed_away: { texto: "ARMADO (RUA)", cor: "#ffa500" },
  armed_night: { texto: "ARMADO (NOITE)", cor: "#ffa500" },
  armed_vacation: { texto: "ARMADO (VIAGEM)", cor: "#ffa500" },
  arming: { texto: "ARMANDO…", cor: "#ffa500" },
  pending: { texto: "AGUARDANDO…", cor: "#ffa500" },
  triggered: { texto: "DISPARADO", cor: "#ff0000" },
};

const COR_OK = "#4caf50";
const COR_ALERTA = "#ff4d4d";
const COR_SEM_SINAL = "#f5c542";
const COR_DESCONHECIDO = "#888";

/** @param {unknown} valor */
function esc(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[c]);
}

const SEM_SINAL = new Set(["unknown", "unavailable", "none", ""]);

/**
 * Classifica um sensor para a lista do card.
 * Nunca devolve "ok" por omissão: estado não reconhecido vira "sem sinal",
 * para uma câmera morta não aparecer com check verde.
 * @param {{state?: string} | undefined} state
 */
function classificarSensorEstado(state) {
  const valor = String(state?.state ?? "").toLowerCase();
  if (SEM_SINAL.has(valor)) {
    return { tom: "sem_sinal", icone: "mdi:help-circle-outline", cor: COR_SEM_SINAL, rotulo: "sem sinal" };
  }
  if (valor === "on" || valor === "open" || valor === "detected") {
    return { tom: "alerta", icone: "mdi:alert-circle", cor: COR_ALERTA, rotulo: "acionado" };
  }
  if (["off", "closed", "idle", "streaming", "recording", "home", "clear"].includes(valor)) {
    return { tom: "ok", icone: "mdi:check-circle", cor: COR_OK, rotulo: "ok" };
  }
  return { tom: "sem_sinal", icone: "mdi:help-circle-outline", cor: COR_SEM_SINAL, rotulo: valor || "sem sinal" };
}

class MayaKnoxCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("maya-knox-card: defina 'entity' (alarm_control_panel.maya_knox_portal).");
    }
    this.config = config;
    this._assinatura = {};
  }

  getCardSize() {
    return 12;
  }

  set hass(hass) {
    if (!this.config) return;
    this._hass = hass;
    if (!this._montado) this._montarShell();

    const entityId = this.config.entity;
    const state = hass.states[entityId];
    this._atualizarCabecalho(state, entityId);
    this._atualizarSensores(state, hass);
    this._atualizarRegistro(state);
    this._sincronizarBotoes(state);
  }

  get hass() {
    return this._hass;
  }

  // ---------- shell (uma vez) ----------

  _montarShell() {
    const logoUrl = this._logoUrl();
    const nome = this.config.name || "Maya Knox";
    this.innerHTML = `
      <ha-card style="overflow: hidden; border-radius: 15px; background: #1c1c1c; color: white; padding: 16px; text-align: center; position: relative;">
        <style>
          .maya-link { color: #888; text-decoration: none; display: flex; align-items: center; gap: 4px; transition: color .3s; }
          .maya-link:hover { color: #00d4ff; }
          .maya-acao { cursor: pointer; display: flex; flex-direction: column; align-items: center; transition: transform .2s, opacity .2s; background: none; border: 0; color: inherit; padding: 4px 8px; font: inherit; }
          .maya-acao:hover { transform: scale(1.1); }
          .maya-acao:focus-visible { outline: 2px solid #00d4ff; outline-offset: 2px; border-radius: 8px; }
          #btn-settings { background: none; border: 0; cursor: pointer; color: #888; transition: color .3s; padding: 4px; }
          #btn-settings:hover, #btn-settings:focus-visible { color: white; }
          [data-busy="1"] .maya-acao, [data-busy="1"] #btn-settings { opacity: .45; pointer-events: none; }
        </style>

        <button id="btn-settings" type="button" aria-label="Configurar a entidade">
          <ha-icon icon="mdi:cog"></ha-icon>
        </button>

        <div id="status-glow" style="width: 100px; height: 100px; margin: 0 auto; border-radius: 50%; display: flex; align-items: center; justify-content: center; transition: all .5s ease; box-shadow: 0 0 15px ${COR_OK};">
          <img id="logo" alt="" src="${esc(logoUrl)}" style="width: 90px; height: 90px; border-radius: 50%; border: 2px solid #00d4ff;">
        </div>

        <div style="margin-top: 10px;">
          <span style="font-size: 18px; font-weight: bold; display: block;">${esc(nome)}</span>
          <span id="state-text" style="font-size: 12px; text-transform: uppercase;">—</span>
          <div id="sensor-text" style="font-size: 11px; color: ${COR_ALERTA}; font-weight: bold; margin-top: 5px;"></div>
          <div id="feedback" role="status" aria-live="polite" style="font-size: 11px; color: #888; margin-top: 5px; min-height: 13px;"></div>
        </div>

        <div style="margin-top: 20px; text-align: left; background: rgba(255,255,255,.05); padding: 10px; border-radius: 10px;">
          <div style="font-size: 12px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 8px; color: #00d4ff;">SENSORES</div>
          <div id="sensor-list" style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;"></div>
        </div>

        <div style="margin-top: 10px; text-align: left; background: rgba(255,255,255,.05); padding: 10px; border-radius: 10px;">
          <div style="font-size: 12px; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px; margin-bottom: 8px; color: #00d4ff;">REGISTRO</div>
          <div id="log-list" style="font-size: 11px; color: #aaa; max-height: 100px; overflow-y: auto;"></div>
        </div>

        <div id="acoes" style="margin-top: 15px; display: flex; justify-content: space-around; background: rgba(0,0,0,.2); padding: 10px; border-radius: 10px;">
          <button id="btn-home" class="maya-acao" type="button" style="color: #ffa500;" aria-label="Armar em casa">
            <ha-icon icon="mdi:shield-home" style="--mdc-icon-size: 32px;"></ha-icon>
            <span style="font-size: 10px; margin-top: 4px; font-weight: bold;">CASA</span>
          </button>
          <button id="btn-away" class="maya-acao" type="button" style="color: ${COR_ALERTA};" aria-label="Armar para sair (rua)">
            <ha-icon icon="mdi:shield-lock" style="--mdc-icon-size: 32px;"></ha-icon>
            <span style="font-size: 10px; margin-top: 4px; font-weight: bold;">RUA</span>
          </button>
          <button id="btn-disarm" class="maya-acao" type="button" style="color: ${COR_OK};" aria-label="Desarmar alarme">
            <ha-icon icon="mdi:shield-off" style="--mdc-icon-size: 32px;"></ha-icon>
            <span id="btn-disarm-label" style="font-size: 10px; margin-top: 4px; font-weight: bold;">DESARMAR</span>
          </button>
        </div>

        <div style="margin-top: 15px; padding: 10px; border-top: 1px solid #333; display: flex; justify-content: space-between; align-items: center; font-size: 10px;">
          <a href="https://www.instagram.com/mayahome.oficial" target="_blank" rel="noopener noreferrer" class="maya-link">
            <ha-icon icon="mdi:instagram" style="--mdc-icon-size: 14px;"></ha-icon>
            <span>@mayahome.oficial</span>
          </a>
          <a href="https://www.mayahome.ia.br" target="_blank" rel="noopener noreferrer" class="maya-link">
            <ha-icon icon="mdi:web" style="--mdc-icon-size: 14px;"></ha-icon>
            <span>www.mayahome.ia.br</span>
          </a>
        </div>
        <div style="position: absolute; bottom: 2px; right: 5px; font-size: 8px; color: #444;">v${VERSION}</div>
      </ha-card>
    `;

    this.querySelector("#btn-settings").addEventListener("click", () => {
      const event = new Event("hass-more-info", { bubbles: true, composed: true });
      event.detail = { entityId: this.config.entity };
      this.dispatchEvent(event);
    });
    this.querySelector("#btn-home").addEventListener("click", () => this._chamar("alarm_arm_home", "Armando (Casa)…"));
    this.querySelector("#btn-away").addEventListener("click", () => this._chamar("alarm_arm_away", "Armando (Rua)…"));
    this.querySelector("#btn-disarm").addEventListener("click", () => this._desarmarComConfirmacao());

    this._montado = true;
  }

  _logoUrl() {
    const state = this._hass?.states?.[this.config.entity];
    return state?.attributes?.entity_picture || LOGO_FALLBACK;
  }

  // ---------- ações ----------

  async _chamar(servico, feedback) {
    this._cancelarConfirmacao();
    this._setBusy(true, feedback);
    try {
      await this._hass.callService("alarm_control_panel", servico, { entity_id: this.config.entity });
      this._setBusy(false, "");
    } catch (err) {
      this._setBusy(false, `Não deu para enviar: ${err?.message || err}`);
    }
  }

  /** Toque acidental no bolso não pode desarmar: exige segundo toque em 3s. */
  _desarmarComConfirmacao() {
    const label = this.querySelector("#btn-disarm-label");
    if (!this._confirmando) {
      this._confirmando = true;
      if (label) label.textContent = "CONFIRMAR?";
      this._confirmTimer = window.setTimeout(() => this._cancelarConfirmacao(), 3000);
      this._feedback("Toque de novo para desarmar.");
      return;
    }
    this._cancelarConfirmacao();
    void this._chamar("alarm_disarm", "Desarmando…");
  }

  _cancelarConfirmacao() {
    this._confirmando = false;
    if (this._confirmTimer) window.clearTimeout(this._confirmTimer);
    this._confirmTimer = null;
    const label = this.querySelector("#btn-disarm-label");
    if (label) label.textContent = "DESARMAR";
  }

  _setBusy(busy, mensagem) {
    this.dataset.busy = busy ? "1" : "0";
    this._feedback(busy ? mensagem : "");
  }

  _feedback(texto) {
    const el = this.querySelector("#feedback");
    if (el) el.textContent = texto || "";
  }

  // ---------- render ----------

  _atualizarCabecalho(state, entityId) {
    const chave = `${entityId}|${state?.state ?? "ausente"}|${state?.attributes?.sensor_disparo ?? ""}`;
    if (this._assinatura.cabecalho === chave) return;
    this._assinatura.cabecalho = chave;

    const stateText = this.querySelector("#state-text");
    const glow = this.querySelector("#status-glow");
    const sensorText = this.querySelector("#sensor-text");

    if (!state) {
      stateText.textContent = "CENTRAL NÃO ENCONTRADA";
      stateText.style.color = COR_SEM_SINAL;
      glow.style.boxShadow = `0 0 15px ${COR_SEM_SINAL}`;
      sensorText.textContent = `Confira a entidade: ${entityId}`;
      return;
    }

    const info = ESTADOS[String(state.state).toLowerCase()];
    stateText.textContent = info ? info.texto : `NÃO MAPEADO: ${String(state.state).toUpperCase()}`;
    stateText.style.color = info ? info.cor : COR_DESCONHECIDO;
    glow.style.boxShadow = `0 0 ${state.state === "triggered" ? 25 : 15}px ${info ? info.cor : COR_DESCONHECIDO}`;

    if (state.state === "triggered") {
      sensorText.textContent = `DISPARO EM: ${esc(state.attributes.sensor_disparo || "zona não informada")}`;
    } else {
      sensorText.textContent = "";
    }
  }

  _atualizarSensores(state, hass) {
    const sensores = state?.attributes?.sensors || [];
    const chave = sensores.map((s) => `${s}:${hass.states[s]?.state ?? "-"}`).join("|");
    if (this._assinatura.sensores === chave) return;
    this._assinatura.sensores = chave;

    const lista = this.querySelector("#sensor-list");
    if (!sensores.length) {
      lista.innerHTML = `<div style="color: #666; font-style: italic; font-size: 10px;">Nenhum sensor configurado</div>`;
      return;
    }
    lista.innerHTML = sensores
      .map((sId) => {
        const sState = hass.states[sId];
        const nome = sState?.attributes?.friendly_name || sId;
        const info = classificarSensorEstado(sState);
        return `
          <div style="display: flex; align-items: center; gap: 6px;" title="${esc(nome)}: ${esc(info.rotulo)}">
            <ha-icon icon="${info.icone}" style="color: ${info.cor}; --mdc-icon-size: 14px;"></ha-icon>
            <span style="font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: ${info.cor}; max-width: 100px;">${esc(nome)}</span>
          </div>`;
      })
      .join("");
  }

  _atualizarRegistro(state) {
    const logs = state?.attributes?.recent_logs || [];
    const chave = `${logs.length}|${logs[logs.length - 1]?.time ?? ""}|${logs[logs.length - 1]?.action ?? ""}`;
    if (this._assinatura.registro === chave) return;
    this._assinatura.registro = chave;

    const lista = this.querySelector("#log-list");
    if (!logs.length) {
      lista.innerHTML = `<div style="text-align: center; padding: 10px 0; color: #666; font-style: italic;">Nenhum evento foi registrado ainda...</div>`;
      return;
    }
    lista.innerHTML = logs
      .slice()
      .reverse()
      .map((log) => {
        const disparo = String(log.action || "").toUpperCase() === "DISPARO";
        const acao = disparo
          ? `<span style="color: ${COR_ALERTA}; font-weight: 700;">${esc(log.action)}</span>`
          : `<span style="color: white;">${esc(log.action)}</span>`;
        return `
          <div style="margin-bottom: 4px; border-bottom: 1px solid #2c2c2c; padding-bottom: 2px; display: flex; justify-content: space-between; gap: 8px;${disparo ? ` background: rgba(255,77,77,.08);` : ""}">
            <span><span style="color: ${COR_OK};">[${esc(log.time)}]</span> ${acao}</span>
            <span style="color: #888; font-style: italic;">${esc(log.info)}</span>
          </div>`;
      })
      .join("");
  }

  _sincronizarBotoes(state) {
    const desarmado = state?.state === "disarmed";
    const home = this.querySelector("#btn-home");
    const away = this.querySelector("#btn-away");
    const disarm = this.querySelector("#btn-disarm");
    if (!home) return;

    const marcar = (el, ativo) => {
      el.setAttribute("aria-pressed", ativo ? "true" : "false");
      el.style.textDecoration = ativo ? "underline" : "none";
      el.querySelector("ha-icon").style.opacity = ativo ? "1" : ".7";
    };
    marcar(home, state?.state === "armed_home");
    marcar(away, state?.state === "armed_away");
    marcar(disarm, desarmado);
    disarm.disabled = desarmado;
    disarm.style.opacity = desarmado ? ".35" : "1";
  }

  static getStubConfig() {
    return { entity: "alarm_control_panel.maya_knox_portal", name: "Central Maya Knox" };
  }
}

// Exposto para teste (tests/test_card_logic.mjs) — sem efeito no Home Assistant.
window.mayaKnoxInternals = { esc, classificarSensorEstado, ESTADOS, VERSION };

if (!customElements.get("maya-knox-card")) customElements.define("maya-knox-card", MayaKnoxCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "maya-knox-card",
  name: "Maya Knox Security",
  description: "Painel de controle avançado Maya Knox para Hipercube.",
  icon: "mdi:shield-check",
  preview: true,
});
