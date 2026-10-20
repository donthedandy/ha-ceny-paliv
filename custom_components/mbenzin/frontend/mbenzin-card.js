/*
 * mBenzin card — shipped with the mBenzin integration, nothing to install separately.
 *
 *   type: custom:mbenzin-card
 *   fuel: n95            # n95 | benzinplus | diesel | dieselplus | lpg | cng | adblue
 *
 * Optional:
 *   show_map: true        # map with the 5 cheapest stations (+ your favourite one)
 *   show_graph: true      # 30-day graph of your favourite station
 *   logos: [orlen, makro] # chains for which /local/<chain>.png exists (round 128 px PNG in config/www/)
 *   logo_path: /local/
 *
 * The card also has a visual editor: Add card > mBenzin.
 *
 * Texts come from the language chosen in the integration setup (attribute `labels` of the top5 sensor).
 */
const MBENZIN_CARD_VERSION = '0.2.1';

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const STYLE = `
  :host { display: block; }
  .stack { display: flex; flex-direction: column; gap: 16px; }
  .card { background: #171a20; border: 1px solid #262a33; border-radius: 22px; padding: 16px; color: #eef0f3;
          font-family: Manrope, system-ui, sans-serif; box-sizing: border-box; }
  .card.home { border-color: rgba(76,195,217,0.30); cursor: pointer; }
  .row { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-top: 1px solid #23272f; cursor: pointer; user-select: none; }
  .row:first-of-type { border-top: none; }
  .map, .graph { border-radius: 22px; overflow: hidden; }
  ha-icon { display: inline-block; }
`;

class MBenzinCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._sig = '';
    this._children = null;
    this._timer = null;
  }

  setConfig(config) {
    if (!config || !config.fuel) throw new Error('mbenzin-card: set "fuel", for example "n95"');
    this._config = Object.assign({ show_map: true, show_graph: true, logos: [], logo_path: '/local/' }, config);
    this._ids = null;
    this._scanAt = 0;
    this._sig = '';
    this._children = null;
    this._build();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    this._ids = this._resolve(hass);
    const top = hass.states[this._ids.top5];
    const home = hass.states[this._ids.home];
    const sig = [top && top.last_updated, home && home.last_updated, top && top.state, home && home.state].join('|');
    if (sig !== this._sig) {
      this._sig = sig;
      this._renderTexts();
    }
    if (this._children) this._children.forEach((c) => { c.hass = hass; });
  }

  // Find this fuel's sensors by their attributes, so the card does not depend on how Home Assistant names the
  // entities (device name prefix, renamed entities, second city...). Older installs without the attributes are
  // matched on the entity id suffix (..._<fuel>_top5, _home, _1 .. _5).
  _resolve(hass) {
    const c = this._ids;
    const valid = c && c.top5 && hass.states[c.top5] && (!c.home || hass.states[c.home]) && c.pos.every((id) => !id || hass.states[id]);
    const now = Date.now();
    if (valid && (c.home || now - this._scanAt < 10000)) return c;
    this._scanAt = now;
    const fuel = this._config.fuel;
    const ids = { top5: null, home: null, pos: [] };
    for (const id of Object.keys(hass.states)) {
      if (!id.startsWith('sensor.mbenzin_')) continue;
      const a = hass.states[id].attributes || {};
      let role = null; let idx = 0;
      if (a.mbenzin_fuel) {
        if (a.mbenzin_fuel !== fuel) continue;
        role = a.mbenzin_role; idx = a.mbenzin_index || 0;
      } else {
        const m = id.match(/_([a-z0-9]+)_(top5|home|[1-5])$/);
        if (!m || m[1] !== fuel) continue;
        role = m[2] === 'top5' ? 'top5' : m[2] === 'home' ? 'home' : 'position'; idx = /^\d$/.test(m[2]) ? Number(m[2]) : 0;
      }
      if (role === 'top5') ids.top5 = id;
      else if (role === 'home') ids.home = id;
      else if (role === 'position' && idx >= 1 && idx <= 5) ids.pos[idx - 1] = id;
    }
    return ids;
  }

  getCardSize() { return 12; }
  getGridOptions() { return { columns: 12, min_columns: 6 }; }
  static getConfigElement() { return document.createElement('mbenzin-card-editor'); }
  static fuels(hass) {
    const out = [];
    for (const [id, st] of Object.entries((hass && hass.states) || {})) {
      if (!id.startsWith('sensor.mbenzin_')) continue;
      const a = st.attributes || {};
      const isTop = a.mbenzin_role === 'top5' || (!a.mbenzin_role && /_top5$/.test(id) && a.fuel);
      if (isTop && a.fuel && !out.some((o) => o.value === a.fuel)) out.push({ value: a.fuel, label: a.fuel_label || a.fuel });
    }
    return out;
  }
  static getStubConfig(hass) {
    const found = MBenzinCard.fuels(hass)[0];
    return { type: 'custom:mbenzin-card', fuel: found ? found.value : 'n95' };
  }

  // ---------------------------------------------------------------- skeleton
  _build() {
    const root = this.shadowRoot;
    root.innerHTML = `<style>${STYLE}</style><div class="stack"><div id="texts"></div><div id="extra" class="stack"></div></div>`;
    root.addEventListener('click', (e) => this._click(e));
    root.addEventListener('pointerdown', (e) => this._down(e));
    ['pointerup', 'pointerleave', 'pointercancel'].forEach((n) => root.addEventListener(n, () => clearTimeout(this._timer)));
    this._extraReady = false;
  }

  async _buildExtra() {
    if (this._extraReady || !this._hass) return;
    this._extraReady = true;
    const c = this._config;
    const extra = this.shadowRoot.getElementById('extra');
    const helpers = window.loadCardHelpers ? await window.loadCardHelpers() : null;
    if (!helpers) return;
    const hasHome = !!this._hass.states[this._ids.home];
    const kids = [];
    if (c.show_map) {
      const entities = this._ids.pos.filter(Boolean).map((id) => ({ entity: id, label_mode: 'state', focus: true }));
      if (hasHome) entities.push({ entity: this._ids.home, label_mode: 'state', focus: true });
      kids.push({ cls: 'map', config: { type: 'map', theme_mode: 'dark', auto_fit: true, default_zoom: 12, hours_to_show: 0, entities } });
    }
    if (c.show_graph && hasHome) {
      kids.push({
        cls: 'graph',
        config: {
          type: 'statistics-graph', title: '30 d', entities: [this._ids.home], days_to_show: 30, period: 'day',
          chart_type: 'line', stat_types: ['mean', 'min', 'max'],
        },
      });
    }
    this._children = [];
    for (const k of kids) {
      const el = helpers.createCardElement(k.config);
      el.hass = this._hass;
      const wrap = document.createElement('div');
      wrap.className = k.cls;
      wrap.appendChild(el);
      extra.appendChild(wrap);
      this._children.push(el);
    }
  }

  // ---------------------------------------------------------------- helpers
  _labels() {
    const top = this._hass.states[this._ids.top5];
    return (top && top.attributes && top.attributes.labels) || {};
  }

  _T(k, v) {
    const lb = this._labels();
    return String(lb[k] !== undefined ? lb[k] : k).replace(/\{(\w+)\}/g, (m, x) => (v && v[x] !== undefined ? v[x] : m));
  }

  _arrow(t) {
    if (!t) return { icon: 'mdi:minus', color: '#5b6270', txt: '—' };
    if (t.dir === 'down') return { icon: 'mdi:arrow-down-bold', color: '#5fd39a', txt: '−' + Math.abs(t.delta).toFixed(2) };
    if (t.dir === 'up') return { icon: 'mdi:arrow-up-bold', color: '#ff7a6b', txt: '+' + Math.abs(t.delta).toFixed(2) };
    return { icon: 'mdi:minus', color: '#f5c26b', txt: '0.00' };
  }

  _age(s, today) {
    if (!s.updated_date) return s.updated === 'Dnes' ? 0 : 99;
    return Math.round((today - new Date(s.updated_date + 'T00:00:00')) / 86400000);
  }

  _avatar(s, rank, best) {
    const T = (k) => this._T(k);
    const name = s.name || '—';
    const chain = name.toLowerCase().split(' ')[0];
    const badge = best ? 'background:rgba(95,211,154,0.16);color:#5fd39a' : 'background:#23272f;color:#9aa1ad';
    if (!(this._config.logos || []).map((x) => String(x).toLowerCase()).includes(chain)) {
      return `<span style="width:30px;height:30px;border-radius:999px;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;flex-shrink:0;${badge}">${rank}</span>`;
    }
    const plain = `position:absolute;left:0;top:0;width:30px;height:30px;border-radius:999px;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;${badge}`;
    return `<span style="position:relative;width:32px;height:32px;flex-shrink:0;display:block"><span style="${plain}">${rank}</span><img src="${esc(this._config.logo_path)}${esc(chain)}.png?v=1" alt="${esc(name)}" onload="this.previousElementSibling.style.display='none';this.nextElementSibling.style.display='flex'" onerror="this.style.display='none'" style="position:absolute;left:0;top:0;width:32px;height:32px;border-radius:999px;display:block;${best ? 'box-shadow:0 0 0 2px #5fd39a' : ''}"><span style="display:none;position:absolute;right:-5px;bottom:-5px;min-width:17px;height:17px;padding:0 3px;box-sizing:border-box;border-radius:999px;background:#0e1014;border:1px solid ${best ? '#5fd39a' : '#2a2f39'};color:${best ? '#5fd39a' : '#d6dae1'};font-size:10px;font-weight:800;align-items:center;justify-content:center">${rank}</span></span>`;
  }

  // ---------------------------------------------------------------- rendering
  _renderTexts() {
    const hass = this._hass;
    const top = hass.states[this._ids.top5];
    const host = this.shadowRoot.getElementById('texts');
    if (!top || top.state === 'unavailable') {
      host.innerHTML = `<div class="card" style="color:#9aa1ad;font-size:14px">mBenzin (${esc(this._config.fuel)}): sensor not found or unavailable — is the fuel set up in the integration?</div>`;
      return;
    }
    host.innerHTML = `<div class="stack">${this._homeHtml()}${this._listHtml()}</div>`;
    this._buildExtra();
  }

  _homeHtml() {
    const e = this._hass.states[this._ids.home];
    if (!e) return '';
    const T = (k, v) => this._T(k, v);
    const LOC = this._labels().locale || 'en-GB';
    const a = e.attributes;
    const stationName = a.station || T('my_station');
    const ok = !['unavailable', 'unknown'].includes(e.state);
    const price = ok ? Number(e.state).toFixed(2) : '—';
    const stale = a.age_days == null || Number(a.age_days) > 1;
    const updTxt = a.age_days == 0 ? T('updated_today') : (a.age_days == 1 ? T('updated_yesterday') : T('price_from', { d: a.updated || '—' }));
    const tr = a.trends || {};
    const today = new Date(); today.setHours(0, 0, 0, 0);
    let partial = null;
    const chip = (n) => {
      const t = tr[String(n)]; const r = this._arrow(t);
      let covered = true;
      if (t) {
        const target = new Date(today); target.setDate(target.getDate() - n);
        covered = new Date(t.ref_date + 'T00:00:00') <= target; if (!covered) partial = t.ref_date;
      }
      return `<div style="display:flex;flex-direction:column;align-items:center;gap:2px;background:#1f232b;border-radius:12px;padding:8px 2px;min-width:0">
        <span style="font-size:11px;font-weight:700;color:#9aa1ad">${n} d${t && !covered ? '*' : ''}</span>
        <ha-icon icon="${r.icon}" style="--mdc-icon-size:18px;color:${r.color}"></ha-icon>
        <span style="font-size:13px;font-weight:800;color:${r.color};white-space:nowrap">${r.txt}</span></div>`;
    };
    const chips = [1, 2, 7, 14, 30].map(chip).join('');
    const anyTrend = Object.values(tr).some(Boolean);
    const note = !anyTrend ? T('trends_start')
      : (partial ? T('since_partial', { d: new Date(partial + 'T00:00:00').toLocaleDateString(LOC, { day: 'numeric', month: 'short' }) }) : '');
    let pos;
    if (a.rank == null) pos = `<span style="color:#f5c26b">${esc(T('not_ranked'))}</span>`;
    else if (Number(a.vs_cheapest) <= 0) pos = `<span style="color:#5fd39a">${esc(T('cheapest_town', { rank: a.rank, n: a.fresh_count }))}</span>`;
    else pos = `<span style="color:#f5c26b">${esc(T('vs_cheapest', { d: Number(a.vs_cheapest).toFixed(2), name: a.cheapest_name, rank: a.rank, n: a.fresh_count }))}</span>`;
    const chain0 = stationName.split(' ')[0].toLowerCase();
    const iconBox = `<div style="position:absolute;left:0;top:0;width:44px;height:44px;border-radius:14px;display:flex;align-items:center;justify-content:center;background:rgba(76,195,217,0.16)"><ha-icon icon="mdi:gas-station-in-use" style="--mdc-icon-size:22px;color:#4cc3d9"></ha-icon></div>`;
    const logoImg = (this._config.logos || []).map((x) => String(x).toLowerCase()).includes(chain0)
      ? `<img src="${esc(this._config.logo_path)}${esc(chain0)}.png?v=1" onload="this.previousElementSibling.style.display='none'" onerror="this.style.display='none'" style="position:absolute;left:0;top:0;width:44px;height:44px;border-radius:999px;display:block">`
      : '';
    const logo = `<div style="position:relative;width:44px;height:44px;flex-shrink:0">${iconBox}${logoImg}</div>`;
    return `<div class="card home" data-more-info="${esc(this._ids.home)}">
      <div style="display:flex;flex-direction:column;gap:12px;width:100%;text-align:left">
        <div style="display:flex;align-items:center;gap:12px">${logo}
          <div style="flex:1 1 auto;display:flex;flex-direction:column;gap:2px;min-width:0">
            <span style="font-size:12px;letter-spacing:.09em;text-transform:uppercase;font-weight:700;color:#9aa1ad">${esc(T('my_station'))}</span>
            <span style="font-size:15px;font-weight:700;color:#eef0f3">${esc(stationName)}</span>
            <span style="font-size:12px;color:${stale ? '#f5c26b' : '#9aa1ad'}">${esc(updTxt)}</span></div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;flex-shrink:0">
            <span style="font-size:40px;font-weight:800;letter-spacing:-0.03em;line-height:1;color:${stale ? '#9aa1ad' : '#eef0f3'}">${price}</span>
            <span style="font-size:11px;color:#9aa1ad;font-weight:600">${esc(a.unit_of_measurement || 'Kč/l')}</span></div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px">${chips}</div>
        ${note ? `<span style="font-size:11px;color:#5b6270;margin-top:-4px">${esc(note)}</span>` : ''}
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12px;font-weight:600">${pos}
          <span style="color:#5b6270;font-weight:500;white-space:nowrap">${esc(T('tap_history'))}</span></div>
      </div></div>`;
  }

  _listHtml() {
    const S = this._hass.states[this._ids.top5];
    const at = S.attributes;
    const T = (k, v) => this._T(k, v);
    const LOC = this._labels().locale || 'en-GB';
    const all = Array.isArray(at.stations) ? at.stations : [];
    const maxAge = at.max_age_days != null ? Number(at.max_age_days) : 1;
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const list = all.filter((s) => this._age(s, today) <= maxAge);
    const prices = list.map((s) => Number(s.price)).filter((p) => !isNaN(p));
    const min = prices.length ? Math.min(...prices) : null;
    const unit = at.unit_of_measurement || 'Kč/l';
    const fp = (p) => Number(p).toFixed(2);
    const n = min === null ? 0 : list.filter((s) => Number(s.price) === min).length;
    const sub = min === null ? T('no_recent') : T('cheapest_price', { p: fp(min), unit }) + (n > 1 ? ' · ' + T('stations_same', { n }) : '');
    const head = `<div style="display:flex;align-items:center;gap:12px;width:100%;padding-bottom:12px">
      <div style="width:44px;height:44px;border-radius:14px;display:flex;align-items:center;justify-content:center;background:rgba(245,177,76,0.16);flex-shrink:0">
        <ha-icon icon="mdi:gas-station" style="--mdc-icon-size:22px;color:#f5b14c"></ha-icon></div>
      <div style="flex:1 1 auto;display:flex;flex-direction:column;gap:2px;text-align:left;min-width:0">
        <span style="font-size:15px;font-weight:700;color:#eef0f3">${esc(at.fuel_label || this._config.fuel)} · ${esc(at.city_name || '')}</span>
        <span style="font-size:13px;color:#9aa1ad">${esc(sub)}</span></div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;flex-shrink:0">
        <span style="font-size:28px;font-weight:800;letter-spacing:-0.02em;line-height:1;color:${min === null ? '#5b6270' : '#5fd39a'}">${min === null ? '—' : fp(min)}</span>
        <span style="font-size:11px;color:#9aa1ad;font-weight:600">${esc(unit)}</span></div></div>`;
    const rows = list.map((s, i) => {
      const best = Number(s.price) === min;
      const diff = Number(s.price) - min;
      const name = s.name || '—';
      const a0 = s.address || '';
      const addr = a0.startsWith(name) ? a0.slice(name.length).trim() : a0;
      const tr = this._arrow((s.trends || {})['1']);
      const age = this._age(s, today);
      const when = age <= 0 ? T('today') : `<span style="color:#f5c26b">${esc(age === 1 ? T('yesterday') : (s.updated || '—'))}</span>`;
      const home = s.home ? `<ha-icon icon="mdi:home" title="${esc(T('my_station'))}" style="--mdc-icon-size:14px;color:#4cc3d9;margin-left:6px"></ha-icon>` : '';
      return `<div class="row" data-maps="${esc(s.maps)}">
        ${this._avatar(s, i + 1, best)}
        <div style="flex:1 1 auto;display:flex;flex-direction:column;gap:2px;text-align:left;min-width:0">
          <span style="font-size:15px;font-weight:700;color:#eef0f3">${esc(name)}${home}</span>
          <span style="font-size:12px;color:#9aa1ad;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(addr)} · ${when}</span></div>
        <div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;width:40px" title="${esc(T('vs_yesterday'))}">
          <ha-icon icon="${tr.icon}" style="--mdc-icon-size:18px;color:${tr.color}"></ha-icon>
          <span style="font-size:10px;font-weight:700;color:${tr.color}">${tr.txt}</span></div>
        <div style="display:flex;flex-direction:column;align-items:flex-end;flex-shrink:0;gap:1px">
          <span style="font-size:18px;font-weight:800;color:${best ? '#5fd39a' : '#eef0f3'}">${fp(s.price)}</span>
          <span style="font-size:11px;font-weight:600;color:${best ? '#5fd39a' : '#9aa1ad'}">${esc(best ? T('cheapest_badge') : '+' + fp(diff))}</span></div>
        <ha-icon icon="mdi:chevron-right" style="--mdc-icon-size:18px;color:#5b6270;flex-shrink:0"></ha-icon></div>`;
    }).join('');
    // footer
    const now = new Date();
    const hm = (d) => d.toLocaleTimeString(LOC, { hour: '2-digit', minute: '2-digit' });
    const when = (d) => (d.toDateString() === now.toDateString() ? hm(d) : d.toLocaleString(LOC, { weekday: 'short', hour: '2-digit', minute: '2-digit' }));
    const fa = at.fetched_at ? new Date(at.fetched_at) : null;
    const la = at.last_attempt ? new Date(at.last_attempt) : null;
    const nu = at.next_update ? new Date(at.next_update) : null;
    const hidden = (at.excluded || 0) + (all.length - list.length);
    const lines = [`<span style="font-size:13px;color:#d6dae1;font-weight:600">${esc(T('table_updated', { t: fa ? when(fa) : '—', n: nu ? when(nu) : '—' }))}</span>`];
    if (at.fetch_error) lines.push(`<span style="font-size:12px;color:#f5c26b">${esc(T('refresh_failed', { at: la ? T('at') + when(la) : '', err: at.fetch_error }))}</span>`);
    if (at.city_total) lines.push(`<span style="font-size:12px;color:#9aa1ad">${esc(T('hidden', { h: hidden, t: at.city_total, age: maxAge >= 1 ? T('yesterday_l') : T('today_l') }))}</span>`);
    lines.push(`<span style="font-size:11px;color:#9aa1ad">${esc(T('arrows'))} · <span style="color:#5fd39a">▼ ${esc(T('down'))}</span> · <span style="color:#f5c26b">— ${esc(T('stable'))}</span> · <span style="color:#ff7a6b">▲ ${esc(T('up'))}</span> · ${esc(T('longpress'))}</span>`);
    lines.push(`<span style="font-size:11px;color:#5b6270">mBenzin.cz · ${esc(at.fuel_label || '')}${at.fuel === 'n95' ? ' ' + esc(T('e10_note')) : ''} · ${esc(T('tap_station'))}</span>`);
    const foot = `<div style="display:flex;flex-direction:column;gap:3px;text-align:left;border-top:1px solid #23272f;padding-top:12px">${lines.join('')}</div>`;
    return `<div class="card" data-more-info="${esc(this._ids.home || this._ids.top5)}">${head}${rows}${foot}</div>`;
  }

  // ---------------------------------------------------------------- interaction
  _entityId(e) {
    const t = e.composedPath ? e.composedPath().find((n) => n.dataset && (n.dataset.maps || n.dataset.moreInfo)) : null;
    return t || null;
  }

  _down(e) {
    const t = this._entityId(e);
    this._long = false;
    clearTimeout(this._timer);
    if (t && t.dataset.maps) {
      this._timer = setTimeout(() => {
        this._long = true;
        this._moreInfo(this._ids.home || this._ids.top5);
      }, 550);
    }
  }

  _click(e) {
    const t = this._entityId(e);
    if (!t) return;
    if (this._long) { this._long = false; return; }
    if (t.dataset.maps) window.open(t.dataset.maps, '_blank', 'noopener');
    else if (t.dataset.moreInfo && !e.composedPath().some((n) => n.dataset && n.dataset.maps)) this._moreInfo(t.dataset.moreInfo);
  }

  _moreInfo(entityId) {
    this.dispatchEvent(new CustomEvent('hass-more-info', { bubbles: true, composed: true, detail: { entityId } }));
  }
}


// ------------------------------------------------------------------ visual editor
const EDITOR_TEXT = {
  en: { fuel: 'Fuel', show_map: 'Show the map', show_graph: 'Show the 30-day graph of my favourite station' },
  cs: { fuel: 'Palivo', show_map: 'Zobrazit mapu', show_graph: 'Zobrazit graf za 30 dní oblíbené stanice' },
};

class MBenzinCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; this._render(); }
  set hass(hass) { this._hass = hass; this._render(); }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement('ha-form');
      this._form.addEventListener('value-changed', (e) => {
        this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: Object.assign({}, this._config, e.detail.value) }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    const lang = ((this._hass.language || 'en').split('-')[0] in EDITOR_TEXT) ? this._hass.language.split('-')[0] : 'en';
    const options = MBenzinCard.fuels(this._hass);
    this._form.hass = this._hass;
    this._form.data = Object.assign({ show_map: true, show_graph: true }, this._config);
    this._form.schema = [
      { name: 'fuel', required: true, selector: { select: { options, mode: 'dropdown' } } },
      { name: 'show_map', selector: { boolean: {} } },
      { name: 'show_graph', selector: { boolean: {} } },
    ];
    this._form.computeLabel = (schema) => EDITOR_TEXT[lang][schema.name] || schema.name;
  }
}
if (!customElements.get('mbenzin-card-editor')) customElements.define('mbenzin-card-editor', MBenzinCardEditor);

if (!customElements.get('mbenzin-card')) customElements.define('mbenzin-card', MBenzinCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === 'mbenzin-card')) {
  window.customCards.push({
    type: 'mbenzin-card',
    name: 'mBenzin',
    description: 'Cheapest fuel stations of your city, your favourite station, map and 30-day graph (mBenzin integration).',
  });
}
console.info(`%c mBenzin card %c ${MBENZIN_CARD_VERSION} `, 'color:#fff;background:#f5b14c;font-weight:700', 'color:#f5b14c;background:#171a20');
