import { formatDateTime, formatDecimal, titleCase } from "../lib/format";
import type { HistoryOrder } from "../types/api";

interface OrderHistoryTableProps {
  orders: HistoryOrder[];
  error?: string;
}

export function OrderHistoryTable({ orders, error }: OrderHistoryTableProps) {
  return (
    <div className="table-shell">
      {error ? <p className="section-error">历史订单异常：{error}</p> : null}

      {orders.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">暂无历史订单</p>
          <p className="empty-state__copy">
            应用筛选后，这里会展示最近一段时间的订单生命周期结果。
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
              <th>均价</th>
              <th>状态</th>
              <th>风控</th>
              <th>只减仓</th>
              <th>更新时间</th>
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
                <td>{formatDecimal(order.avg_fill_price, 2)}</td>
                <td>{titleCase(order.status)}</td>
                <td title={order.risk_reason ?? "无额外风控备注"}>{titleCase(order.risk_decision)}</td>
                <td>{order.reduce_only ? "是" : "否"}</td>
                <td>{formatDateTime(order.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

