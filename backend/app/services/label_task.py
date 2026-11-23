"""标注派发领域服务：派发清单只消费样本分层出样校验明细中的有效范围。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.services.sample_count import SAMPLE_LOCK, parse_sample_count


class LabelTaskService(BaseModuleService):
    MODULE = "label_task"
    ENTITY = "标注任务"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["任务编号", "样本范围", "标注类型", "标注规范", "派发人数", "截止日期", "完成进度", "派发时间"]
    REQUIRED_FIELDS = ["任务编号", "样本范围", "标注类型"]
    STATUS_ORDER = ["待派发", "标注中", "已完成", "已回收"]
    ACTION_RULES = {"派发任务": "标注中", "回收任务": "已完成", "强制完成": "已回收"}
    NEGATIVE_ACTIONS = []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        if action != "派发任务":
            return super().run_action(entry_id, action, values)
        with SAMPLE_LOCK:
            entry = self.get_entry(entry_id)
            if entry is None:
                return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
            # 来自样本分层的任务只能消费出样校验明细里已确认的有效范围；
            # 未关联策略的任务保留原来的手工派发能力。
            if entry.get("原策略编号") or entry.get("触发策略"):
                count, reason = parse_sample_count(entry.get("有效样本数量"))
                if count is None:
                    entry["派发状态"] = "待补录"
                    entry["派发原因"] = reason or "暂无可用数量，待补录"
                    return None, f"暂无可用样本量，不能派发：{entry['派发原因']}"
                entry["派发状态"] = "已接受"
                entry["派发原因"] = f"样本数量 {count} 已通过出样校验，派发已接受"
            return super().run_action(entry_id, action, values)
