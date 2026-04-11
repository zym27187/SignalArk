import { DefinitionGrid } from "./DefinitionGrid";

export function TradingGlossaryPanel() {
  return (
    <div className="trading-glossary">
      <p className="trading-glossary__intro">
        下面这些词是页面里最常出现的交易术语，先理解它们，再看数字会轻松很多。
      </p>
      <DefinitionGrid
        items={[
          {
            label: "持仓",
            value: "账户当前还持有多少股票",
            hint: "它会决定你现在暴露在哪些价格波动里。",
          },
          {
            label: "成交",
            value: "订单真正买到或卖掉的记录",
            hint: "只有成交后，仓位和现金才会真的变化。",
          },
          {
            label: "冻结资金",
            value: "已经被挂单暂时占住、暂时不能自由使用的钱",
            hint: "看到可用资金变少时，先排查是不是还有订单在排队。",
          },
          {
            label: "权益",
            value: "现金加上当前持仓按最新价格估算后的总价值",
            hint: "它比单看现金更能反映账户整体状态。",
          },
          {
            label: "回撤",
            value: "账户从之前高点回落了多少",
            hint: "回撤越大，说明这段时间承受的损失或波动越明显。",
          },
          {
            label: "Kill Switch",
            value: "紧急刹车，阻止新的开仓",
            hint: "通常在系统异常或人工紧急干预时开启。",
          },
          {
            label: "Protection Mode",
            value: "风险保护状态，系统会更保守地限制动作",
            hint: "这通常意味着对账、数据或运行状态存在不确定性。",
          },
        ]}
      />
    </div>
  );
}
