#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校园优选 · 电商后端服务（单文件版）。

商品、订单、支付、评价四组接口，数据存放在脚本同目录的 sut.db 中，
启动时删除重建并写入种子数据。仅依赖 Python 3.10+ 标准库。
"""

import argparse
import json
import os
import sqlite3
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sut.db")

JSON_TYPE = "application/json; charset=utf-8"
HTML_TYPE = "text/html; charset=utf-8"
TOKEN_PREFIX = "tk_"
TOKEN_TTL_SECONDS = 12 * 60 * 60
STOCK_WINDOW_SECONDS = 0.15
DEFAULT_PAGE_SIZE = 10
DEFAULT_ADDRESS = "兰州市城关区天水南路222号"
CATEGORIES = ("数码", "图书", "服饰", "食品", "文具")

STARTED_AT = time.time()
LOG_LOCK = threading.Lock()

# ---- 日志 ----

def log_line(tag, message):
    """统一格式的控制台日志：时间 [标签] 内容。"""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "%s [%s] %s" % (stamp, tag, message)
    with LOG_LOCK:
        print(line, flush=True)

def iso_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ---- 数据库 ----

SCHEMA_SQL = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'user',
    real_name TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
    price INTEGER NOT NULL, stock INTEGER NOT NULL DEFAULT 0,
    category TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'on', seller_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT, order_no TEXT NOT NULL DEFAULT '',
    user_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
    product_title TEXT NOT NULL, quantity INTEGER NOT NULL,
    unit_price INTEGER NOT NULL, total_amount NUMERIC NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    receiver_phone TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, paid_at TEXT
);

CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, payment_no TEXT NOT NULL DEFAULT '',
    order_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
    method TEXT NOT NULL, amount NUMERIC NOT NULL,
    status TEXT NOT NULL DEFAULT 'paid', created_at TEXT NOT NULL,
    paid_at TEXT
);

CREATE TABLE product_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL, content TEXT NOT NULL,
    rating INTEGER NOT NULL, created_at TEXT NOT NULL
);

CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_orders_user ON orders(user_id);
CREATE INDEX idx_payments_order ON payments(order_id);
CREATE INDEX idx_reviews_product ON product_reviews(product_id);
"""

SEED_USERS = [
    ("admin", "Admin@123", "admin", "系统管理员", "13800138001", "兰州市城关区天水南路222号"),
    ("alice", "Alice@123", "user", "张爱丽", "13800138002", "兰州市城关区天水南路222号"),
    ("bob", "Bob@123", "user", "李波", "13800138003", "兰州市安宁区安宁西路88号"),
    ("carol", "Carol@123", "user", "王卡罗", "13800138004", "兰州市七里河区西津东路45号"),
    ("dave", "Dave@123", "user", "赵大伟", "13800138005", "兰州市榆中县夏官营镇1号"),
]

# title, price, stock, category, description, status, seller_id
SEED_PRODUCTS = [
    ("无线蓝牙耳机", 1990, 12, "数码", "半入耳设计，蓝牙 5.3，单次续航 6 小时。", "on", 1),
    ("机械键盘 87 键", 12900, 8, "数码", "青轴热插拔，支持三模连接与全键无冲。", "on", 2),
    ("《金字塔原理》精装版", 4999, 20, "图书", "麦肯锡经典表达方法论，附思维导图册。", "on", 3),
    ("《人类简史》十周年纪念版", 3990, 15, "图书", "从认知革命讲到人工智能，新增作者后记。", "on", 1),
    ("轻薄防晒外套", 8990, 1, "服饰", "UPF50+ 防晒面料，可收纳进随身小包。", "on", 2),
    ("纯棉基础款短袖", 3590, 30, "服饰", "260g 重磅纯棉，圆领不易变形。", "on", 3),
    ("云南小粒咖啡豆 500g", 6880, 9, "食品", "中度烘焙，坚果与焦糖风味，现烘现发。", "off", 1),
    ("手工黑糖麻花礼盒", 2980, 25, "食品", "独立小包装，酥脆不粘牙，适合办公室分享。", "on", 2),
    ("中性笔 0.5mm 十二支装", 1290, 50, "文具", "速干墨水，考试刷题不断墨。", "on", 3),
    ("A5 硬壳笔记本", 2350, 40, "文具", "100g 道林纸，可 180 度平摊。", "on", 1),
    ("便携充电宝 10000mAh", 9900, 6, "数码", "自带双线，支持 22.5W 快充。", "on", 2),
    ("桌面收纳盒", 3290, 22, "文具", "分层抽屉设计，可叠放。", "on", 3),
]

# order_no, user_id, product_id, product_title, quantity, unit_price, total_amount,
# status, receiver_phone, address, created_at, paid_at
SEED_ORDERS = [
    ("SO202609180001", 2, 1, "无线蓝牙耳机", 2, 1990, 3980, "created", "13800138002", "兰州市城关区天水南路222号", "2026-09-18T09:20:00Z", None),
    ("SO202609200002", 3, 2, "机械键盘 87 键", 1, 12900, 12900, "paid", "13800138003", "兰州市安宁区安宁西路88号", "2026-09-20T13:05:00Z", "2026-09-20T13:06:12Z"),
]

SEED_PAYMENTS = [
    ("PAY202609200001", 2, 3, "alipay", 12900, "paid", "2026-09-20T13:05:40Z", "2026-09-20T13:06:12Z"),
]

SEED_PRODUCT_REVIEWS = [
    (1, 2, "耳机音质比预期好，通勤戴着也稳，续航差不多两天。", 5, "2026-09-19T10:22:00Z"),
    (1, 3, "连接偶尔会断一下，整体还行，这个价位可以接受。", 4, "2026-09-22T16:40:00Z"),
]

def get_conn():
    """打开一个数据库连接，调用方负责关闭。"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

def init_database():
    """删除旧库文件，重新建表并写入种子数据。"""
    for suffix in ("", "-wal", "-shm"):
        path = DB_PATH + suffix
        if os.path.exists(path):
            os.remove(path)

    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA_SQL)
        conn.executemany(
            "INSERT INTO users (username, password, role, real_name, phone, address, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [item + ("2026-09-01T08:00:00Z",) for item in SEED_USERS],
        )
        conn.executemany(
            "INSERT INTO products (title, price, stock, category, description, status,"
            " seller_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [item + ("2026-09-%02dT09:00:00Z" % (index + 1),)
             for index, item in enumerate(SEED_PRODUCTS)],
        )
        conn.executemany(
            "INSERT INTO orders (order_no, user_id, product_id, product_title, quantity,"
            " unit_price, total_amount, status, receiver_phone, address, created_at, paid_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            SEED_ORDERS,
        )
        conn.executemany(
            "INSERT INTO payments (payment_no, order_id, user_id, method, amount, status,"
            " created_at, paid_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            SEED_PAYMENTS,
        )
        conn.executemany(
            "INSERT INTO product_reviews (product_id, user_id, content, rating, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            SEED_PRODUCT_REVIEWS,
        )
        conn.commit()
    finally:
        conn.close()
    log_line("db", "数据库已重建: %s" % DB_PATH)

# ---- 数据转换 ----

def user_to_dict(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "realName": row["real_name"],
        "phone": row["phone"],
        "role": row["role"],
        "createdAt": row["created_at"],
    }

def product_brief(row):
    return {
        "id": row["id"], "title": row["title"], "price": row["price"],
        "stock": row["stock"], "category": row["category"], "status": row["status"],
        "sellerId": row["seller_id"], "sellerPhone": row["seller_phone"],
        "createdAt": row["created_at"],
    }

def product_detail(row):
    data = product_brief(row)
    data["description"] = row["description"]
    return data

def order_to_dict(row):
    return {
        "id": row["id"], "orderNo": row["order_no"],
        "userId": row["user_id"], "userName": row["user_name"],
        "productId": row["product_id"], "productTitle": row["product_title"],
        "quantity": row["quantity"], "unitPrice": row["unit_price"],
        "totalAmount": row["total_amount"], "status": row["status"],
        "receiverPhone": row["receiver_phone"], "address": row["address"],
        "createdAt": row["created_at"], "paidAt": row["paid_at"],
    }

def admin_order_item(row):
    return {
        "id": row["id"], "orderNo": row["order_no"],
        "userId": row["user_id"], "userName": row["user_name"],
        "productTitle": row["product_title"], "quantity": row["quantity"],
        "totalAmount": row["total_amount"], "status": row["status"],
        "receiverPhone": row["receiver_phone"], "address": row["address"],
        "createdAt": row["created_at"],
    }

def ok_body(data):
    return {"code": 0, "message": "ok", "data": data}

def error_body(code, message):
    return {"code": code, "message": message, "data": None}

# ---- 鉴权 ----

def parse_token(auth_header):
    """从 Authorization 头里解析出用户 id，token 形如 tk_2。"""
    if not auth_header:
        return None
    value = auth_header.strip()
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    if not value.startswith(TOKEN_PREFIX):
        return None
    raw = value[len(TOKEN_PREFIX):]
    if not raw.isdigit():
        return None
    return int(raw)

def current_user(auth_header):
    """校验 token 并返回对应用户记录，失败返回 None。"""
    user_id = parse_token(auth_header)
    if user_id is None:
        return None
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    return row

def unauthorized():
    return (401, JSON_TYPE, error_body(40101, "未登录或登录已过期"))

# ---- 业务处理：认证 ----

def handle_login(payload):
    username = payload.get("username") or ""
    password = payload.get("password") or ""
    log_line("auth", "登录请求 username=%s password=%s" % (username, password))

    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    finally:
        conn.close()

    if row is None or row["password"] != password:
        log_line("auth", "登录失败 username=%s" % username)
        return (401, JSON_TYPE, error_body(40101, "用户名或密码错误"))

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)
    data = {
        "token": TOKEN_PREFIX + str(row["id"]),
        "userId": row["id"],
        "username": row["username"],
        "role": row["role"],
        "expiresAt": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    log_line("auth", "登录成功 username=%s userId=%s" % (row["username"], row["id"]))
    return (200, JSON_TYPE, ok_body(data))

def handle_logout(auth_header):
    user = current_user(auth_header)
    if user is None:
        return unauthorized()
    log_line("auth", "退出登录 userId=%s" % user["id"])
    return (200, JSON_TYPE, ok_body({"message": "已退出登录"}))

# ---- 业务处理：用户 ----

def handle_user_detail(auth_header, raw_id):
    if current_user(auth_header) is None:
        return unauthorized()
    user_id = int(raw_id)

    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return (404, JSON_TYPE, error_body(40401, "用户不存在"))
    return (200, JSON_TYPE, ok_body(user_to_dict(row)))

# ---- 业务处理：商品 ----

PRODUCT_SELECT = (
    "SELECT p.id, p.title, p.price, p.stock, p.category, p.description, p.status,"
    " p.seller_id, u.phone AS seller_phone, p.created_at"
    " FROM products p LEFT JOIN users u ON u.id = p.seller_id"
)

def handle_product_list(query):
    keyword = query.get("keyword", [""])[0].strip()
    status = query.get("status", [""])[0].strip()
    page = int(query.get("page", ["1"])[0] or "1")
    raw_size = query.get("pageSize", [""])[0]
    page_size = int(raw_size) if raw_size.strip() else DEFAULT_PAGE_SIZE

    conditions = []
    params = []
    if keyword:
        conditions.append("p.title LIKE '%" + keyword + "%'")
    if status:
        conditions.append("p.status = ?")
        params.append(status)
    else:
        conditions.append("p.status = 'on'")
    where = " AND ".join(conditions)

    offset = (page - 1) * page_size
    list_sql = (PRODUCT_SELECT + " WHERE " + where
                + " ORDER BY p.id LIMIT %d OFFSET %d" % (page_size, offset))
    count_sql = "SELECT COUNT(*) AS total FROM products p WHERE " + where

    conn = get_conn()
    try:
        total = conn.execute(count_sql, params).fetchone()["total"]
        rows = conn.execute(list_sql, params).fetchall()
    finally:
        conn.close()

    return (200, JSON_TYPE, ok_body({
        "total": total,
        "page": page,
        "pageSize": page_size,
        "items": [product_brief(row) for row in rows],
    }))

def handle_product_detail(raw_id):
    product_id = int(raw_id)

    conn = get_conn()
    try:
        row = conn.execute(PRODUCT_SELECT + " WHERE p.id = ?", (product_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return (404, JSON_TYPE, error_body(40401, "商品不存在"))
    return (200, JSON_TYPE, ok_body(product_detail(row)))

def handle_create_product(auth_header, payload):
    user = current_user(auth_header)
    if user is None:
        return unauthorized()

    title = (payload.get("title") or "").strip()
    price = payload.get("price")
    stock = payload.get("stock")
    category = payload.get("category")
    description = payload.get("description") or ""

    if not title or len(title) > 50:
        return (400, JSON_TYPE, error_body(40001, "标题长度需为 1~50 个字符"))
    if not isinstance(price, int) or isinstance(price, bool) or price <= 0:
        return (400, JSON_TYPE, error_body(40001, "价格必须为正整数（分）"))
    if not isinstance(stock, int) or isinstance(stock, bool) or stock < 0 or stock > 999:
        return (400, JSON_TYPE, error_body(40001, "库存需为 0~999 的整数"))
    if category not in CATEGORIES:
        return (400, JSON_TYPE, error_body(40001, "分类不在可选范围内"))

    created_at = iso_now()
    conn = get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO products (title, price, stock, category, description, status,"
            " seller_id, created_at) VALUES (?, ?, ?, ?, ?, 'on', ?, ?)",
            (title, price, stock, category, description, user["id"], created_at),
        )
        conn.commit()
        product_id = cursor.lastrowid
        row = conn.execute(PRODUCT_SELECT + " WHERE p.id = ?", (product_id,)).fetchone()
    finally:
        conn.close()

    log_line("product", "创建商品 productId=%s sellerId=%s" % (product_id, user["id"]))
    return (201, JSON_TYPE, ok_body(product_detail(row)))

def handle_product_status(auth_header, raw_id, payload):
    user = current_user(auth_header)
    if user is None:
        return unauthorized()

    status = payload.get("status")
    if status not in ("on", "off"):
        return (400, JSON_TYPE, error_body(40001, "状态只能为 on 或 off"))

    product_id = int(raw_id)
    conn = get_conn()
    try:
        row = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if row is None:
            return (404, JSON_TYPE, error_body(40401, "商品不存在"))
        conn.execute("UPDATE products SET status = ? WHERE id = ?", (status, product_id))
        conn.commit()
    finally:
        conn.close()

    log_line("product", "更新商品状态 productId=%s status=%s by=%s"
             % (product_id, status, user["id"]))
    return (200, JSON_TYPE, ok_body({"id": product_id, "status": status}))

# ---- 业务处理：订单 ----

ORDER_SELECT = (
    "SELECT o.id, o.order_no, o.user_id, u.username AS user_name, o.product_id,"
    " o.product_title, o.quantity, o.unit_price, o.total_amount, o.status,"
    " o.receiver_phone, o.address, o.created_at, o.paid_at"
    " FROM orders o LEFT JOIN users u ON u.id = o.user_id"
)

def handle_create_order(auth_header, payload):
    user = current_user(auth_header)
    if user is None:
        return unauthorized()

    product_id = payload.get("productId")
    if product_id is None:
        return (400, JSON_TYPE, error_body(40001, "参数不完整"))
    product_id = int(product_id)
    raw_quantity = payload.get("quantity")
    quantity = 1 if raw_quantity is None else int(raw_quantity)

    conn = get_conn()
    try:
        product = conn.execute(
            "SELECT id, title, price, stock FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        if product is None:
            return (404, JSON_TYPE, error_body(40401, "商品不存在"))
        if product["stock"] < quantity:
            return (409, JSON_TYPE, error_body(40901, "库存不足"))

        # 等待库存服务返回可售数量
        time.sleep(STOCK_WINDOW_SECONDS)

        unit_price = payload.get("unitPrice")
        if unit_price is None:
            unit_price = product["price"]
        unit_price = int(unit_price)

        total = unit_price / 100 * quantity
        total_amount = total * 100
        if payload.get("totalAmount") is not None:
            total_amount = payload.get("totalAmount")

        created_at = iso_now()
        cursor = conn.execute(
            "INSERT INTO orders (order_no, user_id, product_id, product_title, quantity,"
            " unit_price, total_amount, status, receiver_phone, address, created_at)"
            " VALUES ('', ?, ?, ?, ?, ?, ?, 'created', ?, ?, ?)",
            (user["id"], product_id, product["title"], quantity, unit_price,
             total_amount, user["phone"], user["address"], created_at),
        )
        order_id = cursor.lastrowid
        order_no = "SO%s%04d" % (datetime.now().strftime("%Y%m%d"), order_id)
        conn.execute("UPDATE orders SET order_no = ? WHERE id = ?", (order_no, order_id))
        conn.execute("UPDATE products SET stock = stock - ? WHERE id = ?",
                     (quantity, product_id))
        conn.commit()
    finally:
        conn.close()

    log_line("order", "创建订单 orderId=%s userId=%s receiverPhone=%s"
             % (order_id, user["id"], user["phone"]))
    return (201, JSON_TYPE, ok_body({
        "id": order_id, "orderNo": order_no,
        "productId": product_id, "productTitle": product["title"],
        "quantity": quantity, "unitPrice": unit_price,
        "totalAmount": total_amount, "status": "created",
        "receiverPhone": user["phone"], "address": user["address"],
        "createdAt": created_at,
    }))

def handle_order_detail(auth_header, raw_id):
    if current_user(auth_header) is None:
        return unauthorized()
    order_id = int(raw_id)

    conn = get_conn()
    try:
        row = conn.execute(ORDER_SELECT + " WHERE o.id = ?", (order_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return (404, JSON_TYPE, error_body(40401, "订单不存在"))
    return (200, JSON_TYPE, ok_body(order_to_dict(row)))

def handle_my_orders(auth_header):
    user = current_user(auth_header)
    if user is None:
        return unauthorized()

    conn = get_conn()
    try:
        rows = conn.execute(
            ORDER_SELECT + " WHERE o.user_id = ? ORDER BY o.id DESC", (user["id"],)
        ).fetchall()
    finally:
        conn.close()

    items = [order_to_dict(row) for row in rows]
    return (200, JSON_TYPE, ok_body({"total": len(items), "items": items}))

def handle_admin_orders(auth_header):
    if current_user(auth_header) is None:
        return unauthorized()

    conn = get_conn()
    try:
        rows = conn.execute(ORDER_SELECT + " ORDER BY o.id DESC").fetchall()
    finally:
        conn.close()

    items = [admin_order_item(row) for row in rows]
    return (200, JSON_TYPE, ok_body({"total": len(items), "items": items}))

# ---- 业务处理：支付 ----

def handle_create_payment(auth_header, payload):
    user = current_user(auth_header)
    if user is None:
        return unauthorized()

    order_id = payload.get("orderId")
    method = payload.get("method")
    if order_id is None or method is None:
        return (400, JSON_TYPE, error_body(40001, "参数不完整"))
    if method not in ("alipay", "wechat"):
        return (400, JSON_TYPE, error_body(40001, "不支持的支付方式"))
    order_id = int(order_id)

    conn = get_conn()
    try:
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        amount = order["total_amount"] if order is not None else 0
        paid_at = iso_now()
        cursor = conn.execute(
            "INSERT INTO payments (payment_no, order_id, user_id, method, amount, status,"
            " created_at, paid_at) VALUES ('', ?, ?, ?, ?, 'paid', ?, ?)",
            (order_id, user["id"], method, amount, paid_at, paid_at),
        )
        payment_id = cursor.lastrowid
        payment_no = "PAY%s%04d" % (datetime.now().strftime("%Y%m%d"), payment_id)
        conn.execute("UPDATE payments SET payment_no = ? WHERE id = ?",
                     (payment_no, payment_id))
        conn.execute("UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?",
                     (paid_at, order_id))
        conn.commit()
    finally:
        conn.close()

    log_line("pay", "发起支付 paymentId=%s orderId=%s method=%s amount=%s"
             % (payment_no, order_id, method, amount))
    return (200, JSON_TYPE, ok_body({
        "paymentId": payment_no, "orderId": order_id,
        "amount": amount, "status": "paid", "paidAt": paid_at,
    }))

def handle_payment_callback(payload):
    order_id = payload.get("orderId")
    payment_id = payload.get("paymentId") or ""
    result = payload.get("result")
    if order_id is None:
        return (400, JSON_TYPE, error_body(40001, "参数不完整"))
    order_id = int(order_id)

    conn = get_conn()
    try:
        order = conn.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
        if result == "success":
            paid_at = iso_now()
            conn.execute("UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?",
                         (paid_at, order_id))
            conn.commit()
            status = "paid"
        else:
            status = order["status"] if order is not None else "created"
    finally:
        conn.close()

    log_line("pay", "支付回调 orderId=%s paymentId=%s result=%s"
             % (order_id, payment_id, result))
    return (200, JSON_TYPE, ok_body({"orderId": order_id, "status": status}))

# ---- 业务处理：评价 ----

def stars_text(rating):
    value = max(0, min(5, int(rating)))
    return "★" * value + "☆" * (5 - value)

def render_reviews_page(product_title, rows):
    """服务端渲染商品评价列表页。"""
    head = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>商品评价</title>
<style>
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#f4f5f7;margin:0;padding:32px 16px;color:#222;}
.page{max-width:720px;margin:0 auto;background:#fff;border-radius:8px;padding:24px 28px 16px;box-shadow:0 1px 4px rgba(0,0,0,.08);}
h1{font-size:20px;margin:0 0 4px;}
.meta{color:#888;font-size:13px;margin:0 0 20px;}
.review{border-top:1px solid #eee;padding:14px 0;}
.head{font-size:13px;color:#666;margin-bottom:6px;}
.user{font-weight:600;color:#333;margin-right:12px;}
.stars{color:#f5a623;margin-right:12px;letter-spacing:1px;}.time{color:#aaa;}
.content{font-size:14px;line-height:1.7;white-space:pre-wrap;}
.empty{color:#999;font-size:14px;padding:12px 0;}footer{margin-top:20px;font-size:12px;color:#bbb;text-align:center;}
</style>
</head>
<body>
<div class="page">
"""
    parts = [head]
    parts.append("<h1>商品评价</h1>")
    parts.append('<p class="meta">%s 共 %d 条评价</p>\n' % (product_title, len(rows)))
    if not rows:
        parts.append('<p class="empty">暂无评价，购买后可以留下你的使用感受。</p>\n')
    for row in rows:
        parts.append('<div class="review">')
        parts.append(
            '<div class="head"><span class="user">%s</span>'
            '<span class="stars">%s</span><span class="time">%s</span></div>'
            % (row["username"], stars_text(row["rating"]), row["created_at"])
        )
        parts.append('<div class="content">%s</div>' % row["content"])
        parts.append("</div>\n")
    parts.append("<footer>校园优选 · 商品评价</footer>\n</div>\n</body>\n</html>\n")
    return "".join(parts)

def handle_reviews_page(query):
    raw_product_id = query.get("productId", [""])[0]
    try:
        product_id = int(raw_product_id)
    except ValueError:
        product_id = 0

    conn = get_conn()
    try:
        product = conn.execute(
            "SELECT id, title FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        rows = conn.execute(
            "SELECT r.id, r.content, r.rating, r.created_at, u.username"
            " FROM product_reviews r LEFT JOIN users u ON u.id = r.user_id"
            " WHERE r.product_id = ? ORDER BY r.id DESC",
            (product_id,),
        ).fetchall()
    finally:
        conn.close()

    title = product["title"] if product is not None else "未知商品"
    return (200, HTML_TYPE, render_reviews_page(title, rows))

def handle_create_review(auth_header, payload):
    user = current_user(auth_header)
    if user is None:
        return unauthorized()

    product_id = payload.get("productId")
    content = payload.get("content")
    rating = payload.get("rating")
    if product_id is None or content is None or rating is None:
        return (400, JSON_TYPE, error_body(40001, "参数不完整"))
    product_id = int(product_id)
    rating = int(rating)
    if not isinstance(content, str) or not content.strip() or len(content) > 200:
        return (400, JSON_TYPE, error_body(40001, "评价内容需为 1~200 个字符"))
    if rating < 1 or rating > 5:
        return (400, JSON_TYPE, error_body(40001, "评分必须为 1~5"))

    conn = get_conn()
    try:
        product = conn.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
        if product is None:
            return (404, JSON_TYPE, error_body(40401, "商品不存在"))
        created_at = iso_now()
        cursor = conn.execute(
            "INSERT INTO product_reviews (product_id, user_id, content, rating, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (product_id, user["id"], content, rating, created_at),
        )
        conn.commit()
        review_id = cursor.lastrowid
    finally:
        conn.close()

    return (201, JSON_TYPE, ok_body({
        "id": review_id,
        "productId": product_id,
        "userId": user["id"],
        "content": content,
        "rating": rating,
        "createdAt": created_at,
    }))

# ---- 其他 ----

def handle_health():
    uptime = round(time.time() - STARTED_AT, 1)
    return (200, JSON_TYPE, ok_body({"status": "up", "uptime": uptime}))

# ---- 路由 ----

def route(method, path, query, auth_header, payload):
    """按 method + path 分发到具体处理函数。"""
    segments = [seg for seg in path.split("/") if seg]

    if method == "GET" and segments == ["health"]:
        return handle_health()

    if len(segments) >= 2 and segments[0] == "api":
        area = segments[1]

        if area == "auth" and len(segments) == 3:
            if method == "POST" and segments[2] == "login":
                return handle_login(payload)
            if method == "POST" and segments[2] == "logout":
                return handle_logout(auth_header)

        if area == "users" and len(segments) == 3 and method == "GET":
            return handle_user_detail(auth_header, segments[2])

        if area == "admin" and segments[2:] == ["orders"] and method == "GET":
            return handle_admin_orders(auth_header)

        if area == "products":
            if len(segments) == 2 and method == "GET":
                return handle_product_list(query)
            if len(segments) == 2 and method == "POST":
                return handle_create_product(auth_header, payload)
            if len(segments) == 3 and method == "GET":
                return handle_product_detail(segments[2])
            if len(segments) == 4 and segments[3] == "status" and method == "PATCH":
                return handle_product_status(auth_header, segments[2], payload)

        if area == "orders":
            if len(segments) == 2 and method == "POST":
                return handle_create_order(auth_header, payload)
            if len(segments) == 3 and segments[2] == "mine" and method == "GET":
                return handle_my_orders(auth_header)
            if len(segments) == 3 and method == "GET":
                return handle_order_detail(auth_header, segments[2])

        if area == "payments":
            if len(segments) == 2 and method == "POST":
                return handle_create_payment(auth_header, payload)
            if len(segments) == 3 and segments[2] == "callback" and method == "POST":
                return handle_payment_callback(payload)

        if area == "product-reviews" and len(segments) == 2:
            if method == "GET":
                return handle_reviews_page(query)
            if method == "POST":
                return handle_create_review(auth_header, payload)

    return (404, JSON_TYPE, error_body(40401, "接口不存在"))

def read_json_body(raw):
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data

# ---- HTTP 层 ----

class ApiHandler(BaseHTTPRequestHandler):
    server_version = "CampusMall/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self._process("GET")

    def do_POST(self):
        self._process("POST")

    def do_PATCH(self):
        self._process("PATCH")

    def log_message(self, fmt, *args):
        # 访问日志在 _process 中统一输出
        return

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _process(self, method):
        started = time.time()
        parsed = urlsplit(self.path)
        query_string = parsed.query
        full_path = parsed.path + ("?" + query_string if query_string else "")
        query = parse_qs(query_string, keep_blank_values=True)
        auth_header = self.headers.get("Authorization") or ""
        raw_body = self._read_body()

        status, content_type, body_text = 500, JSON_TYPE, ""
        try:
            status, content_type, body = route(
                method, parsed.path, query, auth_header, read_json_body(raw_body)
            )
            if isinstance(body, str):
                body_text = body
            else:
                body_text = json.dumps(body, ensure_ascii=False)
        except Exception:
            traceback.print_exc(file=sys.stdout)
            sys.stdout.flush()
            status = 500
            content_type = JSON_TYPE
            body_text = json.dumps(error_body(50000, "服务内部错误"), ensure_ascii=False)

        self._write_response(status, content_type, body_text)
        cost_ms = (time.time() - started) * 1000
        log_line("access", "%s %s %d %.1fms token=%s"
                 % (method, full_path, status, cost_ms, auth_header or "-"))

    def _write_response(self, status, content_type, body_text):
        data = body_text.encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

class MallServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

def main():
    parser = argparse.ArgumentParser(description="校园优选电商后端服务")
    parser.add_argument("--port", type=int, default=8080, help="监听端口，默认 8080")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址，默认 0.0.0.0")
    args = parser.parse_args()

    init_database()
    server = MallServer((args.host, args.port), ApiHandler)
    log_line("boot", "服务已启动: http://127.0.0.1:%d" % args.port)
    log_line("boot", "数据库文件: %s" % DB_PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log_line("boot", "收到中断信号，服务退出")
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
