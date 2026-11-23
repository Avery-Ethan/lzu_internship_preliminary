#!/usr/bin/env node
/**
 * 校园好物市集 · 模拟接口服务（零依赖，不需要 npm install）
 *
 * 启动：node frontend/mock/server.mjs
 *       PORT=4000 node frontend/mock/server.mjs
 *
 * 说明：
 *  - 数据在内存里，重启即恢复初始状态（下单会扣库存，重启后复原；也可 POST /api/_reset 重置）。
 *  - 每个请求有 250~700ms 模拟网络延迟，方便观察加载态。
 *  - 金额单位统一是「分」（整数），前端展示时自己除以 100。
 *  - 支付是异步的：POST /api/payments 返回 processing，需轮询 GET /api/payments/:id 直到 status 变为 paid。
 *  - 想让接口失败：ERROR_RATE=1 node frontend/mock/server.mjs（对所有业务接口生效）
 */
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 3001);
const ERROR_RATE = Number(process.env.ERROR_RATE ?? 0);

const db = JSON.parse(readFileSync(join(__dirname, 'db.json'), 'utf8'));
const products = db.products.map((p) => ({ ...p }));

// 订单与商品来自 db.json，重启即恢复初始状态
const seedOrders = (db.orders || []).map((o) => ({ ...o }));
let productSeq = products.reduce((m, p) => Math.max(m, p.id), 0) + 1;
let orderSeq = seedOrders.reduce((m, o) => Math.max(m, o.id), 0) + 1;
let paymentSeq = 1;
const orders = seedOrders;
const payments = new Map();

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const rand = (min, max) => min + Math.floor(Math.random() * (max - min + 1));
// 分页参数容错：非法/缺失/非正数一律回退到默认值，避免 NaN 导致静默返回空列表
const toPositiveInt = (raw, fallback) => {
  const n = Number(raw);
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : fallback;
};
const now = () => new Date().toISOString();

function send(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Methods': 'GET, POST, PATCH, OPTIONS',
    'Content-Length': Buffer.byteLength(payload),
  });
  res.end(payload);
}
const ok = (res, data) => send(res, 200, { code: 0, message: 'ok', data });
const created = (res, data) => send(res, 201, { code: 0, message: 'ok', data });
const fail = (res, status, code, message) => send(res, status, { code, message, data: null });

function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (c) => {
      raw += c;
      if (raw.length > 1e6) reject(new Error('too large'));
    });
    req.on('end', () => {
      if (!raw) return resolve({});
      try { resolve(JSON.parse(raw)); } catch (e) { reject(e); }
    });
    req.on('error', reject);
  });
}

const CATEGORIES = db.categories;
const orderNo = (id) => 'SO' + new Date().toISOString().slice(0, 10).replace(/-/g, '') + String(id).padStart(4, '0');
const payNo = (id) => 'PAY' + new Date().toISOString().slice(0, 10).replace(/-/g, '') + String(id).padStart(4, '0');

const server = http.createServer(async (req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      'Access-Control-Allow-Methods': 'GET, POST, PATCH, OPTIONS',
    });
    return res.end();
  }

  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const path = url.pathname;
  const startedAt = Date.now();
  res.on('finish', () => {
    console.log(`${now()} ${req.method} ${path}${url.search} -> ${res.statusCode} (${Date.now() - startedAt}ms)`);
  });
  await sleep(rand(250, 700));

  try {
    // 调试用：把内存数据恢复成 db.json 的初始状态（不受故障注入影响）
    if (req.method === 'POST' && path === '/api/_reset') {
      const fresh = JSON.parse(readFileSync(join(__dirname, 'db.json'), 'utf8'));
      products.length = 0;
      products.push(...fresh.products.map((p) => ({ ...p })));
      orders.length = 0;
      orders.push(...(fresh.orders || []).map((o) => ({ ...o })));
      payments.clear();
      productSeq = products.reduce((m, p) => Math.max(m, p.id), 0) + 1;
      orderSeq = orders.reduce((m, o) => Math.max(m, o.id), 0) + 1;
      paymentSeq = 1;
      return ok(res, { products: products.length, orders: orders.length, payments: 0 });
    }

    // 故障注入：ERROR_RATE > 0 时对所有业务接口生效（_reset 除外）
    if (ERROR_RATE > 0 && Math.random() < ERROR_RATE) return fail(res, 503, 50300, '服务暂时不可用，请稍后重试');

    if (req.method === 'GET' && path === '/api/categories') return ok(res, CATEGORIES);

    // ---------- 商品 ----------
    if (req.method === 'GET' && path === '/api/products') {
      const keyword = (url.searchParams.get('keyword') || '').trim().toLowerCase();
      const status = url.searchParams.get('status') || '';
      const category = url.searchParams.get('category') || '';
      const page = toPositiveInt(url.searchParams.get('page'), 1);
      const pageSize = Math.min(50, toPositiveInt(url.searchParams.get('pageSize'), 50));

      let list = products.filter((p) => {
        const okKeyword = !keyword || p.title.toLowerCase().includes(keyword);
        const okStatus = !status || p.status === status;
        const okCategory = !category || p.category === category;
        return okKeyword && okStatus && okCategory;
      });
      const total = list.length;
      const items = list.slice((page - 1) * pageSize, page * pageSize);
      return ok(res, { total, page, pageSize, items });
    }

    const productDetail = path.match(/^\/api\/products\/(\d+)$/);
    if (req.method === 'GET' && productDetail) {
      const p = products.find((x) => x.id === Number(productDetail[1]));
      if (!p) return fail(res, 404, 40401, '商品不存在');
      return ok(res, p);
    }

    if (req.method === 'POST' && path === '/api/products') {
      const body = await readBody(req);
      const { title, price, stock, category, description } = body || {};
      // 表单拿到的值往往是字符串（如 "1999"），统一转数字后再校验；仍要求结果为整数
      const priceNum = Number(price);
      const stockNum = Number(stock);
      if (!title || typeof title !== 'string' || title.trim().length === 0 || title.trim().length > 50)
        return fail(res, 400, 40001, '标题需为 1~50 个字符');
      if (!Number.isInteger(priceNum) || priceNum <= 0) return fail(res, 400, 40001, '价格必须为正整数（单位：分）');
      if (!Number.isInteger(stockNum) || stockNum < 0 || stockNum > 999) return fail(res, 400, 40001, '库存需为 0~999 的整数');
      if (!CATEGORIES.includes(category)) return fail(res, 400, 40001, '分类不合法');
      if (description != null && String(description).length > 200) return fail(res, 400, 40001, '描述不能超过 200 字');

      const product = {
        id: productSeq++,
        title: title.trim(),
        price: priceNum,
        stock: stockNum,
        category,
        status: 'on',
        sellerName: '我',
        description: description || '',
      };
      products.push(product);
      return created(res, product);
    }

    const statusPath = path.match(/^\/api\/products\/(\d+)\/status$/);
    if (req.method === 'PATCH' && statusPath) {
      const body = await readBody(req);
      const p = products.find((x) => x.id === Number(statusPath[1]));
      if (!p) return fail(res, 404, 40401, '商品不存在');
      if (!['on', 'off'].includes(body.status)) return fail(res, 400, 40001, 'status 只能是 on 或 off');
      p.status = body.status;
      return ok(res, { id: p.id, status: p.status });
    }

    // ---------- 订单 ----------
    if (req.method === 'POST' && path === '/api/orders') {
      const body = await readBody(req);
      const { productId, quantity } = body || {};
      const qty = Number(quantity);
      if (!productId || !Number.isInteger(qty) || qty <= 0) return fail(res, 400, 40001, '购买数量必须是正整数');
      const p = products.find((x) => x.id === Number(productId));
      if (!p) return fail(res, 404, 40401, '商品不存在');
      if (p.status !== 'on') return fail(res, 409, 40902, '商品已下架');
      if (p.stock < qty) return fail(res, 409, 40901, '库存不足');
      p.stock -= qty;
      const order = {
        id: orderSeq++,
        orderNo: orderNo(orderSeq - 1),
        productId: p.id,
        productTitle: p.title,
        quantity: qty,
        unitPrice: p.price,
        totalAmount: p.price * qty,
        status: 'created',
        createdAt: now(),
        paidAt: null,
      };
      orders.push(order);
      return created(res, order);
    }

    if (req.method === 'GET' && path === '/api/orders') {
      const page = toPositiveInt(url.searchParams.get('page'), 1);
      const pageSize = Math.min(50, toPositiveInt(url.searchParams.get('pageSize'), 10));
      const list = [...orders].sort((a, b) => b.id - a.id);
      return ok(res, { total: list.length, page, pageSize, items: list.slice((page - 1) * pageSize, page * pageSize) });
    }

    const orderDetail = path.match(/^\/api\/orders\/(\d+)$/);
    if (req.method === 'GET' && orderDetail) {
      const o = orders.find((x) => x.id === Number(orderDetail[1]));
      if (!o) return fail(res, 404, 40401, '订单不存在');
      return ok(res, o);
    }

    // ---------- 支付 ----------
    if (req.method === 'POST' && path === '/api/payments') {
      const body = await readBody(req);
      const { orderId, method } = body || {};
      const o = orders.find((x) => x.id === Number(orderId));
      if (!o) return fail(res, 404, 40401, '订单不存在');
      if (o.status === 'paid') return fail(res, 409, 40903, '订单已支付，请勿重复支付');
      if (!['alipay', 'wechat'].includes(method)) return fail(res, 400, 40001, '支付方式只能是 alipay 或 wechat');

      const paymentId = payNo(paymentSeq++);
      payments.set(paymentId, { paymentId, orderId: o.id, amount: o.totalAmount, method, status: 'processing', createdAt: now(), startedAt: Date.now() });
      return ok(res, { paymentId, orderId: o.id, amount: o.totalAmount, status: 'processing' });
    }

    const payDetail = path.match(/^\/api\/payments\/([A-Za-z0-9]+)$/);
    if (req.method === 'GET' && payDetail) {
      const pay = payments.get(payDetail[1]);
      if (!pay) return fail(res, 404, 40401, '支付单不存在');
      // 创建后异步转为 paid，保留可观测的中间态
      if (pay.status === 'processing' && Date.now() - pay.startedAt >= 2500) {
        pay.status = 'paid';
        pay.paidAt = now();
        const o = orders.find((x) => x.id === pay.orderId);
        if (o) { o.status = 'paid'; o.paidAt = pay.paidAt; }
      }
      return ok(res, { paymentId: pay.paymentId, orderId: pay.orderId, amount: pay.amount, method: pay.method, status: pay.status, paidAt: pay.paidAt || null });
    }

    return fail(res, 404, 40400, '接口不存在');
  } catch (e) {
    console.error('[error]', e.message);
    // JSON 解析失败与真正的服务端异常分开报，避免误导学生
    if (e instanceof SyntaxError) return fail(res, 400, 40002, '请求体必须是合法 JSON');
    return fail(res, 500, 50000, '服务端处理出错：' + e.message);
  }
});

server.on('error', (e) => {
  if (e.code === 'EADDRINUSE') {
    console.error(`\n端口 ${PORT} 已被占用，mock 没启动。`);
    console.error(`换个端口重跑：PORT=4000 node frontend/mock/server.mjs`);
    console.error(`（前端请求地址也要跟着改成 http://127.0.0.1:4000）\n`);
    process.exit(1);
  }
  console.error('[server error]', e.message);
  process.exit(1);
});

server.listen(PORT, () => {
  console.log(`好物市集 mock 已启动: http://127.0.0.1:${PORT}`);
  console.log(`  商品 ${products.length} 个 / 分类 ${CATEGORIES.length} 个 / 故障注入 ${Math.round(ERROR_RATE * 100)}%`);
  console.log('  POST  /api/_reset         （调试用：恢复初始数据）');
  console.log('  GET   /api/products?keyword=&status=&category=&page=&pageSize=');
  console.log('  GET   /api/products/:id');
  console.log('  POST  /api/products');
  console.log('  PATCH /api/products/:id/status');
  console.log('  POST  /api/orders        { productId, quantity }');
  console.log('  GET   /api/orders  |  /api/orders/:id');
  console.log('  POST  /api/payments      { orderId, method }');
  console.log('  GET   /api/payments/:paymentId   （轮询直到 status=paid）');
});
