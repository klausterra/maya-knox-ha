/**
 * Renderiza o card com um DOM stub e dados REAIS do Home Assistant do Klaus.
 * Verifica o que o usuário veria: estados, cor de sensor morto, escape e desarme.
 * Rode: node tests/test_card_render.mjs
 */
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

class StubNode {
  constructor() {
    this.style = {};
    this.dataset = {};
    this.attrs = {};
    this.children = new Map();
    this.handlers = {};
    this._html = "";
    this.textContent = "";
    this.disabled = false;
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  set innerHTML(v) {
    this._html = String(v);
    this.children = new Map();
    for (const m of this._html.matchAll(/id="([^"]+)"/g)) this.children.set(m[1], new StubNode());
  }
  get innerHTML() {
    return this._html;
  }
  querySelector(sel) {
    if (sel.startsWith("#")) return this.children.get(sel.slice(1)) ?? null;
    return new StubNode();
  }
  addEventListener(ev, fn) {
    (this.handlers[ev] ||= []).push(fn);
  }
  click() {
    // navegador não dispara click em botão disabled
    if (this.disabled) return;
    for (const fn of this.handlers.click ?? []) fn();
  }
  setAttribute(k, v) {
    this.attrs[k] = v;
  }
  getAttribute(k) {
    return this.attrs[k];
  }
  dispatchEvent() {
    return true;
  }
}

const timers = [];
globalThis.window = globalThis;
globalThis.HTMLElement = StubNode;
globalThis.setTimeout = (fn) => {
  timers.push(fn);
  return timers.length;
};
globalThis.clearTimeout = (id) => {
  if (id) timers[id - 1] = null;
};
globalThis.customElements = { get: () => undefined, define: () => {} };

const arquivo = path.resolve(import.meta.dirname, "..", "www", "maya-knox-card.js");
vm.runInThisContext(fs.readFileSync(arquivo, "utf8"), { filename: arquivo });
const { MayaKnoxCard } = { MayaKnoxCard: globalThis.MayaKnoxCard ?? vm.runInThisContext("MayaKnoxCard") };

let falhas = 0;
function ok(rotulo, condicao, detalhe = "") {
  if (!condicao) {
    falhas++;
    console.error(`FALHOU ${rotulo}${detalhe ? ` — ${detalhe}` : ""}`);
  }
}

/** Dados reais do HA do Klaus (sensores e logs vieram do core.restore_state). */
function hassReal(opcoes = {}) {
  const states = {
    "alarm_control_panel.maya_knox_portal": {
      state: opcoes.estado ?? "disarmed",
      attributes: {
        sensor_disparo: opcoes.sensorDisparo ?? null,
        sensors: [
          "camera.direita",
          "camera.esquerda",
          "camera.living",
          "binary_sensor.lt_sp_living_presenca",
        ],
        recent_logs: opcoes.logs ?? [
          { time: "13/10 16:48:55", action: "Armado (Rua)", info: "" },
          { time: "28/06 21:03:37", action: "DISPARO", info: "LT SP Living Presença " },
        ],
        entity_picture: "data:image/png;base64,AAA",
      },
    },
    "camera.direita": { state: "idle", attributes: { friendly_name: "Direita" } },
    "camera.esquerda": { state: "recording", attributes: { friendly_name: "Esquerda" } },
    // câmera fora do ar: o card antigo pintava de verde
    "camera.living": { state: "unavailable", attributes: { friendly_name: opcoes.nomeHostil ?? "Living" } },
    "binary_sensor.lt_sp_living_presenca": {
      state: "on",
      attributes: { friendly_name: "LT SP Living Presença" },
    },
  };
  const chamadas = [];
  return {
    chamadas,
    states,
    callService: (dominio, servico, dados) => {
      chamadas.push({ dominio, servico, dados });
      return Promise.resolve();
    },
  };
}

function montar(hass) {
  const card = new MayaKnoxCard();
  card.setConfig({ entity: "alarm_control_panel.maya_knox_portal", name: "Central Maya Knox" });
  card.hass = hass;
  return card;
}

// ---- 1. desarmado com câmera fora do ar ----
let hass = hassReal();
let card = montar(hass);
ok("estado desarmado", card.querySelector("#state-text").textContent === "DESARMADO");
const sensoresHtml = card.querySelector("#sensor-list").innerHTML;
ok("câmera unavailable NÃO fica verde", !/color: #4caf50[^>]*>\s*Living|#4caf50[^<]*Living/.test(sensoresHtml), sensoresHtml.slice(0, 200));
ok("câmera unavailable marcada como sem sinal", sensoresHtml.includes("#f5c542"), "esperado amarelo de sem sinal");
ok("câmera idle conta como ok", sensoresHtml.includes('title="Direita: ok"'));
ok("sensor de presença acionado", sensoresHtml.includes('title="LT SP Living Presença: acionado"'));
ok("registro destaca DISPARO", card.querySelector("#log-list").innerHTML.includes("#ff4d4d"));
ok("desarmado desabilita o botão desarmar", card.querySelector("#btn-disarm").disabled === true);

// ---- 2. entidade ausente não pode mentir que está desarmada ----
card = montar({ states: {}, callService: () => Promise.resolve() });
ok("entidade ausente avisa", card.querySelector("#state-text").textContent === "CENTRAL NÃO ENCONTRADA");
ok("entidade ausente mostra o id", card.querySelector("#sensor-text").textContent.includes("maya_knox_portal"));

// ---- 3. armado em rua / disparo ----
card = montar(hassReal({ estado: "armed_away" }));
ok("armado em rua", card.querySelector("#state-text").textContent === "ARMADO (RUA)");
card = montar(hassReal({ estado: "arming" }));
ok("estado arming traduzido", card.querySelector("#state-text").textContent === "ARMANDO…");
card = montar(hassReal({ estado: "triggered", sensorDisparo: "LT SP Living Presença" }));
ok("disparo nomeia a zona", card.querySelector("#sensor-text").textContent.includes("DISPARO EM: LT SP Living Presença"));

// ---- 4. escape de HTML hostil em friendly_name ----
card = montar(hassReal({ nomeHostil: '<img src=x onerror="alert(1)">' }));
const html = card.querySelector("#sensor-list").innerHTML;
ok("friendly_name hostil escapado", !html.includes("<img"), html.slice(0, 160));
ok("friendly_name hostil virou entidade", html.includes("&lt;img"));

// ---- 5. desarme: um toque só confirma, dois desarmam ----
hass = hassReal();
card = montar(hass);
const botao = card.querySelector("#btn-disarm");
ok("desarmado não dispara serviço (botão inerte)", (botao.click(), hass.chamadas.length === 0));
hass = hassReal({ estado: "armed_away" });
card = montar(hass);
const botao2 = card.querySelector("#btn-disarm");
botao2.click();
ok("1º toque não desarma", hass.chamadas.length === 0, JSON.stringify(hass.chamadas));
ok("1º toque pede confirmação", card.querySelector("#btn-disarm-label").textContent === "CONFIRMAR?");
ok("1º toque avisa o usuário", card.querySelector("#feedback").textContent.includes("Toque de novo"));
botao2.click();
await new Promise((r) => process.nextTick(r));
ok("2º toque desarma uma única vez", hass.chamadas.length === 1, JSON.stringify(hass.chamadas));
ok("2º toque chamou alarm_disarm", hass.chamadas[0]?.servico === "alarm_disarm");
ok("2º toque usou a entidade configurada", hass.chamadas[0]?.dados.entity_id === "alarm_control_panel.maya_knox_portal");

// ---- 6. confirmação expira sozinha após 3s ----
hass = hassReal({ estado: "armed_away" });
card = montar(hass);
timers.length = 0;
card.querySelector("#btn-disarm").click();
const pendente = timers.find((fn) => typeof fn === "function");
ok("existe timer de expiração", Boolean(pendente));
pendente?.();
ok("expirou sem desarmar", hass.chamadas.length === 0);
ok("expirou voltou o rótulo", card.querySelector("#btn-disarm-label").textContent === "DESARMAR");

// ---- 7. armar casa/rua usa a entidade certa ----
hass = hassReal();
card = montar(hass);
card.querySelector("#btn-home").click();
card.querySelector("#btn-away").click();
await new Promise((r) => process.nextTick(r));
ok("casa e rua chamados", hass.chamadas.map((c) => c.servico).join(",") === "alarm_arm_home,alarm_arm_away", JSON.stringify(hass.chamadas));

if (falhas) {
  console.error(`\n${falhas} verificação(ões) falharam`);
  process.exit(1);
}
console.log("OK — card renderizado com dados reais do HA (11 cenários)");
