# Deep Interview Context Snapshot: stock-trading-bot

- Task statement: User wants to make a stock auto-trading bot that is very smart and earns money well.
- Desired outcome: A bot that can start with small principal and potentially receive more capital if it performs well.
- Stated solution: Automated stock trading bot.
- Probable intent hypothesis: Build a practical wealth-generation trading system while controlling downside during early capital allocation.
- Known facts/evidence: Repository appears greenfield; only `.omx/` exists and no project source files were found at max depth 2.
- Constraints: Financial trading is high risk; no profit can be guaranteed; live trading may require broker/API credentials and regulatory/tax/risk controls.
- Unknowns/open questions: Market/country/broker, automation level, risk tolerance, strategy universe, data source, backtesting/paper trading requirements, monitoring, kill-switches.
- Decision-boundary unknowns: What the agent may decide independently vs what requires user confirmation, especially risk limits and live trading behavior.
- Likely codebase touchpoints: New greenfield project structure, backtester, strategy engine, broker adapter, risk manager, scheduler, monitoring/logging, config/secrets handling.
- Prompt-safe initial-context summary status: not_needed
