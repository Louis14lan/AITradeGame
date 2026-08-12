from datetime import datetime
from typing import Dict, Optional
import json

# 开仓硬校验缓冲：止盈空间必须比往返手续费再高 0.1%，否则拒绝开仓
ENTRY_MIN_PROFIT_BUFFER = 0.001

class TradingEngine:
    def __init__(self, model_id: int, db, market_fetcher, ai_trader, trade_fee_rate: float = 0.001):
        self.model_id = model_id
        self.db = db
        self.market_fetcher = market_fetcher
        self.ai_trader = ai_trader
        self.coins = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE']
        self.trade_fee_rate = trade_fee_rate  # 从配置中传入费率
    
    def execute_trading_cycle(self) -> Dict:
        try:
            market_state = self._get_market_state()

            current_prices = {coin: market_state[coin]['price'] for coin in market_state}

            portfolio = self.db.get_portfolio(self.model_id, current_prices)

            # 1) 止损/止盈兜底：先于 AI 决策执行，行情突变时也能及时平仓
            exit_results = self._check_position_exits(market_state, portfolio)

            # 2) 止损可能已平掉部分仓位，重新获取最新持仓后再让 AI 决策
            portfolio = self.db.get_portfolio(self.model_id, current_prices)

            account_info = self._build_account_info(portfolio)
            print(f"[INFO] Current prices: {current_prices}")
            print(f"[INFO] Account info: {account_info}")
            print(f"[INFO] Market state: {market_state}")
            print(f"[INFO] Portfolio: {portfolio}")
            decisions = self.ai_trader.make_decision(
                market_state, portfolio, account_info, self.trade_fee_rate,
                self._get_interval_minutes()
            )
            print(f"[INFO] Decisions: {decisions}")

            self.db.add_conversation(
                self.model_id,
                user_prompt=self._format_prompt(market_state, portfolio, account_info),
                ai_response=json.dumps(decisions, ensure_ascii=False),
                cot_trace=''
            )

            execution_results = self._execute_decisions(decisions, market_state, portfolio)
            # 3) 止损平仓结果并入返回，方便前端/日志看到
            execution_results = exit_results + execution_results

            updated_portfolio = self.db.get_portfolio(self.model_id, current_prices)
            self.db.record_account_value(
                self.model_id,
                updated_portfolio['total_value'],
                updated_portfolio['cash'],
                updated_portfolio['positions_value']
            )
            
            return {
                'success': True,
                'decisions': decisions,
                'executions': execution_results,
                'portfolio': updated_portfolio
            }
            
        except Exception as e:
            print(f"[ERROR] Trading cycle failed (Model {self.model_id}): {e}")
            import traceback
            print(traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_market_state(self) -> Dict:
        market_state = {}
        prices = self.market_fetcher.get_current_prices(self.coins)
        
        for coin in self.coins:
            if coin in prices:
                market_state[coin] = prices[coin].copy()
                indicators = self.market_fetcher.calculate_technical_indicators(coin)
                market_state[coin]['indicators'] = indicators
        
        return market_state
    
    def _build_account_info(self, portfolio: Dict) -> Dict:
        model = self.db.get_model(self.model_id)
        initial_capital = model['initial_capital']
        total_value = portfolio['total_value']
        total_return = ((total_value - initial_capital) / initial_capital) * 100
        
        return {
            'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_return': total_return,
            'initial_capital': initial_capital
        }
    
    def _get_interval_minutes(self) -> int:
        """读取交易频率设置（分钟），失败时回退 60"""
        try:
            settings = self.db.get_settings()
            return int(settings.get('trading_frequency_minutes') or 60)
        except Exception:
            return 60

    def _format_prompt(self, market_state: Dict, portfolio: Dict,
                      account_info: Dict) -> str:
        return f"Market State: {len(market_state)} coins, Portfolio: {len(portfolio['positions'])} positions"
    
    def _execute_decisions(self, decisions: Dict, market_state: Dict, 
                          portfolio: Dict) -> list:
        results = []
        
        for coin, decision in decisions.items():
            if coin not in self.coins:
                continue
            
            signal = decision.get('signal', '').lower()
            
            try:
                if signal == 'buy_to_enter':
                    result = self._execute_buy(coin, decision, market_state, portfolio)
                elif signal == 'sell_to_enter':
                    result = self._execute_sell(coin, decision, market_state, portfolio)
                elif signal == 'close_position':
                    result = self._execute_close(coin, decision, market_state, portfolio)
                elif signal == 'hold':
                    result = {'coin': coin, 'signal': 'hold', 'message': 'Hold position'}
                else:
                    result = {'coin': coin, 'error': f'Unknown signal: {signal}'}
                
                results.append(result)
                
            except Exception as e:
                print(f"[TRADE-ERROR] {coin}: {e}")
                results.append({'coin': coin, 'error': str(e)})
        
        return results
    
    def _validate_entry_cost(self, coin: str, price: float, leverage: int,
                             decision: Dict) -> Optional[Dict]:
        """开仓前硬校验：止盈空间必须覆盖往返手续费，否则拒绝开仓。

        不依赖 AI 自觉——即使 AI 忽略了 Prompt 里的手续费规则，这里也会兜底拦截。
        仅当 AI 给出止盈价时才校验；没给则交由 Prompt 规则约束。
        """
        profit_target = decision.get('profit_target')
        if not profit_target or profit_target <= 0:
            return None

        # 目标价格变动幅度（手续费按名义金额收，故与杠杆无关）
        move_pct = abs(profit_target - price) / price
        round_trip_cost = self.trade_fee_rate * 2  # 开仓 + 平仓
        min_required = round_trip_cost + ENTRY_MIN_PROFIT_BUFFER

        if move_pct < min_required:
            return {
                'coin': coin,
                'error': (
                    f'Rejected by fee filter: profit target {move_pct:.2%} '
                    f'< round-trip cost + buffer {min_required:.2%} '
                    f'(fee {self.trade_fee_rate:.2%} x2)'
                )
            }
        return None

    def _execute_buy(self, coin: str, decision: Dict, market_state: Dict,
                    portfolio: Dict) -> Dict:
        quantity = float(decision.get('quantity', 0))
        leverage = int(decision.get('leverage', 1))
        price = market_state[coin]['price']

        if quantity <= 0:
            return {'coin': coin, 'error': 'Invalid quantity'}

        # 开仓前硬校验：止盈空间必须覆盖往返手续费（兜底风控，不依赖 AI 自觉）
        reject = self._validate_entry_cost(coin, price, leverage, decision)
        if reject:
            return reject

        # 计算交易额和交易费（按交易额的比例）
        trade_amount = quantity * price  # 交易额
        trade_fee = trade_amount * self.trade_fee_rate  # 交易费（0.2%）
        required_margin = (quantity * price) / leverage  # 保证金

        # 总需资金 = 保证金 + 交易费
        total_required = required_margin + trade_fee
        if total_required > portfolio['cash']:
            return {'coin': coin, 'error': 'Insufficient cash (including fees)'}

        # 更新持仓（携带 AI 设定的止损/止盈价，供引擎兜底执行）
        self.db.update_position(
            self.model_id, coin, quantity, price, leverage, 'long',
            stop_loss=decision.get('stop_loss'),
            profit_target=decision.get('profit_target')
        )
        
        # 记录交易（包含交易费）
        self.db.add_trade(
            self.model_id, coin, 'buy_to_enter', quantity, 
            price, leverage, 'long', pnl=-trade_fee, fee=trade_fee  # 开仓费从现金扣除
        )
        
        return {
            'coin': coin,
            'signal': 'buy_to_enter',
            'quantity': quantity,
            'price': price,
            'leverage': leverage,
            'fee': trade_fee,  # 返回费用信息
            'message': f'Long {quantity:.4f} {coin} @ ${price:.2f} (Fee: ${trade_fee:.2f})'
        }
    
    def _execute_sell(self, coin: str, decision: Dict, market_state: Dict, 
                 portfolio: Dict) -> Dict:
        quantity = float(decision.get('quantity', 0))
        leverage = int(decision.get('leverage', 1))
        price = market_state[coin]['price']
        
        if quantity <= 0:
            return {'coin': coin, 'error': 'Invalid quantity'}

        # 开仓前硬校验：止盈空间必须覆盖往返手续费（兜底风控，不依赖 AI 自觉）
        reject = self._validate_entry_cost(coin, price, leverage, decision)
        if reject:
            return reject

        # 计算交易额和交易费
        trade_amount = quantity * price
        trade_fee = trade_amount * self.trade_fee_rate
        required_margin = (quantity * price) / leverage

        # 总需资金 = 保证金 + 交易费
        total_required = required_margin + trade_fee
        if total_required > portfolio['cash']:
            return {'coin': coin, 'error': 'Insufficient cash (including fees)'}

        # 更新持仓（携带 AI 设定的止损/止盈价，供引擎兜底执行）
        self.db.update_position(
            self.model_id, coin, quantity, price, leverage, 'short',
            stop_loss=decision.get('stop_loss'),
            profit_target=decision.get('profit_target')
        )
        
        # 记录交易（包含交易费）
        self.db.add_trade(
            self.model_id, coin, 'sell_to_enter', quantity, 
            price, leverage, 'short', pnl=-trade_fee, fee=trade_fee  # 开仓费从现金扣除
        )
        
        return {
            'coin': coin,
            'signal': 'sell_to_enter',
            'quantity': quantity,
            'price': price,
            'leverage': leverage,
            'fee': trade_fee,
            'message': f'Short {quantity:.4f} {coin} @ ${price:.2f} (Fee: ${trade_fee:.2f})'
        }
    
    def _check_position_exits(self, market_state: Dict, portfolio: Dict) -> list:
        """检查持仓止盈/止损条件，触发则强制平仓。

        兜底风控，先于 AI 决策执行——确保 AI 输出的 stop_loss / profit_target
        真正被系统执行，而不是只停留在 Prompt 里。
        """
        results = []
        positions = portfolio.get('positions') or []

        for pos in positions:
            coin = pos['coin']
            current_price = market_state.get(coin, {}).get('price')
            if not current_price:
                continue

            stop_loss = pos.get('stop_loss')
            profit_target = pos.get('profit_target')
            trigger = None

            if pos['side'] == 'long':
                if stop_loss and current_price <= stop_loss:
                    trigger = 'stop_loss'
                elif profit_target and current_price >= profit_target:
                    trigger = 'profit_target'
            else:  # short
                if stop_loss and current_price >= stop_loss:
                    trigger = 'stop_loss'
                elif profit_target and current_price <= profit_target:
                    trigger = 'profit_target'

            if trigger:
                print(f"[RISK] {coin} {pos['side']} triggered {trigger} "
                      f"(price={current_price:.2f}, stop_loss={stop_loss}, "
                      f"profit_target={profit_target})")
                result = self._execute_close(
                    coin, {'signal': 'close_position'}, market_state, portfolio
                )
                result['trigger'] = trigger
                results.append(result)

        return results

    def _execute_close(self, coin: str, decision: Dict, market_state: Dict,
                    portfolio: Dict) -> Dict:
        position = None
        for pos in portfolio['positions']:
            if pos['coin'] == coin:
                position = pos
                break
        
        if not position:
            return {'coin': coin, 'error': 'Position not found'}
        
        current_price = market_state[coin]['price']
        entry_price = position['avg_price']
        quantity = position['quantity']
        side = position['side']
        
        # 计算平仓利润（未扣费）
        if side == 'long':
            gross_pnl = (current_price - entry_price) * quantity
        else:  # short
            gross_pnl = (entry_price - current_price) * quantity
        
        # 计算平仓交易费（按平仓时的交易额）
        trade_amount = quantity * current_price
        trade_fee = trade_amount * self.trade_fee_rate
        net_pnl = gross_pnl - trade_fee  # 净利润 = 毛利润 - 交易费
        
        # 关闭持仓
        self.db.close_position(self.model_id, coin, side)
        
        # 记录平仓交易（包含费用和净利润）
        self.db.add_trade(
            self.model_id, coin, 'close_position', quantity,
            current_price, position['leverage'], side, pnl=net_pnl, fee=trade_fee  # 新增fee参数
        )
        
        return {
            'coin': coin,
            'signal': 'close_position',
            'quantity': quantity,
            'price': current_price,
            'pnl': net_pnl,
            'fee': trade_fee,
            'message': f'Close {coin}, Gross P&L: ${gross_pnl:.2f}, Fee: ${trade_fee:.2f}, Net P&L: ${net_pnl:.2f}'
        }
