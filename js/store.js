/* 共用工具：数据读取、金额、订单号、Toast 等 */
window.LH = (function () {
  const DEFAULT_SETTINGS = {
    shopName: '我的卤味小铺',
    slogan: '老卤现捞 · 当天现做',
    notice: '',
    phone: '', wechat: '', hours: '',
    minOrder: 0, deliveryFee: 0, freeDeliveryOver: 0,
    deliveryArea: '',
    deliveryTimeOptions: ['尽快送到'],
    payQrWechat: '', payQrAlipay: '', payNote: '', acceptCash: true,
    orderForm: { provider: 'none', email: '', accessKey: '' },
    adminPin: '1234'
  };

  /* ---------- 数据读取 ---------- */
  async function loadJSON(path, fallback) {
    try {
      const r = await fetch(path + (path.includes('?') ? '&' : '?') + 't=' + Date.now(), { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return await r.json();
    } catch (e) {
      console.warn('[LH] 读取失败 ' + path, e);
      return fallback;
    }
  }
  const loadSettings = () => loadJSON('data/settings.json', {}).then(s => Object.assign({}, DEFAULT_SETTINGS, s || {}));
  const loadProducts = () => loadJSON('data/products.json', { categories: [], items: [] });
  const loadCoupons  = () => loadJSON('data/coupons.json', { items: [] });

  /* ---------- 金额 ---------- */
  const money = n => {
    n = Number(n) || 0;
    let s = (Math.round(n * 100) / 100).toFixed(2);
    s = s.replace(/\.00$/, '').replace(/(\.\d)0$/, '$1');
    return s;
  };
  const yuan = n => '¥' + money(n);

  /* ---------- 安全转义 ---------- */
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  /* ---------- 订单号 ---------- */
  function orderCode() {
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    const stamp = String(d.getFullYear()).slice(2) + p(d.getMonth() + 1) + p(d.getDate()) +
      p(d.getHours()) + p(d.getMinutes());
    const rnd = Math.random().toString(36).slice(2, 5).toUpperCase();
    return 'LH' + stamp + rnd;
  }

  /* ---------- Toast ---------- */
  let toastTimer;
  function toast(msg, ms) {
    let el = document.querySelector('.toast');
    if (!el) { el = document.createElement('div'); el.className = 'toast'; document.body.appendChild(el); }
    el.textContent = msg;
    el.classList.add('on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('on'), ms || 1900);
  }

  /* ---------- 本地存储 ---------- */
  const LS = {
    get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
    del(k) { try { localStorage.removeItem(k); } catch (e) {} }
  };

  /* ---------- 优惠券计算 ---------- */
  // 返回 {ok, discount, freeShip, reason}
  function calcCoupon(cp, subtotal, shipFee) {
    if (!cp || cp.on === false) return { ok: false, reason: '不可用' };
    const today = new Date().toISOString().slice(0, 10);
    if (cp.start && today < cp.start) return { ok: false, reason: '未开始' };
    if (cp.end && today > cp.end) return { ok: false, reason: '已过期' };
    if (cp.total && Number(cp.used || 0) >= Number(cp.total)) return { ok: false, reason: '已抢完' };
    const min = Number(cp.min || 0);
    if (subtotal < min) return { ok: false, reason: '满 ' + money(min) + ' 可用' };
    let discount = 0, freeShip = false;
    if (cp.type === 'percent') {
      const zhe = Number(cp.value) || 100;           // 88 表示 88 折
      discount = subtotal * (1 - zhe / 100);
    } else if (cp.type === 'freeship') {
      freeShip = true; discount = 0;
    } else {
      discount = Math.min(Number(cp.value) || 0, subtotal);
    }
    discount = Math.round(discount * 100) / 100;
    return { ok: true, discount, freeShip };
  }
  function couponLabel(cp) {
    if (cp.type === 'percent') return (Number(cp.value) / 10).toFixed(1).replace(/\.0$/, '') + '折';
    if (cp.type === 'freeship') return '免运费';
    return '减' + money(cp.value) + '元';
  }

  /* ---------- 图片压缩（后台传图用） ---------- */
  function compressImage(file, maxW, quality) {
    maxW = maxW || 900; quality = quality || 0.82;
    return new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => {
        const im = new Image();
        im.onload = () => {
          const scale = Math.min(1, maxW / im.width);
          const w = Math.round(im.width * scale), h = Math.round(im.height * scale);
          const cv = document.createElement('canvas');
          cv.width = w; cv.height = h;
          const ctx = cv.getContext('2d');
          ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, w, h);
          ctx.drawImage(im, 0, 0, w, h);
          resolve(cv.toDataURL('image/jpeg', quality));
        };
        im.onerror = reject;
        im.src = fr.result;
      };
      fr.onerror = reject;
      fr.readAsDataURL(file);
    });
  }

  /* ---------- 从 URL 推断 GitHub 仓库 ---------- */
  function guessRepo() {
    const h = location.hostname;
    const m = h.match(/^([\w-]+)\.github\.io$/i);
    if (m) {
      const seg = location.pathname.split('/').filter(Boolean)[0] || (m[1] + '.github.io');
      return { owner: m[1], repo: decodeURIComponent(seg), branch: 'gh-pages' };
    }
    return { owner: '', repo: '', branch: 'gh-pages' };
  }

  function copyText(text) {
    if (navigator.clipboard && location.protocol !== 'file:') return navigator.clipboard.writeText(text);
    return new Promise(res => {
      const ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch (e) {}
      document.body.removeChild(ta); res();
    });
  }

  return { DEFAULT_SETTINGS, loadJSON, loadSettings, loadProducts, loadCoupons,
           money, yuan, esc, orderCode, toast, LS, calcCoupon, couponLabel,
           compressImage, guessRepo, copyText };
})();
