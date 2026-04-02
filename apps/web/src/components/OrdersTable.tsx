import { formatDateTime, formatDecimal, titleCase } from "../lib/format";
import type { ActiveOrder } from "../types/api";

interface OrdersTableProps {
  orders: ActiveOrder[];
  error?: string;
}

export function OrdersTable({ orders, error }: OrdersTableProps) {
  return (
    <div className="table-shell">
      {error ? <p className="section-error">订单数据异常：{error}</p> : null}

      {orders.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">暂无活动订单</p>
          <p className="empty-state__copy">
            这里只展示控制平面中的 `NEW`、`ACK` 和 `PARTIALLY_FILLED` 订单。
          </p>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>标的</th>
              <th>方向</th>
              <th>类型</th>
              <th>数量</th>
              <th>已成交</th>
              <th>状态</th>
              <th>只减仓</th>
              <th>提交时间</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.order_id}>
                <td>{order.symbol}</td>
                <td>{titleCase(order.side)}</td>
                <td>{titleCase(order.order_type)}</td>
                <td>{formatDecimal(order.qty, 0)}</td>
                <td>{formatDecimal(order.filled_qty, 0)}</td>
                <td>{titleCase(order.status)}</td>
                <td>{order.reduce_only ? "是" : "否"}</td>
                <td>{formatDateTime(order.submitted_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
