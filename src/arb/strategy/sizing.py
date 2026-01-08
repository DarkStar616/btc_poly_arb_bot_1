def get_size_usd(capital_usd, risk_fraction, max_usd):
    # Simple fixed fractional
    amt = capital_usd * risk_fraction
    return min(amt, max_usd)
