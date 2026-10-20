# ⛽ mBenzin – ceny paliv v Home Assistantu

[English](README.md) · **Česky**

Integrace pro HACS, která v Home Assistantu ukazuje ceny paliv z [mBenzin.cz](https://www.mbenzin.cz) pro **vaše město**: **Natural 95, naftu, LPG, CNG** a další. Najdete v ní žebříček nejlevnějších čerpacích stanic, mapu a **vaši oblíbenou stanici** s historií cen a trendy. Všechno se nastavuje v rozhraní Home Assistantu, bez úprav souborů.

![Dashboard](docs/screenshot.webp)

> Neoficiální projekt, nijak nesouvisí s mBenzin.cz. Zdroj dat: [mBenzin.cz](https://www.mbenzin.cz).

## Co umí

- Vyberete si **město**, **jedno či více paliv** (třeba Natural 95 a LPG pro vůz na dvě paliva) a pro každé palivo **oblíbenou stanici**.
- Pro každé palivo **5 nejlevnějších stanic ve městě** (jen z vašeho města, nikoli z celého kraje), odkaz na Google Maps a **mapu s cenami**.
- U oblíbené stanice: aktuální cena, **trendy oproti 1, 2, 7, 14 a 30 dnům**, pořadí ve městě a dlouhodobá statistika (graf za 30 dní).
- Hotové **pohledy na dashboard** (jeden pro každé palivo) s volbou jazyka **čeština / angličtina**.
- Zastaralé ceny se skrývají: u benzínu a nafty cena starší než včerejšek, u CNG starší než 3 dny, u LPG a AdBlue starší než 7 dní.

## 1. Získání přístupového klíče (zdarma)

mBenzin před automatickým stahováním dat chrání ověřením prohlížeče, ale uživatelům Home Assistantu **zdarma vystavuje osobní přístupový klíč**.

1. Napište na **reklama@mbenzin.cz**.
2. Uveďte, že ceny budete používat v Home Assistantu, **pro které město nebo stanice** a **jak často** je budete načítat (stačí napsat např. „4× denně“).
3. Klíč vám přijde e-mailem a funguje okamžitě. (Mně odpověděli rychle.)

Co je dobré vědět:

- Klíč je **osobní** – nikomu ho nesdílejte a nikam ho nezveřejňujte. **Každý si žádá vlastní.**
- Limit je **20 stránek za hodinu** na jeden klíč. Tato integrace volá web pouze 4× denně pro každé palivo.
- Integrace používá data cenové mapy mBenzin, nikoli oficiálně zdokumentované API. Buďte k serveru ohleduplní a respektujte podmínky mBenzin.

## 2. Instalace přes HACS

1. V HACS otevřete menu **⋮ → Vlastní repozitáře** a přidejte `https://github.com/donthedandy/ha-mbenzin-ceny-paliv` s kategorií **Integrace** (Integration).
2. Vyhledejte **mBenzin**, stáhněte ho a **restartujte** Home Assistant.
3. Otevřete **Nastavení → Zařízení a služby → Přidat integraci → mBenzin** a postupně zadejte:
   1. **přístupový klíč**,
   2. **město** (výběr ze seznamu),
   3. **paliva** (jedno nebo více) a **jazyk** textů v dashboardu,
   4. pro každé palivo **oblíbenou stanici** ze seznamu stanic ve vašem městě (nebo „—“, pokud žádnou nechcete).

Paliva, jazyk i oblíbené stanice můžete později změnit tlačítkem **Konfigurovat** u integrace.

> Texty samotného nastavení se řídí jazykem Home Assistantu (čeština i angličtina jsou k dispozici). Volba jazyka v kroku „Paliva a jazyk“ určuje jen popisky v hotových pohledech dashboardu.

## Senzory

Pro každé palivo `<palivo>` (`n95`, `benzinplus`, `diesel`, `dieselplus`, `lpg`, `cng`, `adblue`):

| Entita | Co obsahuje |
|---|---|
| `sensor.mbenzin_<palivo>_top5` | cena nejlevnější stanice; v atributech je všech 5 stanic (název, adresa, cena, souřadnice, odkaz na Google Maps, trendy…) a texty v zvoleném jazyce |
| `sensor.mbenzin_<palivo>_home` | cena u vaší oblíbené stanice (jen pokud jste nějakou vybrali), trendy, pořadí, statistika |
| `sensor.mbenzin_<palivo>_1` … `_5` | 5 nejlevnějších stanic se zeměpisnou šířkou a délkou pro kartu mapy |

Ceny se obnovují každých 6 hodin. Pokud se aktualizace nepovede (třeba kvůli chybě 429), zůstanou zachována poslední data a atribut `fetch_error` uvede důvod.

## 3. Dashboard (volitelné)

1. Z HACS nainstalujte [`button-card`](https://github.com/custom-cards/button-card).
2. **Dashboard → Upravit → + (přidat pohled) → ⋮ → Upravit v YAML** → vložte obsah souboru `dashboard/fuel_view_<palivo>.yaml` (n95, diesel, lpg, cng) → Uložit. Pro každé palivo jeden pohled.
3. Kulatá loga řetězců (např. `orlen.png`, `makro.png`, 128 px) se zobrazí, pokud je dáte do `config/www/`. Jde o ochranné známky, proto nejsou součástí repozitáře; chybějící loga se prostě nezobrazí. V pohledu můžete upravit seznam `LOGOS` podle svých řetězců.
4. Nemáte pro dané palivo oblíbenou stanici? Odstraňte z pohledu první kartu a řádek `…_home` v kartě mapy.

Upozornění na změnu ceny na telefonu: viz `examples/price_alert.yaml`.

## Poznámky

- **E10** mBenzin nerozlišuje: u Natural 95 jde o cenu pro všechny 95oktanové benzíny.
- Entity se jmenují `sensor.mbenzin_<palivo>_…`. Druhé město by dostalo příponu `_2`.
- Denní záznam cen potřebný pro trendy ukládá Home Assistant a postupně se plní (hvězdička v pohledu označuje trend z kratší historie).

## Licence

MIT – viz [LICENSE](LICENSE).
