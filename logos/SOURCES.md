# Station logo pack

Optional round-ready PNG logos (128 × 128, white background) for the chains most common in the mBenzin data. They are **not** part of the integration: the integration downloads only the ones you tick (Settings → Devices & services → Ceny paliv → Configure → *Station logos*), or you can copy the files by hand (see the main README).

**The logos are trademarks of their respective owners.** They are used here only to identify the stations in a dashboard, nothing more. This project is independent and not affiliated with, endorsed or sponsored by any of these companies or by mBenzin.cz. If you are a rights holder and want a logo removed, open an issue and it will be removed promptly.

Sources (the files were resized and placed on a white square; the artwork itself is unchanged):

| File | Chain | Source |
|---|---|---|
| `armex.png` | Armex Oil | [armexoil.cz website icon](https://www.armexoil.cz/) |
| `avia.png` | AVIA | [Commons: File:Avia logo (1983).svg](https://commons.wikimedia.org/wiki/File:Avia_logo_(1983).svg) |
| `eurooil.png` | EuroOil | [Commons: File:Logo EuroOil.png](https://commons.wikimedia.org/wiki/File:Logo_EuroOil.png) |
| `exxon.png` | Exxon | [Commons: File:Exxon logo.svg](https://commons.wikimedia.org/wiki/File:Exxon_logo.svg) |
| `globus.png` | Globus | [Commons: File:Logo of Globus (2009).svg](https://commons.wikimedia.org/wiki/File:Logo_of_Globus_(2009).svg) |
| `gulf.png` | Gulf | [Commons: File:Gulf Oil logo.svg](https://commons.wikimedia.org/wiki/File:Gulf_Oil_logo.svg) |
| `makro.png` | Makro | [Commons: File:Makro logo la.svg](https://commons.wikimedia.org/wiki/File:Makro_logo_la.svg) |
| `mol.png` | MOL | [Commons: File:MOL Logo.svg](https://commons.wikimedia.org/wiki/File:MOL_Logo.svg) |
| `omv.png` | OMV | [Commons: File:Omv logo.svg](https://commons.wikimedia.org/wiki/File:Omv_logo.svg) |
| `orlen.png` | Orlen | [Commons: File:Orlen wordmark logo.svg](https://commons.wikimedia.org/wiki/File:Orlen_wordmark_logo.svg) |
| `shell.png` | Shell | [Commons: File:Shell.svg](https://commons.wikimedia.org/wiki/File:Shell.svg) |
| `silmet.png` | Silmet | [silmet.cz website icon](https://silmet.cz/) |
| `tankono.png` | Tank ONO | [Commons: File:Logo tank ono.gif](https://commons.wikimedia.org/wiki/File:Logo_tank_ono.gif) |
| `tesco.png` | Tesco | [Commons: File:Tesco 2016 logo.svg](https://commons.wikimedia.org/wiki/File:Tesco_2016_logo.svg) |
| `texaco.png` | Texaco | [Commons: File:Texaco logo.svg](https://commons.wikimedia.org/wiki/File:Texaco_logo.svg) |
| `tomegas.png` | Tomegas | [tomegas.cz website icon](https://tomegas.cz/) |

`index.json` lists the pack: `id` is the file name, `match` the chain names (as written in the mBenzin data, lower case, no diacritics) the logo is used for. A chain name matches when it equals a `match` entry or starts with it followed by a space (so `AVIA XPress` uses the AVIA logo).

## Adding more logos

Pull requests are welcome: a 128 × 128 PNG (logo centred with some margin on a white background, under 150 kB), a line in `index.json` and a line with the source in this file.
