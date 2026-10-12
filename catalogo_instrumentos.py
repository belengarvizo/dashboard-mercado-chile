"""
Catalogo semilla de instrumentos de XTB para el modulo de trading.

QUE ES Y QUE NO. Es la semilla VERSIONADA del catalogo: nombres, categorias,
elegibilidad para el torneo y tickers de Yahoo validados. Se carga una sola vez
en la tabla `trading_instrumentos` de PostgreSQL y, a partir de ahi, la fuente
de verdad es la tabla: el usuario edita desde la UI los campos que dependen de
su cuenta (margen, valor por punto), y el sistema de archivos de Railway es
efimero, asi que un archivo editado desde la UI se perderia en el siguiente
despliegue.

TICKERS. Todos los que aparecen aca se probaron con una descarga real de 1 anio
contra Yahoo Finance el 11-10-2026: devuelven 200+ observaciones diarias. Los
que fallaron quedan en None con la nota "sin datos Yahoo". Los marcados
"PROPUESTO por validacion" no venian en el catalogo original: los encontro esa
prueba, y hay que verificar que correspondan al instrumento de XTB antes de
confiar en ellos.

MARGENES Y VALOR POR PUNTO. Van en None salvo los dos que el usuario leyo de
sus tickets. NO se calculan con una formula de apalancamiento supuesta: quedan
pendientes hasta que se ingresen desde el ticket real.

TAMANIO DEL PIP. No es derivable del nombre, y por eso es un dato explicito.
Medido el 11-10-2026: USDCLP cotiza a 975, USDCOP a 3.187 y USDHUF a 325, asi
que para esos un pip de 0,0001 seria una fraccion absurda del precio. Solo se
precarga donde es seguro: 0,01 en los pares con JPY, y 0,0001 en los que
cotizan en una divisa que se mueve cerca de 1 (USD, CAD, CHF, GBP, AUD, NZD,
EUR). El resto queda en None, y el calculador de lotes debe NEGARSE a calcular
en vez de asumir: equivocarse por un factor de 100 en el pip es equivocarse por
100 en el tamanio de la posicion.
"""
from decimal import Decimal

CATEGORIAS = ("divisas", "indices", "indices_volatilidad", "materias_primas",
              "zona_gris", "cripto")

# Pares con panel de datos en la Fase 1 (los unicos que se agregan al cron).
PARES_FASE_1 = (
    "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDJPY", "USDCAD", "USDCHF", "USDCLP",
    "USDBRL", "USDMXN", "EURJPY", "GBPJPY", "EURGBP", "USDIDX",
)

# (nombre_xtb, categoria, elegible_torneo, ticker_yahoo, pip_tamanio, margen_001_clp, notas)
CATALOGO_SEMILLA = [
    ("EURUSD", "divisas", True, "EURUSD=X", Decimal('0.0001'), Decimal('5489'), "margen del ticket de XTB con EURUSD a 1,11995. panel de datos Fase 1."),
    ("GBPUSD", "divisas", True, "GBPUSD=X", Decimal('0.0001'), None, "panel de datos Fase 1."),
    ("AUDUSD", "divisas", True, "AUDUSD=X", Decimal('0.0001'), None, "panel de datos Fase 1."),
    ("NZDUSD", "divisas", True, "NZDUSD=X", Decimal('0.0001'), None, "panel de datos Fase 1."),
    ("USDJPY", "divisas", True, "USDJPY=X", Decimal('0.01'), None, "panel de datos Fase 1."),
    ("USDCAD", "divisas", True, "USDCAD=X", Decimal('0.0001'), None, "panel de datos Fase 1."),
    ("USDCHF", "divisas", True, "USDCHF=X", Decimal('0.0001'), None, "panel de datos Fase 1."),
    ("USDCLP", "divisas", True, "USDCLP=X", None, None, "panel de datos Fase 1. pip PENDIENTE: CLP cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDBRL", "divisas", True, "USDBRL=X", None, None, "panel de datos Fase 1. pip PENDIENTE: BRL cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDMXN", "divisas", True, "USDMXN=X", None, None, "panel de datos Fase 1. pip PENDIENTE: MXN cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDCOP", "divisas", True, "USDCOP=X", None, None, "pip PENDIENTE: COP cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDCNH", "divisas", True, None, None, None, "sin datos Yahoo (1 sola observacion en 1 anio). pip PENDIENTE: CNH cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDINR", "divisas", True, "USDINR=X", None, None, "pip PENDIENTE: INR cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDTRY", "divisas", True, "USDTRY=X", None, None, "pip PENDIENTE: TRY cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDZAR", "divisas", True, "USDZAR=X", None, None, "pip PENDIENTE: ZAR cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDSGD", "divisas", True, "USDSGD=X", None, None, "pip PENDIENTE: SGD cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDTHB", "divisas", True, "USDTHB=X", None, None, "pip PENDIENTE: THB cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDILS", "divisas", True, "USDILS=X", None, None, "pip PENDIENTE: ILS cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDNOK", "divisas", True, "USDNOK=X", None, None, "pip PENDIENTE: NOK cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDSEK", "divisas", True, "USDSEK=X", None, None, "pip PENDIENTE: SEK cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDPLN", "divisas", True, "USDPLN=X", None, None, "pip PENDIENTE: PLN cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDCZK", "divisas", True, "USDCZK=X", None, None, "pip PENDIENTE: CZK cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDHUF", "divisas", True, "USDHUF=X", None, None, "pip PENDIENTE: HUF cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("USDRON", "divisas", True, "USDRON=X", None, None, "pip PENDIENTE: RON cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("AUDCAD", "divisas", True, "AUDCAD=X", Decimal('0.0001'), None, ""),
    ("AUDCHF", "divisas", True, "AUDCHF=X", Decimal('0.0001'), None, ""),
    ("AUDJPY", "divisas", True, "AUDJPY=X", Decimal('0.01'), None, ""),
    ("AUDNZD", "divisas", True, "AUDNZD=X", Decimal('0.0001'), None, ""),
    ("CADCHF", "divisas", True, "CADCHF=X", Decimal('0.0001'), None, ""),
    ("CADJPY", "divisas", True, "CADJPY=X", Decimal('0.01'), None, ""),
    ("CADMXN", "divisas", True, "CADMXN=X", None, None, "pip PENDIENTE: MXN cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("CHFHUF", "divisas", True, "CHFHUF=X", None, None, "pip PENDIENTE: HUF cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("CHFJPY", "divisas", True, "CHFJPY=X", Decimal('0.01'), None, ""),
    ("CHFNOK", "divisas", True, "CHFNOK=X", None, None, "pip PENDIENTE: NOK cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("CHFPLN", "divisas", True, "CHFPLN=X", None, None, "pip PENDIENTE: PLN cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("CHFSEK", "divisas", True, "CHFSEK=X", None, None, "pip PENDIENTE: SEK cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("EURAUD", "divisas", True, "EURAUD=X", Decimal('0.0001'), None, ""),
    ("EURCAD", "divisas", True, "EURCAD=X", Decimal('0.0001'), None, ""),
    ("EURCHF", "divisas", True, "EURCHF=X", Decimal('0.0001'), None, ""),
    ("EURCNH", "divisas", True, None, None, None, "sin datos Yahoo (1 sola observacion en 1 anio). pip PENDIENTE: CNH cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("EURCZK", "divisas", True, "EURCZK=X", None, None, "pip PENDIENTE: CZK cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("EURGBP", "divisas", True, "EURGBP=X", Decimal('0.0001'), None, "panel de datos Fase 1."),
    ("EURHUF", "divisas", True, "EURHUF=X", None, None, "pip PENDIENTE: HUF cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("EURJPY", "divisas", True, "EURJPY=X", Decimal('0.01'), None, "panel de datos Fase 1."),
    ("EURMXN", "divisas", True, "EURMXN=X", None, None, "pip PENDIENTE: MXN cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("EURNOK", "divisas", True, "EURNOK=X", None, None, "pip PENDIENTE: NOK cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("EURNZD", "divisas", True, "EURNZD=X", Decimal('0.0001'), None, ""),
    ("EURPLN", "divisas", True, "EURPLN=X", None, None, "pip PENDIENTE: PLN cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("EURRON", "divisas", True, "EURRON=X", None, None, "pip PENDIENTE: RON cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("EURSEK", "divisas", True, "EURSEK=X", None, None, "pip PENDIENTE: SEK cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("EURSGD", "divisas", True, "EURSGD=X", None, None, "pip PENDIENTE: SGD cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("EURTRY", "divisas", True, "EURTRY=X", None, None, "pip PENDIENTE: TRY cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("EURZAR", "divisas", True, "EURZAR=X", None, None, "pip PENDIENTE: ZAR cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("GBPAUD", "divisas", True, "GBPAUD=X", Decimal('0.0001'), None, ""),
    ("GBPCAD", "divisas", True, "GBPCAD=X", Decimal('0.0001'), None, ""),
    ("GBPCHF", "divisas", True, "GBPCHF=X", Decimal('0.0001'), None, ""),
    ("GBPJPY", "divisas", True, "GBPJPY=X", Decimal('0.01'), None, "panel de datos Fase 1."),
    ("GBPMXN", "divisas", True, "GBPMXN=X", None, None, "pip PENDIENTE: MXN cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("GBPNOK", "divisas", True, "GBPNOK=X", None, None, "pip PENDIENTE: NOK cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("GBPNZD", "divisas", True, "GBPNZD=X", Decimal('0.0001'), None, ""),
    ("GBPPLN", "divisas", True, "GBPPLN=X", None, None, "pip PENDIENTE: PLN cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("GBPSEK", "divisas", True, "GBPSEK=X", None, None, "pip PENDIENTE: SEK cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("GBPZAR", "divisas", True, "GBPZAR=X", None, None, "pip PENDIENTE: ZAR cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("NOKSEK", "divisas", True, "NOKSEK=X", None, None, "pip PENDIENTE: SEK cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("NZDCAD", "divisas", True, "NZDCAD=X", Decimal('0.0001'), None, ""),
    ("NZDCHF", "divisas", True, "NZDCHF=X", Decimal('0.0001'), None, ""),
    ("NZDJPY", "divisas", True, "NZDJPY=X", Decimal('0.01'), None, ""),
    ("NZDSGD", "divisas", True, "NZDSGD=X", None, None, "pip PENDIENTE: SGD cotiza lejos de 1, confirmar con el ticket de XTB"),
    ("ZARJPY", "divisas", True, "ZARJPY=X", Decimal('0.01'), None, ""),
    ("USDIDX", "divisas", True, "DX-Y.NYB", None, None, "indice dolar, no es un par: no tiene pip. panel de datos Fase 1"),
    ("US500", "indices", True, "^GSPC", None, None, "el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("US100", "indices", True, "^NDX", None, Decimal('30581'), "margen del ticket de XTB con US100 a 31.196,5. el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("US30", "indices", True, "^DJI", None, None, "el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("US2000", "indices", True, "^RUT", None, None, "el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("DE40", "indices", True, "^GDAXI", None, None, "el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("EU50", "indices", True, "^STOXX50E", None, None, "el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("FRA40", "indices", True, "^FCHI", None, None, "el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("ITA40", "indices", True, "FTSEMIB.MI", None, None, "ticker FTSEMIB.MI PROPUESTO por validacion, verificar que corresponda. el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("SPA35", "indices", True, "^IBEX", None, None, "el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("UK100", "indices", True, "^FTSE", None, None, "el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("NED25", "indices", True, "^AEX", None, None, "el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("SUI20", "indices", True, "^SSMI", None, None, "el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("CH50cash", "indices", True, "^HSCE", None, None, "ticker ^HSCE PROPUESTO por validacion, verificar que corresponda. el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("BRAComp", "indices", True, "^BVSP", None, None, "el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("MEXComp", "indices", True, "^MXX", None, None, "el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("VIET30", "indices", True, None, None, None, "sin datos Yahoo. el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("W20", "indices", True, None, None, None, "sin datos Yahoo. el CFD de XTB puede cotizar sobre un futuro, su precio no coincide exacto con el indice spot de Yahoo (ej. US500 ~7.870 vs S&P500 spot 7.811,54)"),
    ("VIX", "indices_volatilidad", False, "^VIX", None, None, "aparece bajo Indices en XTB pero mide volatilidad: confirmar con XTB si cuenta como indice del torneo"),
    ("VSTOXX", "indices_volatilidad", False, None, None, None, "aparece bajo Indices en XTB pero mide volatilidad: confirmar con XTB si cuenta como indice del torneo. sin datos Yahoo"),
    ("GOLD", "materias_primas", True, "GC=F", None, None, ""),
    ("SILVER", "materias_primas", True, "SI=F", None, None, ""),
    ("PLATINUM", "materias_primas", True, "PL=F", None, None, ""),
    ("PALLADIUM", "materias_primas", True, "PA=F", None, None, ""),
    ("COPPER", "materias_primas", True, "HG=F", None, None, "Yahoo viene en USD por libra; XTB puede usar otra unidad: verificar antes de comparar precios"),
    ("ALUMINIUM", "materias_primas", True, "ALI=F", None, None, "ticker ALI=F PROPUESTO por validacion, verificar."),
    ("NICKEL", "materias_primas", True, None, None, None, "sin datos Yahoo."),
    ("ZINC", "materias_primas", True, "ZNC=F", None, None, "ticker ZNC=F PROPUESTO por validacion, verificar."),
    ("OIL", "materias_primas", True, "BZ=F", None, None, "en XTB OIL es BRENT (~104), no confundir con OIL.WTI"),
    ("OIL.WTI", "materias_primas", True, "CL=F", None, None, "en XTB OIL.WTI es WTI (~90). El 'WTI Oil' del Brief es este"),
    ("NATGAS", "materias_primas", True, "NG=F", None, None, ""),
    ("GASOLINE", "materias_primas", True, "RB=F", None, None, ""),
    ("LSGASOIL", "materias_primas", True, None, None, None, "sin datos Yahoo."),
    ("WHEAT", "materias_primas", True, "ZW=F", None, None, ""),
    ("CORN", "materias_primas", True, "ZC=F", None, None, ""),
    ("SOYBEAN", "materias_primas", True, "ZS=F", None, None, ""),
    ("SOYOIL", "materias_primas", True, "ZL=F", None, None, ""),
    ("SUGAR", "materias_primas", True, "SB=F", None, None, ""),
    ("COFFEE", "materias_primas", True, "KC=F", None, None, ""),
    ("COCOA", "materias_primas", True, "CC=F", None, None, ""),
    ("COTTON", "materias_primas", True, "CT=F", None, None, ""),
    ("CATTLE", "materias_primas", True, "LE=F", None, None, ""),
    ("LEANHOGS", "materias_primas", True, "HE=F", None, None, ""),
    ("BUND10Y", "zona_gris", False, None, None, None, "aparece en Commodities de XTB pero no es materia prima clasica: confirmar con XTB antes de operar"),
    ("SCHATZ2Y", "zona_gris", False, None, None, None, "aparece en Commodities de XTB pero no es materia prima clasica: confirmar con XTB antes de operar"),
    ("TNOTE", "zona_gris", False, None, None, None, "aparece en Commodities de XTB pero no es materia prima clasica: confirmar con XTB antes de operar"),
    ("EMISS", "zona_gris", False, None, None, None, "aparece en Commodities de XTB pero no es materia prima clasica: confirmar con XTB antes de operar"),
    ("BITCOIN", "cripto", True, "BTC-USD", None, None, "spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("ETHEREUM", "cripto", True, "ETH-USD", None, None, "spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("SOLANA", "cripto", True, "SOL-USD", None, None, "spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("RIPPLE", "cripto", True, "XRP-USD", None, None, "spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("CARDANO", "cripto", True, "ADA-USD", None, None, "spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("DOGECOIN", "cripto", True, "DOGE-USD", None, None, "spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("LITECOIN", "cripto", True, "LTC-USD", None, None, "spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("BITCOINCASH", "cripto", True, "BCH-USD", None, None, "ticker BCH-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("BCHUSD", "cripto", True, None, None, None, "sin datos Yahoo. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("BINANCECOIN", "cripto", True, "BNB-USD", None, None, "ticker BNB-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("AVALANCHE", "cripto", True, "AVAX-USD", None, None, "spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("CHAINLINK", "cripto", True, "LINK-USD", None, None, "spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("POLKADOT", "cripto", True, "DOT-USD", None, None, "spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("POLYGON", "cripto", True, None, None, None, "sin datos Yahoo. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("TRON", "cripto", True, "TRX-USD", None, None, "ticker TRX-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("STELLAR", "cripto", True, "XLM-USD", None, None, "ticker XLM-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("TEZOS", "cripto", True, "XTZ-USD", None, None, "ticker XTZ-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("COSMOS", "cripto", True, "ATOM-USD", None, None, "ticker ATOM-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("NEAR", "cripto", True, "NEAR-USD", None, None, "ticker NEAR-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("SUI", "cripto", True, "SUI20947-USD", None, None, "ticker SUI20947-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("AAVE", "cripto", True, "AAVE-USD", None, None, "ticker AAVE-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("UNISWAP", "cripto", True, "UNI7083-USD", None, None, "ticker UNI7083-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("COMPOUND", "cripto", True, "COMP5692-USD", None, None, "ticker COMP5692-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("SUSHI", "cripto", True, "SUSHI-USD", None, None, "ticker SUSHI-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("CURVEDAO", "cripto", True, "CRV-USD", None, None, "ticker CRV-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("DYDX", "cripto", True, "DYDX-USD", None, None, "ticker DYDX-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("FILECOIN", "cripto", True, "FIL-USD", None, None, "ticker FIL-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("ALGORAND", "cripto", True, "ALGO-USD", None, None, "ticker ALGO-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("HEDERA", "cripto", True, "HBAR-USD", None, None, "ticker HBAR-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("INJECTIVE", "cripto", True, "INJ-USD", None, None, "ticker INJ-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("INTERCOMP", "cripto", True, None, None, None, "sin datos Yahoo. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("KUSAMA", "cripto", True, "KSM-USD", None, None, "ticker KSM-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("VECHAIN", "cripto", True, "VET-USD", None, None, "ticker VET-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("ZCASH", "cripto", True, "ZEC-USD", None, None, "ticker ZEC-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("RENDER", "cripto", True, "RENDER-USD", None, None, "ticker RENDER-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("JUPITER", "cripto", True, "JUP29210-USD", None, None, "ticker JUP29210-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("ONDO", "cripto", True, "ONDO-USD", None, None, "ticker ONDO-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("PYTH", "cripto", True, "PYTH-USD", None, None, "ticker PYTH-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("STARKNET", "cripto", True, "STRK22691-USD", None, None, "ticker STRK22691-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("GRAPH", "cripto", True, "GRT6719-USD", None, None, "ticker GRT6719-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("APECOIN", "cripto", True, "APE-USD", None, None, "ticker APE-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("GALA", "cripto", True, None, None, None, "sin datos Yahoo. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("SANDBOX", "cripto", True, "SAND-USD", None, None, "ticker SAND-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("DECENTRALAND", "cripto", True, "MANA-USD", None, None, "ticker MANA-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("CHILIZ", "cripto", True, "CHZ-USD", None, None, "ticker CHZ-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("SHIBA", "cripto", True, "SHIB-USD", None, None, "ticker SHIB-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("PEPE", "cripto", True, "PEPE24478-USD", None, None, "ticker PEPE24478-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("BONK", "cripto", True, "BONK-USD", None, None, "ticker BONK-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("DOGWIFHAT", "cripto", True, "WIF-USD", None, None, "ticker WIF-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("POPCAT", "cripto", True, None, None, None, "sin datos Yahoo. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("FARTCOIN", "cripto", True, "FARTCOIN-USD", None, None, "ticker FARTCOIN-USD PROPUESTO por validacion, verificar. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("TRUMP", "cripto", True, None, None, None, "sin datos Yahoo. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
    ("XMRBTC", "cripto", True, None, None, None, "sin datos Yahoo. spread alto en XTB (BTC ~0,22%, SOL ~0,30%, DOGE ~0,57%) y casi todas se mueven juntas"),
]


# Tickers de Yahoo de los instrumentos con panel de datos en la Fase 1. Se
# DERIVA del catálogo en vez de repetirse a mano: así no puede desincronizarse
# de PARES_FASE_1 ni de los tickers validados. Es la lista que el cron agrega
# a su descarga diaria (ver scripts/actualizar_acciones.py).
TICKERS_YAHOO_FASE_1 = [
    ticker
    for nombre, _cat, _eleg, ticker, _pip, _margen, _notas in CATALOGO_SEMILLA
    if nombre in PARES_FASE_1 and ticker
]
