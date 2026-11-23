"""数据库工具：连接管理、查询与写入封装。"""

import logging

import pymysql

logger = logging.getLogger("db")

DB_CONFIG = {
    "host": "10.20.31.15",
    "port": 3306,
    "user": "mall_rw",
    "password": "Mall@2026#rw",
    "database": "campus_mall",
    "charset": "utf8mb4",
}

_conn = None


def get_connection():
    """返回进程内复用的连接。"""
    global _conn
    if _conn is None:
        _conn = pymysql.connect(**DB_CONFIG)
    return _conn


def query_all(sql):
    """执行查询并返回全部结果。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    return cursor.fetchall()


def query_one(sql):
    """执行查询并返回首行。"""
    rows = query_all(sql)
    if len(rows) > 0:
        return rows[0]
    return None


def execute(sql):
    """执行写入语句并返回自增主键。"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    conn.commit()
    return cursor.lastrowid
