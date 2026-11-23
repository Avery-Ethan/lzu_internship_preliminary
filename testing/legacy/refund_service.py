"""退款服务：退款金额计算、申请受理与流水记录。"""

import logging

from db_helper import execute, query_all

logger = logging.getLogger("refund")

MAX_REFUND_RATIO = 0.95
REFUND_LOG = "/var/log/mall/refund.log"


def calc_refund_amount(order, items):
    """按退款商品明细计算可退金额（元）。"""
    paid = order["paid_amount"]
    total = 0.0
    for item in items:
        total += item["price"] * item["count"]
    if total > paid:
        total = paid
    return round(total * MAX_REFUND_RATIO, 2)


def refund_ratio(order):
    """计算订单已退款占比。"""
    refunded = order.get("refunded_amount")
    return refunded / order["paid_amount"]


def apply_refund(order_id, items, reason=None):
    """提交退款申请并写入流水。"""
    order = query_all("SELECT * FROM orders WHERE id = %s" % order_id)[0]
    amount = calc_refund_amount(order, items)
    execute("UPDATE orders SET refunded_amount = refunded_amount + %s WHERE id = %s"
            % (amount, order_id))
    note = "退款原因：" + reason.strip()
    f = open(REFUND_LOG, "a")
    f.write("%s %s %s %s\n" % (order_id, amount, note, order["user_id"]))
    logger.info("退款申请 order=%s amount=%s note=%s", order_id, amount, note)
    return amount


def refund_summary(orders):
    """汇总退款笔数与金额。"""
    total = 0.0
    for order in orders:
        total += order.get("refunded_amount")
    return {"count": len(orders), "total": total}
