const BASE =
  "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/" +
  "CotacaoDolarDia(dataCotacao=@dataCotacao)?@dataCotacao='{DATE}'&$format=json";

function mmddyyyy(d) {
  const p = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Sao_Paulo",
    year: "numeric", month: "2-digit", day: "2-digit"
  }).formatToParts(d);
  const g = (t) => p.find((x) => x.type === t).value;
  return `${g("month")}-${g("day")}-${g("year")}`;
}
function ddmmyyyy(d) {
  const p = new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    year: "numeric", month: "2-digit", day: "2-digit"
  }).formatToParts(d);
  const g = (t) => p.find((x) => x.type === t).value;
  return `${g("day")}/${g("month")}/${g("year")}`;
}

async function fetchPtaxForDate(d) {
  const url = BASE.replace("{DATE}", mmddyyyy(d));
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) return null;
  const j = await r.json();
  if (!j.value || !j.value.length) return null;
  const v = j.value[j.value.length - 1];
  return {
    compra: Number(v.cotacaoCompra),
    venda: Number(v.cotacaoVenda),
    dataBR: ddmmyyyy(d),
    dataHoraCotacao: v.dataHoraCotacao,
  };
}

// Busca a ÚLTIMA PTAX disponível (tenta hoje, depois vai voltando dias)
export async function getLastPtaxUsdBrl(maxBackDays = 10) {
  const hoje = new Date();
  for (let i = 0; i <= maxBackDays; i++) {
    const d = new Date(hoje);
    d.setDate(d.getDate() - i);
    const ptax = await fetchPtaxForDate(d);
    if (ptax) return ptax;
  }
  throw new Error("PTAX não encontrada nos últimos dias.");
}
