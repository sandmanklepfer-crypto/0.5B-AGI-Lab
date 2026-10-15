/* ============================================================================
 *  fp.js —— 唯一指纹 + 访客留痕（官网 & 游戏页通用，零依赖）
 *  --------------------------------------------------------------------------
 *  解决什么问题：
 *    旧版访客 id = 'f'+Math.random()（存在 localStorage），换个浏览器 / 清一次缓存
 *    就是"一个新人"→ 访客数忽多忽少、根本没法信。
 *
 *  现在怎么做（三层，越靠前越稳）：
 *    ① 设备指纹（Fingerprint）：UA/平台/时区/语言/CPU 核数/内存/分辨率/触摸点数
 *       + Canvas 指纹 + WebGL 显卡指纹 → 哈希成一个稳定 id。**清缓存也不会变。**
 *    ② 稳定 UID：localStorage 存一份（tianlei_uid），下次优先用它；丢了就靠 ①找回。
 *    ③ 人物档案（Profile）：localStorage 'tianlei_profile' —— **与游戏存档完全分开**。
 *
 *  ★ 人物 vs 游戏数据（用户要求：游戏数据可销毁，人物记录千万别销毁）：
 *    · 人物记录 = broker 保留消息 `zhz/tianlei/stats/v/<uid>` + 本地 'tianlei_profile'
 *                 → 存在服务器(broker)上，本地怎么清都在，永不被"清档"影响。
 *    · 游戏数据 = localStorage 'tianlei_save'（战绩/建造/时长）
 *                 → Fp.wipeGame() 只删这一份，绝不碰上面那条。
 *
 *  隐私开关：Fp.IP_MODE   'plain'（默认，存明文 IP） | 'hash'（只存加盐哈希） | 'none'
 *  ========================================================================== */
(function (root) {
  'use strict';

  var Fp = {
    /* —— 存储键（★ 人物相关键永不进 LS_SAVE）—— */
    V: 'zhz/tianlei/stats/v/',      // ★ 人物记录：broker 保留消息，一人一条，永不销毁
    LS_UID: 'tianlei_uid',          // 稳定唯一 id
    LS_PROFILE: 'tianlei_profile',  // ★ 本地人物档案（与游戏存档解耦；清档不删）
    LS_SAVE: ['tianlei_save'],      // 游戏数据（可销毁）

    /* —— 隐私开关 —— */
    IP_MODE: 'plain',               // 'plain' | 'hash' | 'none'
    SALT: 'tlFp#2026-zhz',

    _fp: null, _uid: null, _dev: null, _prof: null, _ip: '', _geo: '', _org: '',

    /* ------------------------------------------------------------------ */
    /*  存储小工具（localStorage 可能被禁用 → 全部 try 包住，失败则退化为会话级） */
    ls: function () { try { return root.localStorage; } catch (e) { return null; } },

    /* —— 字符串哈希（两路 32 位 FNV/变体 → 稳定短 id）—— */
    hash: function (s) {
      s = String(s || ''); var h1 = 0x811c9dc5 >>> 0, h2 = 0x1000193 >>> 0;
      for (var i = 0; i < s.length; i++) {
        var c = s.charCodeAt(i);
        h1 = Math.imul(h1 ^ c, 16777619) >>> 0;
        h2 = Math.imul(h2 + c, 2654435761) >>> 0;
      }
      return (h1.toString(36) + h2.toString(36)).slice(0, 12);
    },

    /* —— Canvas 指纹：不同 GPU/字体/抗锯齿渲染出的像素不同 —— */
    canvasSig: function () {
      try {
        var c = document.createElement('canvas'); c.width = 240; c.height = 44;
        var x = c.getContext('2d'); if (!x) return 'nc';
        x.textBaseline = 'top'; x.font = '16px "Arial"';
        x.fillStyle = '#f60'; x.fillRect(0, 0, 130, 20);
        x.fillStyle = '#069'; x.fillText('天泪指纹 TL-fp 2026 ✓', 2, 2);
        x.fillStyle = 'rgba(102,204,0,0.7)'; x.fillText('天泪指纹 TL-fp 2026 ✓', 4, 6);
        x.globalCompositeOperation = 'multiply';
        x.fillStyle = 'rgb(255,0,255)'; x.beginPath(); x.arc(64, 22, 17, 0, Math.PI * 2); x.fill();
        return c.toDataURL();
      } catch (e) { return 'nc'; }
    },

    /* —— WebGL 指纹：显卡厂商 / 渲染器 / 纹理上限 —— */
    glSig: function () {
      try {
        var c = document.createElement('canvas');
        var g = c.getContext('webgl') || c.getContext('experimental-webgl'); if (!g) return 'ng';
        var d = g.getExtension('WEBGL_debug_renderer_info');
        var v = d ? g.getParameter(d.UNMASKED_VENDOR_WEBGL) : g.getParameter(g.VENDOR);
        var r = d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER);
        return [v, r, g.getParameter(g.MAX_TEXTURE_SIZE), g.getParameter(g.MAX_VERTEX_ATTRIBS)].join('|');
      } catch (e) { return 'ng'; }
    },

    /* —— 设备信息（详版，一份缓存）—— */
    device: function () {
      if (this._dev) return this._dev;
      var n = (root.navigator || {}), s = (root.screen || {});
      var tz = ''; try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) {}
      this._dev = {
        ua: n.userAgent || '',
        plat: n.platform || '',
        vendor: n.vendor || '',
        lang: n.language || '',
        langs: (n.languages || []).join(','),
        tz: tz,
        cores: n.hardwareConcurrency || 0,
        mem: n.deviceMemory || 0,
        touch: n.maxTouchPoints || 0,
        dpr: root.devicePixelRatio || 1,
        scr: (s.width || 0) + 'x' + (s.height || 0) + '@' + (s.colorDepth || 0),
        cookie: n.cookieEnabled ? 1 : 0,
        mobile: /Mobi|Android|iPhone|iPad|iPod/i.test(n.userAgent || '') ? 1 : 0,
        canvas: this.canvasSig(),
        gl: this.glSig()
      };
      return this._dev;
    },

    /* —— 综合指纹（稳定 id 的种子）—— */
    fp: function () {
      if (this._fp) return this._fp;
      var d = this.device();
      this._fp = this.hash([d.ua, d.plat, d.vendor, d.lang, d.langs, d.tz, d.cores, d.mem,
        d.touch, d.dpr, d.scr, d.canvas, d.gl].join('~'));
      return this._fp;
    },

    /* —— 稳定 UID：优先 localStorage，丢了用指纹重建 —— */
    uid: function () {
      if (this._uid) return this._uid;
      var ls = this.ls(), u = null;
      try { u = ls && ls.getItem(this.LS_UID); } catch (e) {}
      if (!u) { u = 'u' + this.fp(); try { ls && ls.setItem(this.LS_UID, u); } catch (e) {} }
      this._uid = u; return u;
    },

    /* —— 人物档案（★ 与游戏存档解耦）—— */
    profile: function () {
      if (this._prof) return this._prof;
      var ls = this.ls(), o = null;
      try { o = JSON.parse((ls && ls.getItem(this.LS_PROFILE)) || 'null'); } catch (e) {}
      if (!o || !o.uid) o = { uid: this.uid(), fp: this.fp(), firstAt: Date.now(), visits: 0, pages: {} };
      this._prof = o; return o;
    },
    saveProfile: function () { try { var ls = this.ls(); ls && ls.setItem(this.LS_PROFILE, JSON.stringify(this._prof)); } catch (e) {} },

    /* —— 公网 IP（多源回退，任一成功即用）—— */
    getIP: function (cb) {
      var self = this;
      if (this._ip !== null && this._ip !== undefined && this._ip !== '') return cb(this._ip);
      if (this._ipDone) return cb(this._ip || '');
      var urls = [
        'https://api.ipify.org?format=json',
        'https://ipapi.co/json/',
        'https://api.ip.sb/geoip',
        'https://ifconfig.me/all.json'
      ], i = 0;
      function next() {
        if (i >= urls.length) { self._ipDone = true; self._ip = self._ip || ''; return cb(self._ip); }
        var u = urls[i++], to = setTimeout(next, 3500);
        try {
          fetch(u, { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (j) {
            clearTimeout(to);
            var ip = j.ip || j.ip_addr || j.query || '';
            self._geo = j.country_name || j.country || j.country_code || self._geo || '';
            self._org = j.org || j.isp || j.asn_org || (j.connection && j.connection.isp) || self._org || '';
            if (ip) { self._ip = ip; self._ipDone = true; cb(ip); } else next();
          }).catch(function () { clearTimeout(to); next(); });
        } catch (e) { clearTimeout(to); next(); }
      }
      next();
    },

    /* —— 组装上报体 —— */
    payload: function (page, extra) {
      var p = this.profile(), d = this.device();
      var ip = this._ip || '';
      var ipOut = this.IP_MODE === 'none' ? '' : (this.IP_MODE === 'hash' ? this.hash(this.SALT + ip) : ip);
      return {
        v: 2,
        id: p.uid, fp: p.fp, page: page || '', name: p.name || '', room: p.room || '',
        at: Date.now(), firstAt: p.firstAt, visits: p.visits, pages: p.pages || {},
        ip: ipOut, ipMode: this.IP_MODE,
        geo: this._geo || '', org: this._org || '',
        ua: d.ua, plat: d.plat, tz: d.tz, lang: d.lang, langs: d.langs,
        cores: d.cores, mem: d.mem, touch: d.touch, dpr: d.dpr, scr: d.scr, mobile: d.mobile,
        canvas: this.hash(d.canvas), gl: String(d.gl).slice(0, 96),
        ref: (root.document && document.referrer) || '',
        url: (root.location ? location.href : '').slice(0, 180),
        extra: extra || null
      };
    },

    /* —— 上报（优先复用游戏已有的 MQTT，其次自建短连接；都没有则只存本地）—— */
    emit: function (payload, cb) {
      var self = this, done = false;
      function fin() { if (!done) { done = true; try { cb && cb(payload); } catch (e) {} } }
      var send = function (publish) { try { publish(self.V + payload.id, JSON.stringify(payload), true); fin(); } catch (e) { fin(); } };
      // ① 游戏页已有连接 → 直接用
      if (root.Net && Net.connected && Net.pub) { send(function (t, s, r) { Net.pub(t, s, r); }); return; }
      // ② 自建一次性连接
      if (typeof MiniMqtt === 'undefined' || !MiniMqtt.createClient) { fin(); return; }
      try {
        var mq = MiniMqtt.createClient({ clientId: 'tlfp' + String(payload.id).slice(0, 8) });
        var to = setTimeout(function () { try { mq.end && mq.end(); } catch (e) {} fin(); }, 9000);
        mq.on('connect', function () {
          try { mq.publish(self.V + payload.id, JSON.stringify(payload), true); } catch (e) {}
          clearTimeout(to); setTimeout(function () { try { mq.end && mq.end(); } catch (e) {} fin(); }, 700);
        });
        mq.on('error', function () { clearTimeout(to); fin(); });
      } catch (e) { fin(); }
    },

    /* —— 对外主入口：进一次页面就留一条（官网/游戏页都调它）——
       opts.nofcount = true 时只刷新姓名/房间等，不重复计一次到访 */
    track: function (page, extra, opts) {
      var self = this, p = this.profile(), noc = opts && opts.nofcount;
      if (!noc) { p.visits = (p.visits || 0) + 1; p.lastAt = Date.now(); }
      if (page && !noc) { p.pages = p.pages || {}; p.pages[page] = (p.pages[page] || 0) + 1; p.lastPage = page; }
      if (extra) { if (extra.name) p.name = extra.name; if (extra.room) p.room = extra.room; }
      this.saveProfile();
      this.getIP(function () { self.emit(self.payload(page, extra)); });
      return p;
    },

    /* —— ★ 清游戏数据：只删 tianlei_save，人物记录/UID 一律不动 —— */
    wipeGame: function () {
      var ls = this.ls(), removed = [];
      this.LS_SAVE.forEach(function (k) { try { if (ls && ls.getItem(k) != null) { ls.removeItem(k); removed.push(k); } } catch (e) {} });
      return removed;
    },
    /* —— 人物记录自身的键（供检查/演示"清档不删人物"）—— */
    profileKeys: function () { return [this.LS_UID, this.LS_PROFILE]; },
    topic: function () { return this.V + this.uid(); }
  };

  root.Fp = Fp;
  if (typeof module === 'object' && module.exports) module.exports = Fp;
})(typeof self !== 'undefined' ? self : this);
