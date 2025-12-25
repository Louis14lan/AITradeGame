import json
from typing import Dict, Optional
from openai import OpenAI, APIConnectionError, APIError

class AITrader:
    def __init__(self, provider_type: str, api_key: str, api_url: str, model_name: str):
        self.provider_type = provider_type.lower()
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name
    
    def make_decision(self, market_state: Dict, portfolio: Dict, 
                     account_info: Dict) -> Dict:
        prompt = self._build_prompt(market_state, portfolio, account_info)
        print(f"[INFO] Prompt: {prompt}")
        
        response = self._call_llm(prompt)
        print(f"[INFO] Response: {response}")
        decisions = self._parse_response(response)
        
        return decisions
    
    def _build_prompt(self, market_state: Dict, portfolio: Dict,
                     account_info: Dict) -> str:
        """构建系统化的交易决策 Prompt，提供完整的市场数据让 AI 自主分析和决策"""

        # === 市场概况分析 ===
        market_summary = self._analyze_market_overview(market_state)

        # === 个币详细数据 ===
        coins_analysis = self._format_coins_data(market_state)

        # === 账户和持仓状态 ===
        account_status = self._format_account_status(portfolio, account_info)

        # === 构建主 Prompt ===
        prompt = f"""You are a professional cryptocurrency quantitative trader with expertise in technical analysis and risk management. Your decision frequency is every 3 minutes.

=== MARKET OVERVIEW ===
{market_summary}

=== DETAILED MARKET DATA ===
{coins_analysis}

=== ACCOUNT & POSITIONS ===
{account_status}

=== TRADING FRAMEWORK ===
Decision Signals:
- buy_to_enter: Open long position
- sell_to_enter: Open short position
- close_position: Close existing position
- hold: No action needed

Risk Management Constraints:
- Maximum 10 concurrent positions
- Risk per trade: 1-5% of portfolio
- Leverage range: 1-20x (use conservatively)
- Stop-loss is mandatory for all positions

Your Task:
1. Analyze each asset's trend, momentum, and volatility
2. Verify trend strength with volume confirmation
3. Identify high-probability trading opportunities
4. Determine optimal entry/exit points using technical indicators
5. Set appropriate leverage, profit targets, and stop-losses
6. Manage existing positions based on current market conditions

Key Principles:
- Cut losses quickly when trend reverses
- Let profitable positions run with trailing stops
- Avoid overtrading - quality over quantity
- Consider correlation between assets
- Adapt position sizing to volatility levels

Volume Analysis Guidelines:
- HIGH volume (ratio >1.5x) confirms trend strength
- LOW volume (ratio <0.5x) suggests weak trend, avoid entry
- INCREASING volume + uptrend = strong bullish signal
- DECREASING volume + uptrend = potential reversal warning
- Price-Volume DIVERGENCE signals possible trend reversal
- Volume breakout (>2x avg) on support/resistance = valid breakout

OUTPUT FORMAT (JSON only, no explanations):
```json
{{
  "COIN_SYMBOL": {{
    "signal": "buy_to_enter|sell_to_enter|close_position|hold",
    "quantity": 0.5,
    "leverage": 5,
    "profit_target": 45000.0,
    "stop_loss": 42000.0,
    "confidence": 0.8,
    "justification": "Concise technical reason (max 20 words)"
  }}
}}
```

Analyze the data and provide your trading decisions in JSON format only.
"""

        return prompt

    def _analyze_market_overview(self, market_state: Dict) -> str:
        """分析整体市场状况"""
        if not market_state:
            return "No market data available"

        # 统计市场情绪
        bullish_count = 0
        bearish_count = 0
        neutral_count = 0
        high_volatility_count = 0

        total_change_24h = 0

        for coin, data in market_state.items():
            total_change_24h += data.get('change_24h', 0)

            if 'indicators' in data:
                ind = data['indicators']
                trend = ind.get('trend_direction', 'neutral')
                volatility = ind.get('volatility_level', 'medium')

                if trend == 'bullish':
                    bullish_count += 1
                elif trend == 'bearish':
                    bearish_count += 1
                else:
                    neutral_count += 1

                if volatility == 'high':
                    high_volatility_count += 1

        total_coins = len(market_state)
        avg_change_24h = total_change_24h / total_coins if total_coins > 0 else 0

        # 判断市场情绪
        if bullish_count > bearish_count * 1.5:
            market_sentiment = "BULLISH"
        elif bearish_count > bullish_count * 1.5:
            market_sentiment = "BEARISH"
        else:
            market_sentiment = "NEUTRAL/MIXED"

        # 判断波动率环境
        volatility_env = "HIGH" if high_volatility_count > total_coins / 2 else "NORMAL"

        summary = f"""Market Sentiment: {market_sentiment} ({bullish_count} bullish, {bearish_count} bearish, {neutral_count} neutral)
Average 24h Change: {avg_change_24h:+.2f}%
Volatility Environment: {volatility_env}
Total Assets Tracked: {total_coins}"""

        return summary

    def _format_coins_data(self, market_state: Dict) -> str:
        """格式化每个币种的详细数据"""
        if not market_state:
            return "No coin data available"

        coins_text = ""

        for coin, data in sorted(market_state.items()):
            price = data.get('price', 0)
            change_24h = data.get('change_24h', 0)

            coins_text += f"\n[{coin}] Price: ${price:,.2f} | 24h: {change_24h:+.2f}%\n"

            if 'indicators' in data and data['indicators']:
                ind = data['indicators']

                # 趋势信息
                trend_dir = ind.get('trend_direction', 'neutral').upper()
                trend_strength = ind.get('trend_strength', 0)
                coins_text += f"  Trend: {trend_dir} (Strength: {trend_strength:+.1f})\n"

                # EMA 趋势
                ema_9 = ind.get('ema_9', 0)
                ema_21 = ind.get('ema_21', 0)
                ema_50 = ind.get('ema_50', 0)
                coins_text += f"  EMA: 9=${ema_9:,.2f} | 21=${ema_21:,.2f} | 50=${ema_50:,.2f}\n"

                # MACD
                macd = ind.get('macd', 0)
                macd_signal = ind.get('macd_signal', 0)
                macd_hist = ind.get('macd_histogram', 0)
                macd_cross = "BULLISH CROSS" if macd_hist > 0 else "BEARISH CROSS" if macd_hist < 0 else "NEUTRAL"
                coins_text += f"  MACD: {macd:.2f} | Signal: {macd_signal:.2f} | Histogram: {macd_hist:.2f} ({macd_cross})\n"

                # 动量指标
                rsi = ind.get('rsi_14', 50)
                stoch_rsi = ind.get('stoch_rsi', 50)
                roc = ind.get('roc_10', 0)

                rsi_status = "OVERBOUGHT" if rsi > 70 else "OVERSOLD" if rsi < 30 else "NEUTRAL"
                coins_text += f"  RSI: {rsi:.1f} ({rsi_status}) | Stoch RSI: {stoch_rsi:.1f} | ROC(10d): {roc:+.2f}%\n"

                # 布林带
                bb_upper = ind.get('bb_upper', 0)
                bb_middle = ind.get('bb_middle', 0)
                bb_lower = ind.get('bb_lower', 0)
                bb_width = ind.get('bb_width', 0)
                price_pos = ind.get('price_position', 'middle').upper()
                coins_text += f"  Bollinger: Upper=${bb_upper:,.2f} | Mid=${bb_middle:,.2f} | Lower=${bb_lower:,.2f}\n"
                coins_text += f"  BB Width: {bb_width:.2f}% | Price Position: {price_pos}\n"

                # 波动率和ATR
                atr = ind.get('atr_14', 0)
                volatility = ind.get('volatility_level', 'medium').upper()
                coins_text += f"  ATR(14): ${atr:,.2f} | Volatility: {volatility}\n"

                # 多周期价格变化
                change_1h = ind.get('change_1h', 0)
                change_4h = ind.get('change_4h', 0)
                change_7d = ind.get('change_7d', 0)
                coins_text += f"  Price Changes: 1h {change_1h:+.2f}% | 4h {change_4h:+.2f}% | 7d {change_7d:+.2f}%\n"

                # 成交量分析
                volume_24h = ind.get('volume_24h', 0)
                volume_ma_20 = ind.get('volume_ma_20', 0)
                volume_ratio = ind.get('volume_ratio', 1.0)
                volume_trend = ind.get('volume_trend', 'stable').upper()
                pv_divergence = ind.get('price_volume_divergence', 'none').upper()

                # Format volume with K/M/B suffix
                def format_volume(vol):
                    if vol >= 1e9:
                        return f"${vol/1e9:.2f}B"
                    elif vol >= 1e6:
                        return f"${vol/1e6:.2f}M"
                    elif vol >= 1e3:
                        return f"${vol/1e3:.2f}K"
                    else:
                        return f"${vol:.2f}"

                volume_status = "HIGH" if volume_ratio > 1.5 else "LOW" if volume_ratio < 0.5 else "NORMAL"
                coins_text += f"  Volume 24h: {format_volume(volume_24h)} | Avg(20d): {format_volume(volume_ma_20)} | Ratio: {volume_ratio:.2f}x ({volume_status})\n"
                coins_text += f"  Volume Trend: {volume_trend}"

                if pv_divergence != 'NONE':
                    coins_text += f" | ⚠️  Price-Volume Divergence: {pv_divergence}"
                coins_text += "\n"

        return coins_text.strip()

    def _format_account_status(self, portfolio: Dict, account_info: Dict) -> str:
        """格式化账户和持仓状态"""
        initial_capital = account_info.get('initial_capital', 0)
        total_value = portfolio.get('total_value', 0)
        cash = portfolio.get('cash', 0)
        total_return = account_info.get('total_return', 0)

        status_text = f"""Portfolio Summary:
- Initial Capital: ${initial_capital:,.2f}
- Current Total Value: ${total_value:,.2f}
- Available Cash: ${cash:,.2f}
- Total Return: {total_return:+.2f}%
- Cash Utilization: {((initial_capital - cash) / initial_capital * 100):.1f}%

Active Positions:"""

        positions = portfolio.get('positions', [])

        if not positions:
            status_text += "\n- No open positions"
        else:
            for pos in positions:
                coin = pos.get('coin', 'N/A')
                side = pos.get('side', 'N/A').upper()
                quantity = pos.get('quantity', 0)
                avg_price = pos.get('avg_price', 0)
                leverage = pos.get('leverage', 1)

                # 计算未实现盈亏（如果有当前价格）
                unrealized_pnl = pos.get('unrealized_pnl', 0)
                unrealized_pnl_pct = pos.get('unrealized_pnl_pct', 0)

                status_text += f"\n- {coin} {side} | Qty: {quantity:.4f} @ ${avg_price:,.2f} | Leverage: {leverage}x"
                if unrealized_pnl != 0:
                    status_text += f" | P&L: ${unrealized_pnl:+,.2f} ({unrealized_pnl_pct:+.2f}%)"

        return status_text
    
    def _call_llm(self, prompt: str) -> str:
        """Call LLM API based on provider type"""
        # OpenAI-compatible providers (same format)
        if self.provider_type in ['openai', 'azure_openai', 'deepseek']:
            return self._call_openai_api(prompt)
        elif self.provider_type == 'anthropic':
            return self._call_anthropic_api(prompt)
        elif self.provider_type == 'gemini':
            return self._call_gemini_api(prompt)
        else:
            # Default to OpenAI-compatible API
            return self._call_openai_api(prompt)
    
    def _call_openai_api(self, prompt: str) -> str:
        """Call OpenAI-compatible API"""
        try:
            base_url = self.api_url.rstrip('/')
            if not base_url.endswith('/v1'):
                if '/v1' in base_url:
                    base_url = base_url.split('/v1')[0] + '/v1'
                else:
                    base_url = base_url + '/v1'
            
            client = OpenAI(
                api_key=self.api_key,
                base_url=base_url
            )
            
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional cryptocurrency trader. Output JSON format only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=8000
            )
            print(f"[INFO] Response: {response}")
            
            return response.choices[0].message.content
            
        except APIConnectionError as e:
            error_msg = f"API connection failed: {str(e)}"
            print(f"[ERROR] {error_msg}")
            raise Exception(error_msg)
        except APIError as e:
            error_msg = f"API error ({e.status_code}): {e.message}"
            print(f"[ERROR] {error_msg}")
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"OpenAI API call failed: {str(e)}"
            print(f"[ERROR] {error_msg}")
            import traceback
            print(traceback.format_exc())
            raise Exception(error_msg)
    
    def _call_anthropic_api(self, prompt: str) -> str:
        """Call Anthropic Claude API"""
        try:
            import requests
            
            base_url = self.api_url.rstrip('/')
            if not base_url.endswith('/v1'):
                base_url = base_url + '/v1'
            
            url = f"{base_url}/messages"
            headers = {
                'Content-Type': 'application/json',
                'x-api-key': self.api_key,
                'anthropic-version': '2023-06-01'
            }
            
            data = {
                "model": self.model_name,
                "max_tokens": 2000,
                "system": "You are a professional cryptocurrency trader. Output JSON format only.",
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            return result['content'][0]['text']
            
        except Exception as e:
            error_msg = f"Anthropic API call failed: {str(e)}"
            print(f"[ERROR] {error_msg}")
            import traceback
            print(traceback.format_exc())
            raise Exception(error_msg)
    
    def _call_gemini_api(self, prompt: str) -> str:
        """Call Google Gemini API"""
        try:
            import requests
            
            base_url = self.api_url.rstrip('/')
            if not base_url.endswith('/v1'):
                base_url = base_url + '/v1'
            
            url = f"{base_url}/{self.model_name}:generateContent"
            headers = {
                'Content-Type': 'application/json'
            }
            params = {'key': self.api_key}
            
            data = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": f"You are a professional cryptocurrency trader. Output JSON format only.\n\n{prompt}"
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 2000
                }
            }
            
            response = requests.post(url, headers=headers, params=params, json=data, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            return result['candidates'][0]['content']['parts'][0]['text']
            
        except Exception as e:
            error_msg = f"Gemini API call failed: {str(e)}"
            print(f"[ERROR] {error_msg}")
            import traceback
            print(traceback.format_exc())
            raise Exception(error_msg)
    
    
    def _parse_response(self, response: str) -> Dict:
        response = response.strip()
        
        if '```json' in response:
            response = response.split('```json')[1].split('```')[0]
        elif '```' in response:
            response = response.split('```')[1].split('```')[0]
        
        try:
            decisions = json.loads(response.strip())
            return decisions
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON parse failed: {e}")
            print(f"[DATA] Response:\n{response}")
            return {}
