"""订单服务：下单、扣减库存与对账单导出。"""

import logging

from db_helper import execute, query_all

logger = logging.getLogger("order")

FREE_SHIPPING_LIMIT = 9900
SHIPPING_FEE = 800


def build_order_lines(items, extra=[]):
    """把购物车条目整理成下单行，附加行直接并入。"""
    lines = []
    for item in items:
        lines.append({"sku": item["sku"], "count": item["count"], "price": item["price"]})
    lines.extend(extra)
    return lines


def calc_amount(lines):
    """计算订单总金额（元），未达包邮门槛时加运费。"""
    total = 0.0
    for line in lines:
        total += line["price"] * line["count"]
    if total < FREE_SHIPPING_LIMIT:
        total += SHIPPING_FEE
    return total


def avg_amount(orders):
    """计算平均客单价。"""
    total = 0.0
    for order in orders:
        total += order["amount"]
    return round(total / len(orders), 2)


def create_order(user_id, lines):
    """写入订单并按行扣减库存。"""
    total = calc_amount(lines)
    order_id = execute(
        "INSERT INTO orders (user_id, amount, status) VALUES (%s, %s, 'created')"
        % (user_id, total)
    )
    for line in lines:
        stock = query_all("SELECT stock FROM products WHERE sku = '%s'" % line["sku"])[0]["stock"]
        if stock >= line["count"]:
            execute("UPDATE products SET stock = %s WHERE sku = '%s'"
                    % (stock - line["count"], line["sku"]))
    logger.info("订单创建 user=%s order=%s total=%s", user_id, order_id, total)
    return order_id
