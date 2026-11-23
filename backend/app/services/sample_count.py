"""样本数量字段的共享校验。

样本数量是样本分层和标注派发之间唯一的数量凭据，所有入口（登记、确认出样、
补录、数据流派发）都必须走同一套解析规则，避免 ``int("")`` 之类的隐式转换
把空值、小数、非数字或负数当成可用样本量。
"""
from __future__ import annotations

import datetime
import math
import re
import threading
from typing import Any

from app.store import store

# 同一策略的确认、补录和派发需要串行化：并发确认只能产生一次合法派发。
SAMPLE_LOCK = threading.RLock()

COUNT_KEYS = (
    "样本数量",
    "样本数",
    "数量",
    "sample_count",
    "sampleCount",
    "sample_size",
    "sampleSize",
    "count",
    "quantity",
    "value",
)

# 兼容历史数据：已按整数字符串记录的数量（例如 "12"）仍视为合法。
_INTEGER_TEXT = re.compile(r"^[+-]?\d+$")

_INVALID_REASON = {
    "empty": "样本数量为空，暂无可用数量，待补录",
    "bool": "样本数量必须为正整数，布尔值不是有效样本量",
    "fraction": "样本数量必须为整数，小数不是有效样本量",
    "non_numeric": "样本数量不是有效整数，暂无可用数量",
    "negative": "样本数量不能为负数，暂无可用数量",
    "zero": "样本数量为 0，暂无可用数量",
}


def parse_sample_count(value: Any) -> tuple[int | None, str]:
    """把任意输入解析成合法样本量。

    Returns:
        ``(normalized, reason)``。合法时 ``normalized`` 为正整数、``reason`` 为空；
        非法时 ``normalized`` 为 ``None``，``reason`` 给出可读原因。
    """
    if value is None:
        return None, _INVALID_REASON["empty"]

    if isinstance(value, bool):
        return None, _INVALID_REASON["bool"]

    if isinstance(value, int):
        number = value
    elif isinstance(value, float):
        # 1.5 这类小数不是有效样本量；12.0 是整数值，仍按数字处理。
        if not math.isfinite(value) or not value.is_integer():
            return None, _INVALID_REASON["fraction"]
        number = int(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None, _INVALID_REASON["empty"]
        if not _INTEGER_TEXT.fullmatch(text):
            # 区分小数和普通非数字，方便值班员定位补录问题。
            if re.fullmatch(r"[+-]?\d+\.\d+", text):
                return None, _INVALID_REASON["fraction"]
            return None, _INVALID_REASON["non_numeric"]
        number = int(text)
    else:
        return None, _INVALID_REASON["non_numeric"]

    if number < 0:
        return None, _INVALID_REASON["negative"]
    if number == 0:
        return None, _INVALID_REASON["zero"]
    return number, ""


def count_from_values(values: dict[str, Any] | None) -> tuple[Any, bool]:
    """从动作参数里取样本数量，返回 ``(原始值, 是否显式提供)``。"""
    if not values:
        return None, False
    for key in COUNT_KEYS:
        if key in values:
            return values[key], True
    # 有些调用会把字段放在 data/fields/payload 里。
    for nested_key in ("data", "fields", "payload", "values"):
        nested = values.get(nested_key)
        if isinstance(nested, dict):
            found, provided = count_from_values(nested)
            if provided:
                return found, True
    return None, False


def display_value(value: Any) -> Any:
    """原值展示：保留空值/字符串的历史格式，便于补录前后复查。"""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return repr(value)
    return value


def _now() -> str:
    return datetime.datetime.now().isoformat()


def build_validation_detail(
    entry: dict[str, Any],
    *,
    raw_value: Any = None,
    raw_provided: bool = False,
    action: str = "确认出样",
    accepted: bool | None = None,
    reason: str | None = None,
    task_no: str | None = None,
) -> dict[str, Any]:
    """构建一条出样校验明细，并同步到分层记录。

    明细同时保留中文字段和英文别名，派发清单直接复用这份明细，避免两边
    各自再解析一次样本数量而出现口径差异。
    """
    raw = raw_value if raw_provided else entry.get("样本数量")
    normalized, invalid_reason = parse_sample_count(raw)
    dispatchable = normalized is not None
    strategy_no = str(entry.get("原策略编号") or entry.get("策略编号") or "")

    if reason is None:
        if dispatchable:
            if accepted:
                reason = f"样本数量校验通过，已接受派发任务 {task_no}" if task_no else "样本数量校验通过，可派发"
            else:
                reason = "样本数量校验通过，等待确认出样"
        else:
            reason = invalid_reason

    # accepted 表示“派发是否已经真正被接受”，与“数量是否可派发”分开：
    # 补录完成后数量可派发，但在再次确认前派发仍是未接受状态。
    accepted_value = bool(accepted)
    detail: dict[str, Any] = {
        "策略编号": strategy_no,
        "原策略编号": strategy_no,
        "样本数量原值": display_value(raw),
        "有效样本数量": normalized,
        "可派发": dispatchable,
        "校验状态": "可派发" if dispatchable else "暂无可用数量",
        "派发已接受": accepted_value,
        "已接受": accepted_value,
        "原因": reason,
        "动作": action,
        "更新时间": _now(),
        # 英文别名，供跨模块消费方使用。
        "status": "可派发" if dispatchable else "暂无可用数量",
        "dispatchable": dispatchable,
        "available_count": normalized,
        "accepted": accepted_value,
        "reason": reason,
    }
    if task_no:
        detail["任务编号"] = task_no
        detail["task_no"] = task_no

    entry["当前校验明细"] = detail
    entry["校验状态"] = detail["校验状态"]
    entry["校验原因"] = reason
    entry["有效样本数量"] = normalized
    entry["可派发"] = dispatchable
    entry["派发已接受"] = accepted_value
    entry["派发状态"] = "已接受" if accepted_value else ("待确认" if dispatchable else "待补录")
    entry["派发原因"] = reason

    history = entry.setdefault("出样校验明细", [])
    history.append(dict(detail))
    # 明细列表只用于复查，限制长度避免无上限增长。
    del history[:-50]

    return detail


def refresh_validation(entry: dict[str, Any], *, action: str = "校验") -> dict[str, Any]:
    """按当前样本数量字段刷新校验结果（不再触发任何派发）。"""
    return build_validation_detail(entry, action=action)


def ensure_validation(entry: dict[str, Any]) -> dict[str, Any]:
    """历史记录没有校验明细时补一份，查看/列表接口保持可读。"""
    detail = entry.get("当前校验明细")
    if detail is None:
        detail = build_validation_detail(entry, action="历史记录")
    return detail


def record_invalid_attempt(entry: dict[str, Any], raw: Any, reason: str, action: str) -> None:
    """记录一次无效样本量尝试，供补录后复查补录前的值。"""
    records = entry.setdefault("无效样本记录", [])
    records.append({
        "动作": action,
        "样本数量原值": display_value(raw),
        "无效值": display_value(raw),
        "原因": reason,
        "时间": _now(),
    })
    del records[:-50]
    entry["补录前无效值"] = display_value(raw)


def dispatchable_details() -> list[dict[str, Any]]:
    """派发清单数据源：只返回出样校验明细中“可派发”的记录。

    待补录（暂无可用数量）的策略不会出现在这里，因此不会占用空闲派发任务；
    尚未确认出样的草稿/采样中策略也不进入派发清单。
    """
    details: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for entry in store.rows("sample_strata"):
        if entry.get("status") != "已出样":
            continue
        if entry.get("当前校验明细") is None:
            refresh_validation(entry)
        detail = entry.get("当前校验明细")
        if not detail or not detail.get("可派发"):
            continue
        # 同一策略可能有多条历史分层记录，派发清单按策略编号只保留一条有效范围。
        key = str(detail.get("原策略编号") or detail.get("策略编号") or "")
        current = seen.get(key)
        if current is None or (detail.get("派发已接受") and not current.get("派发已接受")):
            seen[key] = detail
    details.extend(seen.values())
    return details

