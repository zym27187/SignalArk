import { formatDateTime, formatDecimal, formatSymbolLabel, titleCase } from "../lib/format";
import type { ActiveOrder, SymbolNameMap } from "../types/api";

interface OrdersTableProps {
  orders: ActiveOrder[];
  symbolNames: SymbolNameMap;
  error?: string;
}

export function OrdersTable({ orders, symbolNames, error }: OrdersTableProps) {
  return (
    <div className="table-shell">
      {error ? <p className="section-error">订单读取失败：{error}</p> : null}

      {orders.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">暂无未完成订单</p>
          <p className="empty-state__copy">
            这里只展示还没结束的订单，比如待处理、已接收或部分成交。
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
              <th>已成交数量</th>
              <th>状态</th>
              <th>仅减仓</th>
              <th>下单时间</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.order_id}>
                <td>{formatSymbolLabel(order.symbol, symbolNames)}</td>
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
