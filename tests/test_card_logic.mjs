/**
 * Verificação da lógica do card (sem navegador).
 * Rode: node tests/test_card_logic.mjs
 */
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const arquivo = path.resolve(import.meta.dirname, "..", "www", "maya-knox-card.js");

globalThis.window = globalThis;
globalThis.HTMLElement = class {};
const registrados = [];
globalThis.customElements = {
  get: () => undefined,
  define: (nome) => registrados.push(nome),
};

vm.runInThisContext(fs.readFileSync(arquivo, "utf8"), { filename: arquivo });

const { esc, classificarSensorEstado, ESTADOS, VERSION } = globalThis.mayaKnoxInternals;

let falhas = 0;
function eq(rotulo, obtido, esperado) {
  const ok = JSON.stringify(obtido) === JSON.stringify(esperado);
  if (!ok) {
    falhas++;
    console.error(`FALHOU ${rotulo}: obtido ${JSON.stringify(obtido)}, esperado ${JSON.stringify(esperado)}`);
  }
}

// versão única e cache-bust coerente
eq("VERSION", VERSION, "1.3.2");

// escape: friendly_name / log vêm de fora, não podem virar HTML
eq("esc <", esc("<img onerror=1>"), "&lt;img onerror=1&gt;");
eq("esc aspas", esc(`a"b'c&d`), "a&quot;b&#39;c&amp;d");
eq("esc vazio", esc(undefined), "");

// câmera morta não pode aparecer como "ok"
eq("sem estado", classificarSensorEstado(undefined).tom, "sem_sinal");
eq("unavailable", classificarSensorEstado({ state: "unavailable" }).tom, "sem_sinal");
eq("unknown", classificarSensorEstado({ state: "unknown" }).tom, "sem_sinal");
eq("idle", classificarSensorEstado({ state: "idle" }).tom, "ok");
eq("recording", classificarSensorEstado({ state: "recording" }).tom, "ok");
eq("on", classificarSensorEstado({ state: "on" }).tom, "alerta");
eq("estado novo", classificarSensorEstado({ state: "coisa_nova" }).tom, "sem_sinal");

// estados que antes caíam no toUpperCase() cru
for (const estado of ["arming", "pending", "armed_night", "armed_vacation", "triggered", "disarmed"]) {
  eq(`estado mapeado ${estado}`, typeof ESTADOS[estado]?.texto, "string");
}
eq("card registrado", registrados, ["maya-knox-card"]);

if (falhas) {
  console.error(`\n${falhas} verificação(ões) falharam`);
  process.exit(1);
}
console.log("OK — lógica do card (escape, estados, versão)");
