'use strict';
/*
 * 微信支付 v3 · Native 扫码支付（零依赖，只用 Node 内置 crypto / https）
 *
 * 覆盖：
 *   1) 商户私钥签名 → Authorization 头
 *   2) 下单   POST /v3/pay/transactions/native
 *   3) 查单   GET  /v3/pay/transactions/out-trade-no/{no}
 *   4) 关单   POST /v3/pay/transactions/out-trade-no/{no}/close
 *   5) 回调报文验签（平台证书 / 微信支付公钥）+ AES-256-GCM 解密
 *
 * 说明：本项目用微信支付「公钥模式」验签——在商户平台下载「微信支付公钥」，
 *      文件名形如 pub_key.pem，配合 pub_key_id。这样比定期下载平台证书更省事。
 */
const crypto = require('crypto');
const https = require('https');
const fs = require('fs');

const HOST = 'api.mch.weixin.qq.com';

class WxPay {
  constructor(opts) {
    this.mchid = opts.mchid;
    this.appid = opts.appid;
    this.serialNo = opts.serialNo;          // 商户证书序列号
    this.privateKey = opts.privateKey;      // 商户 API 私钥（PEM 文本）
    this.apiV3Key = opts.apiV3Key;          // APIv3 密钥（32 位）
    this.publicKey = opts.publicKey || '';  // 微信支付公钥 PEM（验签，公钥模式）
    this.publicKeyId = opts.publicKeyId || ''; // 微信支付公钥 ID（形如 PUB_KEY_ID_xxx）
  }

  /* ---------------- 1. 商户请求签名 ---------------- */
  _sign(method, urlPath, body) {
    const ts = Math.floor(Date.now() / 1000).toString();
    const nonce = crypto.randomBytes(16).toString('hex');
    const message = `${method}\n${urlPath}\n${ts}\n${nonce}\n${body}\n`;
    const sig = crypto.createSign('RSA-SHA256').update(message).sign(this.privateKey, 'base64');
    const auth =
      `WECHATPAY2-SHA256-RSA2048 mchid="${this.mchid}",` +
      `nonce_str="${nonce}",timestamp="${ts}",` +
      `serial_no="${this.serialNo}",signature="${sig}"`;
    return auth;
  }

  _request(method, urlPath, body) {
    const raw = body ? JSON.stringify(body) : '';
    const auth = this._sign(method, urlPath, raw);
    const headers = {
      'Authorization': auth,
      'Accept': 'application/json',
      'User-Agent': 'luhuo-pay/1.0 (nodejs)',
    };
    if (raw) {
      headers['Content-Type'] = 'application/json';
      headers['Content-Length'] = Buffer.byteLength(raw);
    }
    return new Promise((resolve, reject) => {
      const req = https.request({ host: HOST, method, path: urlPath, headers }, res => {
        let buf = '';
        res.on('data', c => buf += c);
        res.on('end', () => {
          let data = null;
          try { data = buf ? JSON.parse(buf) : null; } catch (e) { data = { raw: buf }; }
          if (res.statusCode >= 200 && res.statusCode < 300) resolve(data);
          else {
            const err = new Error((data && (data.message || data.code)) || ('HTTP ' + res.statusCode));
            err.status = res.statusCode; err.data = data;
            reject(err);
          }
        });
      });
      req.on('error', reject);
      if (raw) req.write(raw);
      req.end();
    });
  }

  /* ---------------- 2. Native 下单 ---------------- */
  async nativeTransaction({ description, outTradeNo, amountFen, notifyUrl, attach, timeExpire }) {
    const body = {
      appid: this.appid,
      mchid: this.mchid,
      description,
      out_trade_no: outTradeNo,
      notify_url: notifyUrl,
      amount: { total: amountFen, currency: 'CNY' },
    };
    if (attach) body.attach = attach;
    if (timeExpire) body.time_expire = timeExpire;   // RFC3339
    const r = await this._request('POST', '/v3/pay/transactions/native', body);
    return r; // { code_url }
  }

  /* ---------------- 3. 查单 ---------------- */
  async queryByOutTradeNo(outTradeNo) {
    const p = `/v3/pay/transactions/out-trade-no/${encodeURIComponent(outTradeNo)}?mchid=${this.mchid}`;
    return this._request('GET', p);
  }

  /* ---------------- 4. 关单 ---------------- */
  async close(outTradeNo) {
    const p = `/v3/pay/transactions/out-trade-no/${encodeURIComponent(outTradeNo)}/close`;
    return this._request('POST', p, { mchid: this.mchid });
  }

  /* ---------------- 5. 回调验签 ---------------- */
  /**
   * @param headers 原始请求头（大小写不敏感）
   * @param rawBody 原始报文字符串（务必是没被 JSON.parse 过的原始 body）
   */
  verifyNotify(headers, rawBody) {
    const h = k => (headers[k] || headers[k.toLowerCase()] || '');
    const ts = h('Wechatpay-Timestamp');
    const nonce = h('Wechatpay-Nonce');
    const sig = h('Wechatpay-Signature');
    const serial = h('Wechatpay-Serial');
    if (!ts || !nonce || !sig) throw new Error('回调缺少签名头');

    const message = `${ts}\n${nonce}\n${rawBody}\n`;

    // 1) 时间戳防重放（5 分钟）
    if (Math.abs(Date.now() / 1000 - Number(ts)) > 300) throw new Error('回调时间戳超出 5 分钟');

    // 2) 验签：支持「微信支付公钥」和「平台证书」两种 PEM
    const key = this.publicKey || this.platformCert;
    if (!key) throw new Error('未配置验签公钥（WXPAY_PUBLIC_KEY_PATH 或 WXPAY_PLATFORM_CERT_PATH）');
    const ok = crypto.createVerify('RSA-SHA256').update(message).verify(key, sig, 'base64');
    if (!ok) throw new Error('回调验签失败');

    // 3) 解密 resource
    const body = JSON.parse(rawBody);
    const res = body.resource;
    if (!res) return { event: body, decrypted: null };
    const decrypted = this.decryptResource(res);
    return { event: body, decrypted, serial };
  }

  decryptResource(res) {
    if (res.algorithm !== 'AEAD_AES_256_GCM') throw new Error('不支持的加密算法 ' + res.algorithm);
    const key = Buffer.from(this.apiV3Key, 'utf8');
    const iv = Buffer.from(res.nonce, 'utf8');
    const data = Buffer.from(res.ciphertext, 'base64');
    const tag = data.slice(data.length - 16);
    const enc = data.slice(0, data.length - 16);
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
    decipher.setAuthTag(tag);
    if (res.associated_data) decipher.setAAD(Buffer.from(res.associated_data, 'utf8'));
    const plain = Buffer.concat([decipher.update(enc), decipher.final()]).toString('utf8');
    return JSON.parse(plain);
  }
}

function fromConfig(cfg) {
  // 公钥优先取环境变量内容，其次文件
  let publicKey = '';
  if (cfg.publicKeyInline) publicKey = cfg.publicKeyInline;
  else if (cfg.publicKeyPathResolved && fs.existsSync(cfg.publicKeyPathResolved)) {
    publicKey = fs.readFileSync(cfg.publicKeyPathResolved, 'utf8');
  }
  const w = new WxPay({
    mchid: cfg.mchid, appid: cfg.appid, serialNo: cfg.serialNo,
    privateKey: cfg.privateKey, apiV3Key: cfg.apiV3Key,
    publicKey, publicKeyId: cfg.publicKeyId,
  });
  // 兼容：没配公钥时，退而使用平台证书验签
  if (!publicKey) {
    if (cfg.platformCertInline) w.platformCert = cfg.platformCertInline;
    else if (cfg.platformCertPathResolved && fs.existsSync(cfg.platformCertPathResolved)) {
      w.platformCert = fs.readFileSync(cfg.platformCertPathResolved, 'utf8');
    }
  }
  return w;
}

module.exports = { WxPay, fromConfig };
