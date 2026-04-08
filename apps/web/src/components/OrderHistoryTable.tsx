import { compactId, formatDateTime, formatDecimal, titleCase } from "../lib/format";
import type { HistoryOrder } from "../types/api";

interface OrderHistoryTableProps {
  orders: HistoryOrder[];
  error?: string;
}

export function OrderHistoryTable({ orders, error }: OrderHistoryTableProps) {
  return (
    <div className="table-shell">
      {error ? <p className="section-error">历史订单读取失败：{error}</p> : null}

      {orders.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">暂无历史订单</p>
          <p className="empty-state__copy">
            更新筛选后，这里会展示最近一段时间订单从提交到结束的结果。
          </p>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>订单编号</th>
              <th>标的</th>
              <th>方向</th>
              <th>类型</th>
              <th>数量</th>
              <th>已成交数量</th>
              <th>成交均价</th>
              <th>状态</th>
              <th>风险判断</th>
              <th>仅减仓</th>
              <th>最后更新</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.order_id}>
                <td title={order.order_id}>{compactId(order.order_id)}</td>
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
