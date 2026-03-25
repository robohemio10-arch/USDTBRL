from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderState(str, Enum):
    IDLE = "idle"
    PLANNED = "planned"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CycleState(str, Enum):
    FLAT = "flat"
    ENTERING = "entering"
    LONG = "long"
    EXITING = "exiting"
    RECONCILING = "reconciling"


class RegimeType(str, Enum):
    UNKNOWN = "unknown"
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
