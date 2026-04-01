import { formatDateTime, formatDecimal, titleCase } from "../lib/format";
import type { ActiveOrder } from "../types/api";

interface OrdersTableProps {
  orders: ActiveOrder[];
  error?: string;
}

export function OrdersTable({ orders, error }: OrdersTableProps) {
  return (
    <div className="table-shell">
      {error ? <p className="section-error">Orders feed issue: {error}</p> : null}

      {orders.length === 0 ? (
        <div className="empty-state">
          <p className="empty-state__title">No active orders</p>
          <p className="empty-state__copy">
            The control plane will list only `NEW`, `ACK`, and `PARTIALLY_FILLED` orders here.
          </p>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Side</th>
              <th>Type</th>
              <th>Qty</th>
              <th>Filled</th>
              <th>Status</th>
              <th>Reduce Only</th>
              <th>Submitted</th>
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
                <td>{order.reduce_only ? "Yes" : "No"}</td>
                <td>{formatDateTime(order.submitted_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

