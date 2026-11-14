import { useState } from 'react';
import './PremiumMoveLab.css';

const startingPremium = 50;
const delta = 0.4;
const theta = -1.5;
const vega = 2;

function signedRupees(value: number) {
  return `${value >= 0 ? '+' : '−'}₹${Math.abs(value).toFixed(2)}`;
}

export default function PremiumMoveLab() {
  const [stockMove, setStockMove] = useState(2);
  const [ivMove, setIvMove] = useState(-1);
  const [oneDay, setOneDay] = useState(true);
  const directionEffect = delta * stockMove;
  const timeEffect = oneDay ? theta : 0;
  const volatilityEffect = vega * ivMove;
  const estimatedChange = directionEffect + timeEffect + volatilityEffect;
  const estimatedPremium = startingPremium + estimatedChange;

  return (
    <section className="learn-premium-lab learn-panel" aria-labelledby="premium-lab-title">
      <div className="learn-premium-heading">
        <div>
          <span className="learn-overline">A SIMPLE PREMIUM STORY</span>
          <h3 id="premium-lab-title">Can a call lose value when the stock rises?</h3>
          <p>Try a one-step example. This is a bought call with a starting premium of ₹50 per unit. Its example delta is 0.40, theta is −₹1.50 for about one day, and vega is ₹2 per IV point.</p>
        </div>
        <span className="learn-premium-badge">Illustration only</span>
      </div>

      <div className="learn-premium-content">
        <div className="learn-premium-controls">
          <label htmlFor="stock-move">Stock price change <strong>{signedRupees(stockMove)}</strong></label>
          <input id="stock-move" type="range" min="-5" max="5" step="0.5" value={stockMove} onChange={event => setStockMove(Number(event.target.value))} />
          <div className="learn-premium-range"><span>−₹5</span><span>+₹5</span></div>

          <label htmlFor="iv-move">IV change <strong>{ivMove >= 0 ? '+' : '−'}{Math.abs(ivMove).toFixed(1)} points</strong></label>
          <input id="iv-move" type="range" min="-5" max="5" step="0.5" value={ivMove} onChange={event => setIvMove(Number(event.target.value))} />
          <div className="learn-premium-range"><span>−5 points</span><span>+5 points</span></div>

          <label className="learn-premium-check"><input type="checkbox" checked={oneDay} onChange={event => setOneDay(event.target.checked)} /> About one day passes</label>
          <p className="learn-premium-prompt">Try keeping the stock at +₹2 and IV at −1 point. The call can lose value even though the stock went up.</p>
        </div>

        <div className="learn-premium-result" aria-live="polite">
          <div className="learn-premium-effect"><span>Stock move × delta</span><strong className={directionEffect >= 0 ? 'up' : 'down'}>{signedRupees(directionEffect)}</strong></div>
          <div className="learn-premium-effect"><span>{oneDay ? 'About one day of theta' : 'No day passes'}</span><strong className={timeEffect >= 0 ? 'up' : 'down'}>{signedRupees(timeEffect)}</strong></div>
          <div className="learn-premium-effect"><span>IV move × vega</span><strong className={volatilityEffect >= 0 ? 'up' : 'down'}>{signedRupees(volatilityEffect)}</strong></div>
          <div className="learn-premium-total"><span>Approximate premium change</span><strong className={estimatedChange >= 0 ? 'up' : 'down'}>{signedRupees(estimatedChange)}</strong></div>
          <p>Starting ₹50.00 → <b>about ₹{estimatedPremium.toFixed(2)} per unit</b></p>
        </div>
      </div>
      <p className="learn-premium-limit">This adds three nearby estimates, not real option quotes or a forecast. Delta, theta and vega change; gamma, bid-ask spread, fees and other factors are left out. Paperlane's synthetic market does not provide live Greeks or IV.</p>
      <a className="learn-source" href="https://prd-web.optionseducation.org/advancedconcepts/volatility-the-greeks" target="_blank" rel="noreferrer">Read more: Options Industry Council on the Greeks ↗</a>
    </section>
  );
}
