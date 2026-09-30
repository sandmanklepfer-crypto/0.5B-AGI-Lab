'use strict';
/* 配置读取：优先环境变量，其次 .env 文件，再次 config.json
 * 零依赖实现，不需要 npm install
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const SHOP_ROOT = path.resolve(ROOT, '..');      // 卤味网页根目录（luhuo/）

function parseEnvFile(p) {
  const out = {};
  if (!fs.existsSync(p)) return out;
  for (const raw of fs.readFileSync(p, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const i = line.indexOf('=');
    if (i < 0) continue;
    const k = line.slice(0, i).trim();
    let v = line.slice(i + 1).trim();
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
    out[k] = v;
  }
  return out;
}

function readJson(p, fallback) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return fallback; }
}

const envFile = parseEnvFile(path.join(ROOT, '.env'));
const jsonCfg = readJson(path.join(ROOT, 'config.json'), {});

function pick(key, def) {
  if (process.env[key] !== undefined && process.env[key] !== '') return process.env[key];
  if (envFile[key] !== undefined && envFile[key] !== '') return envFile[key];
  if (jsonCfg[key] !== undefined && jsonCfg[key] !== '') return jsonCfg[key];
  return def;
}

const cfg = {
  port: Number(pick('PORT', 8787)),
  publicBaseUrl: String(pick('PUBLIC_BASE_URL', '')).replace(/\/+$/, ''),   // 必须公网 HTTPS，用于回调
  adminToken: String(pick('ADMIN_TOKEN', 'change-me')),

  // 微信支付 v3
  mchid: String(pick('WXPAY_MCHID', '')),
  appid: String(pick('WXPAY_APPID', '')),
  serialNo: String(pick('WXPAY_SERIAL_NO', '')),
  apiV3Key: String(pick('WXPAY_APIV3_KEY', '')),
  privateKeyPath: String(pick('WXPAY_PRIVATE_KEY_PATH', path.join(ROOT, 'cert', 'apiclient_key.pem'))),
  notifyPath: String(pick('WXPAY_NOTIFY_PATH', '/api/pay/notify')),

  // 验签用的微信支付公钥（推荐）或平台证书
  publicKeyPath: String(pick('WXPAY_PUBLIC_KEY_PATH', path.join(ROOT, 'cert', 'pub_key.pem'))),
  publicKeyId: String(pick('WXPAY_PUBLIC_KEY_ID', '')),
  platformCertPath: String(pick('WXPAY_PLATFORM_CERT_PATH', path.join(ROOT, 'cert', 'platform_cert.pem'))),

  // 商家通知（付款成功后推给老板）
  merchantWebhook: String(pick('MERCHANT_WEBHOOK', '')),

  // ---------- 订单存储 ----------
  // local  = 服务器本地文件（自有服务器 / 有持久盘）
  // github = 写进你的 GitHub 仓库（免费 PaaS 磁盘会清空时用它）
  storage: String(pick('STORAGE', 'local')).toLowerCase(),
  ghToken: String(pick('GH_TOKEN', '')),
  ghOwner: String(pick('GH_OWNER', '')),
  ghRepo: String(pick('GH_REPO', '')),
  ghBranch: String(pick('GH_BRANCH', 'main')),
  ghFile: String(pick('GH_FILE', 'server-orders/orders.json')),

  // 免真实商户号的演示模式
  mock: String(pick('MOCK', '')).toLowerCase() === '1' || String(pick('MOCK', '')).toLowerCase() === 'true',

  ROOT,
  SHOP_ROOT,
};

/* 证书来源：优先环境变量里的内容（免费 PaaS 没法传文件），其次文件路径 */
function loadPem(pemValue, filePath, label) {
  const inline = String(pemValue || '').replace(/\\n/g, '\n').trim();
  if (inline) {
    if (!/-----BEGIN [A-Z ]+-----/.test(inline)) {
      console.warn(`[config] ${label} 环境变量内容不像 PEM（缺少 -----BEGIN----- 头），已忽略`);
    } else {
      console.log(`[config] ${label}：来自环境变量`);
      return inline;
    }
  }
  if (filePath && fs.existsSync(filePath)) {
    console.log(`[config] ${label}：来自文件 ${filePath}`);
    return fs.readFileSync(filePath, 'utf8');
  }
  return '';
}

cfg.privateKey = loadPem(pick('WXPAY_PRIVATE_KEY_PEM', ''), cfg.privateKeyPath, '商户私钥');
cfg.publicKeyInline = loadPem(pick('WXPAY_PUBLIC_KEY_PEM', ''), cfg.publicKeyPath, '微信支付公钥');
cfg.platformCertInline = loadPem(pick('WXPAY_PLATFORM_CERT_PEM', ''), cfg.platformCertPath, '平台证书');
cfg.publicKeyPathResolved = cfg.publicKeyPath;
cfg.platformCertPathResolved = cfg.platformCertPath;
cfg.ordersFile = String(pick('ORDERS_FILE', path.join(ROOT, 'data', 'orders.json')));

cfg.mock = cfg.mock || !(cfg.mchid && cfg.privateKey && cfg.serialNo && cfg.apiV3Key);

cfg.notifyUrl = (cfg.publicBaseUrl || '') + cfg.notifyPath;

function summary() {
  return {
    mode: cfg.mock ? 'MOCK（演示模式：不接真实微信支付）' : 'LIVE（真实微信支付 v3）',
    port: cfg.port,
    publicBaseUrl: cfg.publicBaseUrl || '(未设置，回调不可用)',
    notifyUrl: cfg.notifyUrl,
    mchid: cfg.mchid ? cfg.mchid.replace(/^(.).*(.)$/, '$1****$2') : '(未配置)',
    hasPrivateKey: !!cfg.privateKey,
    apiV3Key: cfg.apiV3Key ? '已配置' : '(未配置)',
    storage: cfg.storage === 'github' && cfg.ghToken && cfg.ghRepo
      ? ('GitHub ' + cfg.ghOwner + '/' + cfg.ghRepo + ':' + cfg.ghFile)
      : '本地文件',
  };
}

module.exports = { cfg, summary, SHOP_ROOT, ROOT };
