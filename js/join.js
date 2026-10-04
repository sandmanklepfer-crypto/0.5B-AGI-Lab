/* 商家入驻报名页逻辑（零服务器：邮件自动送达 + 一键复制兜底） */
(function () {
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));

  /* ============================================================
   *  只改这一块就行
   *  receiveEmail 填上你的邮箱，商家一提交就会自动发到你邮箱
   *  （用的是 FormSubmit，免注册；第一次会收到一封确认邮件，点一下确认即可）
   *  contactWechat / contactPhone 填了会显示给商家，方便他直接找你
   * ============================================================ */
  const CONFIG = {
    platform: '卤味小店 · 招商',
    contactWechat: '',                 // 例如 'axiang-luwei'  留空则尝试读 data/settings.json 里的微信
    contactPhone: '',                  // 例如 '138xxxxxxxx'
    receiveEmail: '',                  // 例如 'you@example.com'
    web3formsKey: ''                   // 不用 FormSubmit 的话，填 web3forms 的 access key
  };

  const CATS = ['卤味熟食', '小吃快餐', '烘焙甜品', '水果生鲜', '奶茶饮品', '面点主食', '其他'];
  const DELIVER = ['到店自提', '自己配送', '找跑腿', '堂食'];
  const PAY = ['微信 / 支付宝收款码', '想开通微信在线支付', '还没有收款方式，需要帮忙'];

  let ref = '';
  const t0 = Date.now();

  const qs = n => (new URLSearchParams(location.search).get(n) || '').trim();

  /* ---------------- 推荐人（团长）归因 ---------------- */
  function initRef() {
    const r = (qs('ref') || qs('tg') || '').slice(0, 40);
    if (r) LH.LS.set('lh_join_ref', r);
    ref = r || LH.LS.get('lh_join_ref', '') || '';
    if (ref) {
      $('#refBar').classList.remove('hidden');
      $('#refWho').textContent = ref;
      $('#f_ref').value = ref;
    }
  }

  /* ---------------- 渲染表单选项 ---------------- */
  function fillOptions() {
    $('#f_category').innerHTML = '<option value="">请选择</option>' +
      CATS.map(c => '<option>' + LH.esc(c) + '</option>').join('');
    $('#f_delivery').innerHTML = DELIVER.map(d =>
      '<label class="opt"><input type="checkbox" value="' + LH.esc(d) + '"> ' + LH.esc(d) + '</label>').join('');
    $('#f_pay').innerHTML = PAY.map((p, i) =>
      '<label class="opt"><input type="radio" name="pay" value="' + LH.esc(p) + '"' + (i === 0 ? '' : '') + '> ' + LH.esc(p) + '</label>').join('');
    $('#f_ref').value = ref;
  }

  /* ---------------- 平台信息（读 settings.json 兜底） ---------------- */
  async function loadPlatform() {
    let s = {};
    try { s = await LH.loadSettings(); } catch (e) { /* ignore */ }
    const name = s.shopName ? (s.shopName + ' · 招商') : CONFIG.platform;
    const wx = CONFIG.contactWechat || s.wechat || '';
    const ph = CONFIG.contactPhone || s.phone || '';
    $('#platName').textContent = name;
    document.title = '商家入驻报名 · ' + (s.shopName || '卤味小店');

    const lines = [];
    if (wx) lines.push('微信：' + wx);
    if (ph) lines.push('电话：' + ph);
    const html = lines.length
      ? '有问题直接找我们：<br>' + lines.map(LH.esc).join('<br>')
      : '<span style="color:#b06a00">（平台还没填联系方式，先点下面"复制报名信息"发给邀请你的人即可）</span>';
    $('#contactBox').innerHTML = html;
    $('#contactBox2').innerHTML = html;
  }

  /* ---------------- 收集 ---------------- */
  function collect() {
    return {
      shopName: $('#f_shopName').value.trim(),
      category: $('#f_category').value,
      slogan: $('#f_slogan').value.trim(),
      contact: $('#f_contact').value.trim(),
      phone: $('#f_phone').value.trim(),
      wechat: $('#f_wechat').value.trim(),
      address: $('#f_address').value.trim(),
      hours: $('#f_hours').value.trim(),
      delivery: $$('#f_delivery input:checked').map(i => i.value),
      pay: ($$('#f_pay input:checked')[0] || {}).value || '',
      slug: $('#f_slug').value.trim().toLowerCase(),
      note: $('#f_note').value.trim(),
      ref: ref,
      ts: new Date().toLocaleString('zh-CN')
    };
  }

  function validate(d) {
    if (!d.shopName) return '请填写店名';
    if (!d.contact) return '请填写联系人';
    if (!/^(1\d{10}|0\d{2,3}-?\d{7,8})$/.test(d.phone.replace(/\s|-/g, ''))) return '请填写正确的手机号';
    if (!d.address) return '请填写店铺地址';
    if (d.slug && !/^[a-z0-9-]{3,30}$/.test(d.slug)) return '网址名只能用 3~30 位的英文字母、数字或短横线';
    if (!$('#f_agree').checked) return '请勾选最下面的承诺';
    if (Date.now() - t0 < 2500) return '提交太快了，稍等一下再点';
    if ($('#f_honey').value) return '提交失败，请重试';   // 机器人蜜罐
    return '';
  }

  function toText(d) {
    return [
      '【商家入驻报名】',
      '推荐人：' + (d.ref || '（无）'),
      '店名：' + d.shopName,
      '品类：' + (d.category || '-'),
      '一句话介绍：' + (d.slogan || '-'),
      '联系人：' + d.contact,
      '手机：' + d.phone,
      '微信：' + (d.wechat || '-'),
      '地址：' + d.address,
      '营业时间：' + (d.hours || '-'),
      '配送：' + (d.delivery.length ? d.delivery.join('、') : '-'),
      '收款方式：' + (d.pay || '-'),
      '想要的网址名：' + (d.slug || '-'),
      '备注：' + (d.note || '-'),
      '提交时间：' + d.ts
    ].join('\n');
  }

  /* ---------------- 送达：邮件 / 复制 ---------------- */
  async function sendMail(d) {
    const text = toText(d);
    if (CONFIG.web3formsKey) {
      const r = await fetch('https://api.web3forms.com/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({
          access_key: CONFIG.web3formsKey,
          subject: '【商家报名】' + d.shopName + (d.ref ? '（团长：' + d.ref + '）' : ''),
          from_name: '商家入驻报名',
          '报名详情': text
        })
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return 'web3forms';
    }
    if (CONFIG.receiveEmail) {
      const r = await fetch('https://formsubmit.co/ajax/' + encodeURIComponent(CONFIG.receiveEmail), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({
          _subject: '【商家报名】' + d.shopName + (d.ref ? '（团长：' + d.ref + '）' : ''),
          _template: 'table',
          _captcha: 'false',
          报名详情: text,
          店名: d.shopName,
          推荐人: d.ref || '（无）',
          联系人: d.contact,
          手机: d.phone,
          微信: d.wechat || '',
          地址: d.address,
          想要的网址名: d.slug || ''
        })
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j.success === false) throw new Error((j && j.message) || ('HTTP ' + r.status));
      return 'formsubmit';
    }
    return '';
  }

  /* ---------------- 提交 ---------------- */
  async function submit(e) {
    e.preventDefault();
    const btn = $('#btnSubmit');
    const d = collect();
    const err = validate(d);
    if (err) { LH.toast(err); return; }

    LH.LS.set('lh_join_last', d);

    btn.disabled = true;
    const old = btn.textContent;
    btn.textContent = '提交中…';
    setStatus('info', '正在提交…');

    let mode = '';
    try { mode = await sendMail(d); }
    catch (ex) { /* 邮件失败也照样给复制兜底 */ console.warn(ex); }

    btn.disabled = false;
    btn.textContent = old;

    // 不管邮件成不成，都保存一份，并展示可复制的文本
    $('#doneWrap').classList.remove('hidden');
    $('#doneText').textContent = toText(d);
    if (mode) {
      setStatus('ok', '✅ 提交成功！我们收到后会尽快联系你。');
      $('#doneTip').innerHTML = '已自动送达平台。也可以再复制一份，发给你认识的招商负责人，双保险。';
    } else {
      setStatus('warn', '报名信息已生成，请点下面按钮复制，发给邀请你的人。');
      $('#doneTip').innerHTML = '平台还没配置自动收件邮箱，所以要麻烦你手动发一下 👇';
    }
    $('#doneWrap').scrollIntoView({ behavior: 'smooth', block: 'center' });
    $('#f_honey').value = '';
  }

  function setStatus(kind, text) {
    const el = $('#status');
    el.className = 'status ' + kind;
    el.textContent = text;
  }

  /* ---------------- 启动 ---------------- */
  function boot() {
    fillOptions();
    initRef();
    loadPlatform();
    $('#joinForm').addEventListener('submit', submit);
    $('#btnCopy').onclick = async () => {
      await LH.copyText($('#doneText').textContent);
      LH.toast('已复制，发给邀请你的人就行 ✅');
    };
    $('#btnReset').onclick = () => {
      $('#f_shopName').value = ''; $('#f_slogan').value = ''; $('#f_note').value = '';
      $('#doneWrap').classList.add('hidden');
      setStatus('info', '可以再填一份');
    };
    // 回填上次填过的（防止刷新丢数据）
    const last = LH.LS.get('lh_join_last', null);
    if (last) {
      $('#f_shopName').value = last.shopName || '';
      $('#f_slogan').value = last.slogan || '';
      $('#f_note').value = last.note || '';
    }
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
