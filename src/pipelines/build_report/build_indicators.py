from __future__ import annotations

from typing import Callable, Literal, NamedTuple

from src.pipelines.macro_indicators import MacroIndicatorsResult
from src.pipelines.build_report.models import IndicatorReport

Color = Literal["green", "grey", "red"]


class _Cfg(NamedTuple):
    name: str
    value_fn: Callable[[MacroIndicatorsResult], float | None]
    color_fn: Callable[[MacroIndicatorsResult], Color]
    help: str
    unit: str = ""
    label_fn: Callable[[MacroIndicatorsResult], str | None] = lambda r: None


def _clamp(val: float | None, low: float, high: float, invert: bool = False) -> Color:
    if val is None:
        return "grey"
    if not invert:
        return "green" if val <= low else "red" if val >= high else "grey"
    return "green" if val >= high else "red" if val <= low else "grey"


_CONFIGS: list[_Cfg] = [
    _Cfg(
        name="VIX (Indice di Volatilità)",
        value_fn=lambda r: r.vix,
        color_fn=lambda r: _clamp(r.vix, 15.0, 25.0),
        help=(
            "Il VIX del CBOE misura la volatilità implicita a 30 giorni delle opzioni sull'S&P 500 — "
            "il 'termometro della paura' dei mercati. "
            "Sotto 15 = ambiente calmo, scarsa paura (verde). 15–25 = incertezza normale. "
            "Sopra 25 = paura elevata; picchi oltre 40 coincidono storicamente con sell-off importanti. "
            "Il VIX si muove tipicamente in senso inverso ai prezzi azionari."
        ),
    ),
    _Cfg(
        name="Indice Paura & Avidità",
        value_fn=lambda r: r.fear_greed,
        color_fn=lambda r: (
            "green" if r.fear_greed is not None and r.fear_greed > 60 else
            "red"   if r.fear_greed is not None and r.fear_greed < 40 else
            "grey"
        ),
        help=(
            "Indicatore di sentiment composito della CNN (0–100) derivato da 7 segnali: momentum dei prezzi, "
            "rapporto put/call, VIX, domanda di beni rifugio, spread high yield, ampiezza del mercato e forza dei prezzi. "
            "Sopra 60 = avidità (rialzista). Sotto 40 = paura (ribassista). "
            "Le letture estreme sono contrarian: l'avidità estrema può precedere correzioni; "
            "la paura estrema segna spesso i minimi."
        ),
        label_fn=lambda r: r.fear_greed_rating,
    ),
    _Cfg(
        name="Curva dei Rendimenti (10A–3M)",
        value_fn=lambda r: r.yield_curve_10y3m,
        color_fn=lambda r: (
            "green" if r.yield_curve_10y3m is not None and r.yield_curve_10y3m > 0.5 else
            "red"   if r.yield_curve_10y3m is not None and r.yield_curve_10y3m < -0.5 else
            "grey"
        ),
        help=(
            "Spread tra rendimenti Treasury USA a 10 anni e 3 mesi. Positivo = curva normale (verde). "
            "Negativa (invertita) ha preceduto ogni recessione USA dagli anni '60, "
            "tipicamente con 6–18 mesi di anticipo. "
            "Sopra +0,5% = sana. Sotto -0,5% = inversione = segnale di recessione (rosso)."
        ),
        unit="pct+",
    ),
    _Cfg(
        name="Tasso Fed Funds",
        value_fn=lambda r: r.fed_funds_rate,
        color_fn=lambda r: (
            "green" if r.fed_funds_rate is not None and r.fed_funds_rate < 3.0 else
            "red"   if r.fed_funds_rate is not None and r.fed_funds_rate > 5.0 else
            "grey"
        ),
        help=(
            "Il tasso di prestito interbancario overnight fissato dalla Federal Reserve — il costo base del denaro. "
            "Tassi bassi (<3%) = politica accomodante, credito a buon mercato, supporta le valutazioni azionarie. "
            "Tassi alti (>5%) = politica restrittiva, comprime i multipli delle growth stock e aumenta il costo del debito. "
            "La direzione del tasso conta quanto il livello: un ciclo di tagli è rialzista, un ciclo di rialzi è ribassista."
        ),
        unit="pct",
    ),
    _Cfg(
        name="Probabilità Taglio Fed",
        value_fn=lambda r: r.fed_cut_probability_pct,
        color_fn=lambda r: "grey",
        help=(
            "Probabilità CME FedWatch di un taglio di 25bp alla prossima riunione FOMC — "
            "derivata dai futures sui fed funds. "
            "Alta probabilità di taglio è rialzista per azioni e obbligazioni; "
            "alta probabilità di rialzo è ribassista, specialmente per le growth stock e le obbligazioni a lunga duration."
        ),
        unit="pct",
    ),
    _Cfg(
        name="Bilancio della Fed",
        value_fn=lambda r: r.fed_balance_sheet_trn,
        color_fn=lambda r: (
            "green" if r.fed_balance_sheet_trn is not None and r.fed_balance_sheet_trn > 8.0 else
            "red"   if r.fed_balance_sheet_trn is not None and r.fed_balance_sheet_trn < 7.0 else
            "grey"
        ),
        help=(
            "Gli attivi totali della Fed — principalmente Treasury e titoli garantiti da mutui. "
            "Un bilancio in espansione (QE) immette liquidità, sostenendo i prezzi degli asset. "
            "In contrazione (QT), sottrae liquidità, mettendo pressione alle valutazioni. "
            "Una dimensione >$8T riflette un'accomodazione storicamente elevata; "
            "una contrazione rapida è un vento contrario alla liquidità."
        ),
        unit="T$",
    ),
    _Cfg(
        name="M2 USA (YoY%)",
        value_fn=lambda r: r.m2_us_yoy_pct,
        color_fn=lambda r: (
            "green" if r.m2_us_yoy_pct is not None and 2.0 <= r.m2_us_yoy_pct <= 8.0 else
            "red"   if r.m2_us_yoy_pct is not None and r.m2_us_yoy_pct < 0 else
            "grey"
        ),
        help=(
            "L'M2 USA include contanti, depositi, risparmi e fondi monetari — la misura monetaria più ampia comunemente usata. "
            "Crescita rapida (>8% annuo) alimenta inflazione e bolle degli asset. "
            "Crescita negativa (contrazione monetaria) è storicamente rara e precede stress economico. "
            "Crescita moderata (2–8%) supporta l'attività normale."
        ),
        unit="pct+",
        label_fn=lambda r: f"${r.m2_us_trn:.1f}T" if r.m2_us_trn is not None else None,
    ),
    _Cfg(
        name="M2 Globale",
        value_fn=lambda r: r.global_m2_trn,
        color_fn=lambda r: "grey",
        help=(
            "Aggregato della massa monetaria delle principali economie in dollari equivalenti. "
            "Quando le banche centrali globali espandono M2 in sincronia, le condizioni finanziarie si allentano, "
            "sostenendo azioni e asset rischiosi. "
            "Quando contraggono insieme (come nel 2022), gli asset rischiosi tendono a calare in parallelo. "
            "Le variazioni dell'M2 globale tendono a precedere i mercati azionari di circa 3–6 mesi."
        ),
        unit="T$",
    ),
    _Cfg(
        name="RRP Notturno Fed",
        value_fn=lambda r: r.rrp_facility_bln,
        color_fn=lambda r: (
            "green" if r.rrp_facility_bln is not None and r.rrp_facility_bln < 100 else
            "red"   if r.rrp_facility_bln is not None and r.rrp_facility_bln > 500 else
            "grey"
        ),
        help=(
            "Contante parcheggiato dai fondi del mercato monetario presso la Fed overnight. "
            "Quando elevato (>$500 mld), la liquidità in eccesso è intrappolata alla Fed "
            "piuttosto che fluire nei mercati. "
            "Un RRP in calo è rialzista: quella liquidità si sposta in T-bill e altri asset. "
            "Vicino a zero significa che la liquidità in eccesso post-pandemia è completamente assorbita."
        ),
        unit="B$",
    ),
    _Cfg(
        name="Debito su Margine FINRA",
        value_fn=lambda r: r.finra_margin_debt_bln,
        color_fn=lambda r: "grey",
        help=(
            "Capitale totale preso in prestito dagli investitori per acquistare titoli su margine. "
            "Debito su margine alto e in crescita indica leva finanziaria e fiducia degli investitori — ma anche fragilità. "
            "Cali bruschi innescano liquidazioni forzate (margin call), amplificando i sell-off di mercato. "
            "Rapide aumenti vicino ai massimi storici sono un classico segnale di fine ciclo."
        ),
        unit="B$",
    ),
    _Cfg(
        name="Rapporto SPY/M2",
        value_fn=lambda r: r.spy_m2_ratio,
        color_fn=lambda r: (
            "green" if r.spy_m2_ratio_label == "compressed" else
            "red"   if r.spy_m2_ratio_label == "elevated"   else
            "grey"
        ),
        help=(
            "Livello dell'S&P 500 diviso per M2 USA in trilioni — una misura di valutazione corretta per la liquidità. "
            "Compressa (<150): le azioni sono economiche rispetto alla massa monetaria. "
            "Elevata (>250): le azioni sono care rispetto alla liquidità, aumentando il rischio di correzione. "
            "Distingue i movimenti di mercato guidati da crescita reale da quelli guidati puramente dall'espansione monetaria."
        ),
        label_fn=lambda r: r.spy_m2_ratio_label,
    ),
    _Cfg(
        name="Breakeven Inflazione 5A",
        value_fn=lambda r: r.breakeven_5y,
        color_fn=lambda r: (
            "green" if r.breakeven_5y is not None and 1.5 <= r.breakeven_5y <= 2.5 else
            "red"   if r.breakeven_5y is not None and r.breakeven_5y > 3.0 else
            "grey"
        ),
        help=(
            "Aspettativa media annua di inflazione implicita di mercato a 5 anni, "
            "dallo spread tra TIPS e rendimenti nominali. "
            "Ancorata vicino al 2% (verde) = credibilità della Fed intatta, percorso dei tassi prevedibile. "
            "Sopra il 3% = i mercati obbligazionari dubitano della Fed, "
            "aumentando il rischio di ulteriori rialzi o tassi 'più alti più a lungo'. "
            "Segnale a breve termine; più volatile del breakeven a 10 anni."
        ),
        unit="pct",
    ),
    _Cfg(
        name="Breakeven Inflazione 10A",
        value_fn=lambda r: r.breakeven_10y,
        color_fn=lambda r: (
            "green" if r.breakeven_10y is not None and 1.5 <= r.breakeven_10y <= 2.5 else
            "red"   if r.breakeven_10y is not None and r.breakeven_10y > 3.0 else
            "grey"
        ),
        help=(
            "L'aspettativa di inflazione a 10 anni dagli spread TIPS — il segnale di inflazione a lungo termine più monitorato. "
            "Vicino al 2% obiettivo (verde) = il mercato crede che l'inflazione si normalizzi nel decennio. "
            "In aumento oltre il 2,5% spinge la Fed a mantenere tassi più alti a lungo, "
            "il che è ribassista per le growth stock e le obbligazioni a lunga duration. "
            "Driver primario del premio per il rischio azionario."
        ),
        unit="pct",
    ),
    _Cfg(
        name="Inflazione Core PCE (YoY)",
        value_fn=lambda r: r.core_pce_yoy,
        color_fn=lambda r: (
            "green" if r.core_pce_yoy is not None and r.core_pce_yoy <= 2.5 else
            "red"   if r.core_pce_yoy is not None and r.core_pce_yoy > 3.5 else
            "grey"
        ),
        help=(
            "L'indicatore di inflazione preferito dalla Federal Reserve "
            "(Personal Consumption Expenditures, esclusi alimentari ed energia). "
            "L'obiettivo del 2% della Fed è definito su questa misura. "
            "Sotto il 2,5% = in linea con l'obiettivo (verde). "
            "Sopra il 3,5% = ben al di sopra, mantiene la Fed in postura restrittiva (rosso). "
            "Un PCE in calo è la condizione chiave per i tagli dei tassi — "
            "il dato mensile più capace di muovere i mercati."
        ),
        unit="pct",
    ),
    _Cfg(
        name="PMI Manifatturiero ISM",
        value_fn=lambda r: r.ism_manufacturing_pmi,
        color_fn=lambda r: (
            "green" if r.ism_manufacturing_pmi is not None and r.ism_manufacturing_pmi > 50 else
            "red"   if r.ism_manufacturing_pmi is not None and r.ism_manufacturing_pmi < 48 else
            "grey"
        ),
        help=(
            "Sondaggio mensile dei direttori acquisti manifatturieri. "
            "Sopra 50 = espansione (fabbriche in crescita). Sotto 50 = contrazione. "
            "Indicatore anticipatore dell'attività economica di 1–2 trimestri. "
            "Letture prolungate sotto 48 coincidono storicamente con recessioni. "
            "I sotto-indici di nuovi ordini e occupazione sono i più monitorati per il momentum futuro."
        ),
    ),
    _Cfg(
        name="Rapporto CAPE Shiller",
        value_fn=lambda r: r.shiller_cape,
        color_fn=lambda r: (
            "green" if r.shiller_cape is not None and r.shiller_cape < 25 else
            "red"   if r.shiller_cape is not None and r.shiller_cape > 35 else
            "grey"
        ),
        help=(
            "Prezzo S&P 500 diviso per la media decennale degli utili corretti per l'inflazione. "
            "Media storica ~17; picco della bolla internet ~44. "
            "Sopra 35 = storicamente costoso, associato a rendimenti medi decennali inferiori alla media. "
            "Sotto 25 = storicamente ragionevole. "
            "Più adatto per previsioni di rendimento a lungo termine che per il timing di mercato a breve."
        ),
    ),
    _Cfg(
        name="Indicatore di Buffett",
        value_fn=lambda r: r.buffett_indicator_pct,
        color_fn=lambda r: (
            "green" if r.buffett_indicator_pct is not None and r.buffett_indicator_pct < 100 else
            "red"   if r.buffett_indicator_pct is not None and r.buffett_indicator_pct > 150 else
            "grey"
        ),
        help=(
            "Capitalizzazione totale del mercato azionario USA divisa per il PIL — "
            "il parametro di valutazione macro preferito di Warren Buffett. "
            "Sotto 80% = sottovalutato. 80–115% = valore equo. Sopra 150% = sopravvalutato ('giocare col fuoco'). "
            "La globalizzazione delle aziende USA e i tassi bassi dal 2008 hanno strutturalmente elevato questo rapporto; "
            "va usato come confronto storico relativo piuttosto che come segnale assoluto."
        ),
        unit="pct",
    ),
    _Cfg(
        name="Premio per il Rischio Azionario",
        value_fn=lambda r: r.equity_risk_premium,
        color_fn=lambda r: (
            "green" if r.equity_risk_premium is not None and r.equity_risk_premium > 3.0 else
            "red"   if r.equity_risk_premium is not None and r.equity_risk_premium < 1.0 else
            "grey"
        ),
        help=(
            "Rendimento prospettico degli utili (1/P/E forward) meno il rendimento reale decennale — "
            "il rendimento extra che le azioni offrono rispetto ai bond. "
            "Sopra il 3% = azioni attrattivamente valutate rispetto ai bond risk-free (verde). "
            "Sotto il 1% = le azioni offrono un premio minimo rispetto ai bond, "
            "rendendo meno convincente l'allocazione azionaria (rosso). "
            "Un ERP negativo significa che i bond rendono più delle azioni su base corretta per il rischio."
        ),
        unit="pct+",
    ),
    _Cfg(
        name="Indicatore Anticipatore OCSE (USA)",
        value_fn=lambda r: r.lei_conference_board,
        color_fn=lambda r: (
            "green" if r.lei_conference_board is not None and r.lei_conference_board > 100.0 and (r.lei_mom_pct or 0) > 0 else
            "red"   if r.lei_conference_board is not None and r.lei_conference_board < 99.0  and (r.lei_mom_pct or 0) < 0 else
            "grey"
        ),
        help=(
            "Indicatore Anticipatore Composito OCSE per gli USA — un indice normalizzato a 100 "
            "di segnali prospettici (permessi, ordini, fiducia, credito). "
            "Sopra 100 e in crescita = trend di espansione. "
            "Sotto 100 e in calo = possibile rallentamento in arrivo, anticipa il PIL di 6–9 mesi. "
            "Cali mensili consecutivi sotto 99 sono un forte segnale anticipatore di recessione."
        ),
        label_fn=lambda r: f"{r.lei_mom_pct:+.2f}% MoM" if r.lei_mom_pct is not None else None,
    ),
    _Cfg(
        name="Rapporto Rame/Oro",
        value_fn=lambda r: r.copper_gold_ratio,
        color_fn=lambda r: (
            "green" if r.copper_gold_ratio is not None and r.copper_gold_ratio > 0.00040 else
            "red"   if r.copper_gold_ratio is not None and r.copper_gold_ratio < 0.00020 else
            "grey"
        ),
        help=(
            "Rame (proxy della domanda industriale) diviso per oro (proxy del bene rifugio). "
            "Rapporto in crescita = ottimismo sulla crescita, industria che compra rame "
            "per produzione e costruzioni (verde). "
            "Rapporto in calo = risk-off, fuga verso la sicurezza (rosso). "
            "Il rapporto anticipa anche i rendimenti Treasury a 10 anni (segnale Gundlach) — "
            "utile per anticipare la direzione dei tassi."
        ),
    ),
    _Cfg(
        name="P/E Forward S&P 500",
        value_fn=lambda r: r.sp500_fwd_pe,
        color_fn=lambda r: (
            "green" if r.sp500_fwd_pe is not None and r.sp500_fwd_pe < 18 else
            "red"   if r.sp500_fwd_pe is not None and r.sp500_fwd_pe > 22 else
            "grey"
        ),
        help=(
            "Prezzo S&P 500 diviso per le stime di consensus sugli EPS a 12 mesi. Media storica ~16x. "
            "Sotto 18x = ragionevolmente valutato rispetto alle norme moderne. "
            "Sopra 22x = aspettative elevate, vulnerabile a delusioni sugli utili "
            "o a tassi in rialzo (che riducono il valore attuale degli utili futuri). "
            "Il multiplo di valutazione azionaria più monitorato al mondo."
        ),
        unit="x",
    ),
    _Cfg(
        name="Crescita EPS S&P 500 (YoY)",
        value_fn=lambda r: r.sp500_eps_growth_q,
        color_fn=lambda r: (
            "green" if r.sp500_eps_growth_q is not None and r.sp500_eps_growth_q > 10 else
            "red"   if r.sp500_eps_growth_q is not None and r.sp500_eps_growth_q < 0  else
            "grey"
        ),
        help=(
            "Crescita degli utili per azione dell'S&P 500 anno su anno nel trimestre più recente "
            "(combina report effettivi e stime rimanenti). "
            "Sopra il 10% = ciclo degli utili forte, supporta le valutazioni correnti (verde). "
            "Negativa = contrazione degli utili, spesso innesca compressione dei multipli "
            "e debolezza di mercato (rosso). 0–10% = crescita moderata e sostenibile."
        ),
        unit="pct+",
        label_fn=lambda r: r.sp500_eps_growth_quarter,
    ),
    _Cfg(
        name="Crescita EPS EuroStoxx 50",
        value_fn=lambda r: r.eurostoxx50_fwd_eps_growth,
        color_fn=lambda r: (
            "green" if r.eurostoxx50_fwd_eps_growth is not None and r.eurostoxx50_fwd_eps_growth > 8 else
            "red"   if r.eurostoxx50_fwd_eps_growth is not None and r.eurostoxx50_fwd_eps_growth < 0 else
            "grey"
        ),
        help=(
            "Stima di crescita degli EPS forward per l'EuroStoxx 50 (le 50 maggiori aziende europee). "
            "Le azioni europee trattano a sconto rispetto alle USA (P/E inferiore), "
            "quindi la crescita degli utili è il principale driver di alpha. "
            "Crescita forte (>8%) supporta l'allocazione azionaria europea. "
            "Stime negative riflettono venti contrari macro: prezzi dell'energia, "
            "rischio geopolitico o rafforzamento dell'euro."
        ),
        unit="pct+",
    ),
    _Cfg(
        name="Settori Leader (Crescita EPS)",
        value_fn=lambda r: None,
        color_fn=lambda r: "grey",
        help=(
            "Settori dell'S&P 500 con la più alta crescita EPS anno su anno nel trimestre di reporting corrente. "
            "I settori leader attraggono afflussi di capitale e tendono a sovraperformare nel breve termine. "
            "Settori difensivi in testa (Sanità, Utility, Beni di Prima Necessità) = segnale di fine ciclo. "
            "Tecnologia e Finanza in testa insieme = risk-on, regime di crescita da inizio a metà ciclo."
        ),
        label_fn=lambda r: r.leading_sectors,
    ),
]


def build_indicators(result: MacroIndicatorsResult) -> list[IndicatorReport]:
    reports = []
    for cfg in _CONFIGS:
        try:
            value = cfg.value_fn(result)
            color = cfg.color_fn(result)
            label = cfg.label_fn(result)
        except Exception:
            value = None
            color = "grey"
            label = None
        reports.append(IndicatorReport(
            name=cfg.name, value=value, unit=cfg.unit,
            label=label, color=color, help=cfg.help,
        ))
    return reports
