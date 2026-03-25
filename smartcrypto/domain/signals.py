from smartcrypto.domain.models import SignalDecision


def no_signal(reason: str = "no_signal") -> SignalDecision:
    return SignalDecision(should_buy=False, should_sell=False, confidence=0.0, reason=reason)
