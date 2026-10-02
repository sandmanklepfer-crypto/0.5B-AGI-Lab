'use strict';
/*
 * friends.html / friends.js 结构自检（不联网）
 *
 * 行为测试在 friends-live.test.js（真实 broker 端到端），
 * 这里只保证「页面接线」没错：脚本加载顺序、元素 id、引用完整、没有旧的 ghchat 依赖。
 *
 * 运行：node server/test/friends-dom.test.js
 */
const fs = require('fs');
const path = require('path');

let pass = 0, fail = 0;
const ok = (n, c, extra) => {
  if (c) { pass++; console.log('  ✅ ' + n); }
  else { fail++; console.log('  ❌ ' + n + (extra !== undefined ? '  → ' + JSON.stringify(extra) : '')); }
};

const root = path.join(__dirname, '..', '..');
const html = fs.readFileSync(path.join(root, 'friends.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'js', 'friends.js'), 'utf8');
const mqtt = fs.readFileSync(path.join(root, 'js', 'mqtt.js'), 'utf8');

console.log('\n== 1. 脚本加载 ==');
const scripts = [...html.matchAll(/<script src="([^"]+)"><\/script>/g)].map(m => m[1]);
ok('只加载两个脚本', scripts.length === 2, scripts);
ok('先 mqtt.js 后 friends.js（顺序不能反）',
  scripts[0].includes('mqtt') && scripts[1].includes('friends'), scripts);
ok('mqtt.js 是本地文件（不依赖 CDN）', scripts[0].startsWith('js/'), scripts[0]);

console.log('\n== 2. 不再依赖旧的 ghchat 方案 ==');
ok('friends.js 不引用 GHChat', !/GHChat/.test(js));
ok('friends.js 不引用 ghchat', !/ghchat/.test(js));
ok('friends.js 不要求任何令牌（注释里的「免 Token」不算）',
  !/(localStorage|getItem).{0,40}token/i.test(js) && !/Authorization/.test(js));
ok('friends.js 用 MiniMqtt', /MiniMqtt/.test(js));

console.log('\n== 3. 元素 id 完整 ==');
const ids = new Set([...html.matchAll(/id="([\w-]+)"/g)].map(m => m[1]));
const used = new Set([...js.matchAll(/\$\('#([\w-]+)'\)/g)].map(m => m[1]));
const dynamic = new Set(['btnRetry', 'roomCopy', 'roomNew', 'onlineRow', 'dmBar', 'dmBlock', 'dmBack']);
const missing = [...used].filter(u => !ids.has(u) && !dynamic.has(u));
ok('JS 引用的 id 都存在', missing.length === 0, missing);
ok('有输入框', ids.has('input') && ids.has('btnSend'));
ok('有发图按钮', ids.has('btnPic') && ids.has('filePick'));
ok('有房间设置', ids.has('topRoom') && ids.has('sRoom') && ids.has('roomIn'));
ok('有资料设置', ids.has('topMe') && ids.has('sMe') && ids.has('nickIn'));
ok('有连接状态显示', ids.has('liveTxt') && ids.has('liveDot'));

console.log('\n== 4. 默认不弹面板（上次的 bug）==');
const popped = [...html.matchAll(/class="(?:mask|sheet)( )?on"/g)].length;
ok('没有默认弹出的面板', popped === 0, popped);

console.log('\n== 5. MQTT 客户端要点 ==');
ok('内置 broker 列表', /BROKERS\s*=/.test(mqtt) && mqtt.split('wss://').length >= 3);
ok('用 mqtt 子协议（broker 会回显，浏览器才能连）', /'mqtt'/.test(mqtt));
ok('没有手工套 WS 帧（否则双层帧会被拒）',
  !/function frame\(/.test(mqtt), 'frame() 应已删除');
ok('onmessage 直接当 MQTT 报文处理（浏览器已剥帧）',
  /onmessage\s*=\s*e\s*=>\s*onMqtt/.test(mqtt));
ok('有自动重连', /scheduleRetry/.test(mqtt));
ok('有心跳保活', /0xC0/.test(mqtt));

console.log('\n== 6. 交友必备的安全措施 ==');
ok('有敏感词拦截', /BAD\s*=\s*\[/.test(js) && /加微信/.test(js));
ok('拦链接', /https\?:/.test(js));
ok('拦长串数字（防联系方式）', /\\d\{7,\}/.test(js));
ok('有拉黑', /blocked/.test(js) && /dmBlock/.test(js));
ok('有安全提示（页面里）', /任何要钱的都是骗子/.test(html) && /别透露/.test(html));
ok('说明了换设备看不到历史', /换设备看不到/.test(html));
ok('图片会压缩后再发', /compress/.test(js) && /IMG_MAX_KB/.test(js));
ok('房间隔离（不同房间看不到）', /zhz\/chat\//.test(js));

console.log('\n== 7. 无服务器验证 ==');
ok('没有任何后端 API 调用', !/fetch\(/.test(js));
ok('没有 API 地址配置', !/apiBase/.test(js));

console.log(`\n===== 结果：${pass} 通过 / ${fail} 失败 =====\n`);
process.exit(fail ? 1 : 0);
