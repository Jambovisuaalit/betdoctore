# BetDoctore: nykytilan auditointi 5.11.2026

Auditoitu paikallinen revisio: `c7e5c92`, haara
`feat/v1-regular-evaluation-staging`. Auditointi kattaa paikallisen koodin,
asennuksen, migraatiot, testit, säilytetyn tulosnäytön ja arvioinnin uusinta-ajon.
Sovelluskoodia, alkuperäistä dataa tai arviointia ei muutettu.

## Johtopäätös

Tutkimusalustan tekninen perusta toimii ja jäädytetty arviointi on toistettavissa.
Täyttä runkosarjakattavuutta, uuden riippumattoman arvioinnin hyväksyntää,
advanced-aineiston kelpoisuutta tai vedonlyöntietua ei ole osoitettu.
Tuotantohyväksyntä pysyy estettynä.

## Toistetut puutteet

### A1 — P1 ennen todellista kerroindataa: puuttuva jatkoaikasääntö hyväksytään

`src/betdoctore/domain.py:53`: `includes_overtime` saa oletusarvon `True`.
Kun kenttä poistettiin synteettisestä kelvollisesta kerroinrivistä,
`Odds.model_validate` hyväksyi rivin ja palautti `True`. CSV/Parquet-tuonti käyttää
samaa sopimusta. Siten puuttuva markkinasääntö voi läpäistä päätöslogiikan
jatkoaikatarkistuksen. Tämä ei vaikuta nykyiseen score-only-arviointiin, jossa
kerroindataa ei käytetty.

Korjaus: vaadi eksplisiittinen sääntö ja sen lähdenäyttö ennen markkinan hyväksymistä;
puuttuva tai tuntematon sääntö karanteeniin/PASS. Testaa myös puuttuva CSV-kenttä.

### A2 — P2: readiness hyväksyy keskeneräisen skeeman

`src/betdoctore/api.py:21–25`: `/ready` tarkistaa vain `feature_snapshots.digest`-
kyselyn. Erillisessä tilapäisessä tietokannassa luotiin pelkkä
`feature_snapshots (digest TEXT)` -taulu; vastaus oli HTTP 200 ja
`database=ready`, vaikka muut taulut ja Alembic-versio puuttuivat.

Korjaus: tarkista odotettu migraatioversio ja palvelun tarvitsemat taulut.
Pidä tietokantavalmius erillään mallin/data-aineiston hyväksynnästä.

### A3 — P2: kiinteän mallin ajo keskeytyy varhaiseen ennustekohteeseen

`src/betdoctore/backtest.py:52`: mallin koulutusrajaa edeltävä ennustekohde
aiheuttaa `ValueError: Model trained after prediction cutoff`, joka keskeyttää
koko ajon. Tämä toistettiin synteettisellä `dataset()`-aineistolla ja mallilla,
jonka `trained_until` asetettiin viimeisen ottelun aloitusta edeltävään päivään.
Myöhempiä kelvollisia kohteita ei käsitellä. Tulevaan koulutustietoon perustuvaa
ennustetta ei päästetty läpi, joten suoja vuotoa vastaan toimii.

Korjaus: kirjaa varhaiset kohteet yksiselitteisesti ohitetuiksi ja jatka kelvollisiin,
tai vaadi erillinen arviointialku ja validoi se ennen ajoa. Älä muuta koulutusrajaa.

### A4 — P2, paikallinen ympäristö: editable-asennus ei löydä pakettia

`.venv/bin/python -c 'import betdoctore'` epäonnistui `ModuleNotFoundError`-
virheeseen, vaikka `pip show betdoctore` ilmoitti editable-asennuksen tähän projektiin.
Testit ja lähdekoodiajot tässä auditoinnissa käyttivät `PYTHONPATH=src`.
`pip check` ei havainnut ongelmaa. Erillinen normaali paketin asennus onnistui,
joten tämä havainto koskee nykyistä paikallista ympäristöä, ei todistettua
wheel-paketin virhettä.

Korjaus: korjaa tai luo paikallinen virtuaaliympäristö uudelleen ja varmista
CLI/import ilman PYTHONPATH-kiertotietä. Auditointi ei muuttanut ympäristöä.

### A5 — P2: tiladokumentaatio on ristiriitainen

`docs/operations.md:115–123` kertoo, ettei tulos-/otteluohjelmanäyttöä ole
varmennettu ja ettei NBA.com-aineistoa ole haettu. Nykyinen projekti sisältää
varmennettuja arkistokaappauksia ja neljä Firecrawlin kautta säilytettyä virallista
NBA-julkaisua. README kuvaa osittaisen datavalmiuden ja 298 pelin tutkimusajon,
kun CLI `status` palauttaa edelleen staattisen `DATA_READY=BLOCKED` ja
`BACKTEST_READY=synthetic only` ilman score-only-erottelua.

Korjaus: yhtenäistä tilat siten, että tekninen tulosperusta, score-only-arviointi,
advanced-aineisto, vedonlyöntibacktest ja tuotanto erotetaan selvästi.
Älä muuta osittaista onnistumista yleiseksi tuotantovalmiudeksi.

## Suoritetut tarkistukset

| Tarkistus | Tulos |
| --- | --- |
| Ruff koko projektista | PASS |
| Pytest, lähdekoodi PYTHONPATH=src | 223 PASS, yksi Starlette/httpx-deprekaatiovaroitus |
| Riippuvuudet, pip check | PASS; ei todista paketin importin toimivuutta |
| Wheel, normaali eristetty build | PASS |
| Normaali asennus erilliseen tilapäishakemistoon | PASS |
| Asennetun paketin API-import ja protokollaresurssi | PASS |
| SQLite: upgrade head, alembic check, downgrade base, upgrade head | PASS; erillinen tilapäistietokanta |
| Synteettinen CLI fixture-backtest, HTML/JSON | PASS; ei todellista suorituskykynäyttöä |
| API:n smoke-/integraatiotestit | PASS; keskeneräisen skeeman readiness-puute erikseen yllä |
| Neljän korjauspäätöksen lähdetiedostojen uudelleenvarmennus | PASS |
| Säilytettyjen temporal- ja päätösartefaktien sisältöosoitteiset JSON-hashit | PASS |
| Alkuperäisen jäädytetyn arvioinnin uusinta-ajo | PASS; alkuperäinen koodirevisio, sama raporttihash |
| PostgreSQL ja Docker paikallisesti | Ei ajettu; binäärit eivät löytyneet |
| Nykyisen HEADin GitHub CI / etärepon tila | Ei tarkistettu verkosta tässä auditoinnissa |

Build ilman build-eristystä epäonnistui paikallisen setuptools-backendin puuttumiseen;
normaali eristetty build ja asennus onnistuivat. Tätä ei tulkita projektin
paketointivirheeksi.

## Data ja toistettavuus

Paikallisen tietokannan vain luku -inventointi:

- 13 505 `basic_results`-havaintoa ja 8 lähdesnapshotia. Havaintomäärä ei ole
  uniikkien, hyväksyttyjen otteluiden tai täyden kausikattavuuden mittari.
- `source_records`, `feature_snapshots`, `model_artifacts`,
  `advanced_stage_batches` ja `advanced_stage_rows`: kukin 0 riviä.
- Varsinaisessa ennuste-/kerroinputkessa ei siis ole paikallista todellista
  kerroin- tai advanced-aineistoa. Yksityiset tutkimusartefaktit ovat erillisissä tiedostoissa.

Jäädytetyn arvioinnin lähteet ladattiin uudelleen ja alkuperäiset tavut tarkistettiin
uusinta-ajossa revisiolla `034abdbe4e273657cd9139928de918304246ad09` erillisestä
väliaikaisesta checkoutista. Ajo tuotti saman raportin:
`fbe2e16b332e0e616ec5b0dbbd0a3a365d5322ffb23b9df32382cef5dec5a6da.evaluation.json`.
Tämä on toistettavuusnäyttöä jo paljastetulle aineistolle, ei uusi riippumaton testi.

402 jäädytetystä ennusteesta arvioitiin 298; 102 jäi pois historiallisen
piirredatan ristiriitojen ja kaksi kohdeottelun tarkistusten vuoksi.
Ensisijainen seitsemän päivän epävarmuusväli ei ole saatavilla riittämättömän
ajallisen tuen vuoksi. Kolmen päivän herkkyysväli ei korvaa ensisijaista porttia.
300 ottelun suunnittelutavoite ei täyttynyt.

Neljän tulosristiriidan päätösten lähde-esitysten hashit täsmäävät ja päätös
voidaan muodostaa uudelleen. Säilytetty Firecrawl-esitys ei todista alkuperäisiä
HTTP-siirtotavuja eikä historiallista T−60-saatavuutta. Päätöksiä ei ole liitetty
uuteen adjudikointia tukevaan manifestiverifioijaan; alkuperäisiä havaintoja,
piirteitä tai jäädytettyä arviointia ei ole korvattu.

## Valmiusportit

| Portti | Auditoinnin arvio |
| --- | --- |
| CODE_READY | Tutkimusbaseline toimii; yllä olevat puutteet avoinna, nykyisen HEADin CI tarkistamatta |
| DATA_READY | OSITTAIN: tekninen tulosperusta; täydellinen kattavuus ja historiallinen saatavuus avoinna |
| FORECAST_EVALUATION_READY | Toistettava 298 pelin tutkimusajo; uuden riippumattoman arvioinnin hyväksyntä estetty |
| BACKTEST_READY | Synteettinen vedonlyöntiputki toimii; aito kerroinbacktest BLOCKED |
| PRODUCTION_READY | BLOCKED |

## Suositeltu eteneminen

1. Korjaa eksplisiittinen markkinasääntö, readiness ja kiinteän mallin rajakäsittely;
   varmista paikallinen asennus ja nykyisen muutoksen CI.
2. Liitä tulospäätökset append-only-adjudikointikerrokseen, joka säilyttää
   eriävät havainnot; pidä historialliset piirrearvot muuttumattomina.
3. Hanki pidempi kattavuus ja ennen T−60:ta todennetut lähdekaappaukset.
   Lukitse uusi, aiemmasta paljastetusta otoksesta erillinen arviointisuunnitelma.
4. Hyväksy advanced-rivit erillisten lähde-, määritelmä- ja saatavuusporttien kautta.
5. Tee mallin ja vedonlyöntiedun validoinnit erikseen ennen tuotantohyväksyntää.

Auditoinnin alussa työpuu oli puhdas. Paikallinen haara oli yhden commitin
edellä paikallista origin-seurantaviitettä; etäpalvelimen ajantasaista tilaa ei
varmennettu. Tämä raportti ei sisällä yksityisiä raakakaappauksia tai pelikohtaisia ennusteita.


## Korjausseuranta 5.11.2026

A1: jatkoaikasääntö on nyt pakollinen. Puuttuva, null tai tuntematon arvo hylätään;
regressiotestit kattavat validoinnin sekä CSV/Parquet-tuonnin.

A2: `/ready` vaatii tuetun Alembic-revision ja kaikkien sovellustaulujen sarakkeiden
kyseltävyyden. Testit kattavat puuttuvan skeeman, osittaisen migraation, väärän
revision, täydellisen migraation ja jälkikäteen puuttuvan taulun.

A3: kiinteän mallin koulutusrajaa edeltävät kohteet kirjataan ohitetuiksi ja ajo
jatkuu. Testi varmistaa myös täsmälleen katkaisuhetkellä kelvollisen mallin käytön.

A4: editable-paketin uudelleenasennus ei yksin auttanut. Pythonin verbose-loki
osoitti `.pth`-tiedoston hidden-lipun vuoksi ohitetuksi. Lipun poisto kyseisestä
tiedostosta korjasi importin vain saman komentoajon ajaksi: lippu palasi myöhemmin.
Paikalliseen site-packages-hakemistoon lisättiin siksi suora symbolinen linkki
projektin src/betdoctore-pakettiin. Erillisissä ajoissa import ja CLI toimivat
ilman PYTHONPATH-asetusta. Asennuksen ulkopuolinen smoke-testi estää tämän
paikallisen ongelman jäämisen testien PYTHONPATH-asetuksen peittoon.

A5: README, käyttöohje ja CLI erottavat osittaisen datavalmiuden, score-only-
tutkimusajon ja estyneen aidon vedonlyöntibacktestin. Tuotantohyväksyntä pysyy estettynä.

Alkuperäiset auditointihavainnot yllä säilyvät aikaleimattuna lähtötilana.
Korjaukset eivät muuta yksityisiä havaintoja tai jäädytettyä arviointia. Vanha
arviointi toistetaan edelleen omalla mitatulla koodirevisiollaan.
