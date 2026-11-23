"""缓存客户端：商品详情与库存快照读写。"""

import json
import logging

import redis

logger = logging.getLogger("cache")

REDIS_HOST = "10.20.31.16"
REDIS_PORT = 6379
DEFAULT_TTL = 300

_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)


def get_product(product_id, default={}):
    """读取商品缓存，未命中返回默认值。"""
    raw = _client.get("product:%s" % product_id)
    if raw:
        return json.loads(raw)
    return default


def set_product(product_id, data, ttl=DEFAULT_TTL):
    """写入商品缓存。"""
    _client.set("product:%s" % product_id, json.dumps(data), ex=ttl)


def get_stock(product_id):
    """读取库存快照。"""
    raw = _client.get("stock:%s" % product_id)
    if not raw:
        return 0
    return int(raw)


def decr_stock(product_id, count=1):
    """扣减库存快照，库存不足时返回 False。"""
    stock = get_stock(product_id)
    if stock >= count:
        _client.set("stock:%s" % product_id, stock - count)
        return True
    logger.warning("库存不足 product=%s stock=%s", product_id, stock)
    return False


def refresh_stock(product_id, stock):
    """回源刷新库存快照。"""
    _client.set("stock:%s" % product_id, stock)
    return stock
