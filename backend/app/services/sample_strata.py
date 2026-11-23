"""样本分层领域服务：在通用骨架之上维护样本数量的校验与补录。"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService
from app.services.sample_count import (
    SAMPLE_LOCK,
    build_validation_detail,
    count_from_values,
    display_value,
    ensure_validation,
    parse_sample_count,
    record_invalid_attempt,
    refresh_validation,
)


class SampleStrataService(BaseModuleService):
    MODULE = "sample_strata"
    ENTITY = "分层策略"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["策略编号", "特征范围", "分层字段", "采样比例", "样本数量", "均衡算法", "覆盖检查", "最后采样"]
    REQUIRED_FIELDS = ["策略编号", "特征范围", "分层字段"]
    STATUS_ORDER = ["草稿", "采样中", "已出样", "覆盖不足"]
    ACTION_RULES = {"启动采样": "采样中", "确认出样": "已出样", "标记不足": "覆盖不足"}
    NEGATIVE_ACTIONS = []
    # 补录样本数量不改变状态，但仍需要走领域逻辑。
    EXTRA_ACTIONS = ("补录样本数量", "补录")

    def after_create(self, entry: dict[str, Any], values: dict[str, Any]) -> None:
        # 保留登记时的策略编号；后续补录/派发都以此复查来源，不因字段改写而丢失。
        entry["原策略编号"] = entry.get("策略编号", "")
        # 登记时填写了样本数量也按同一套规则归一；非法值原样保留，
        # 由出样校验明细标记为“暂无可用数量”，不阻止先登记策略。
        normalized, _ = parse_sample_count(entry.get("样本数量"))
        if normalized is not None:
            entry["样本数量"] = normalized
        refresh_validation(entry, action="登记")

    def list_entries(self, **kwargs: Any) -> tuple[list[dict[str, Any]], int]:
        # 历史数据可能没有校验明细，列表里同步补齐但不改变数量/状态。
        rows, total = super().list_entries(**kwargs)
        for row in rows:
            ensure_validation(row)
        return rows, total

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        with SAMPLE_LOCK:
            entry = self.get_entry(entry_id)
            if entry is None:
                return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
            if action in self.EXTRA_ACTIONS:
                return self._record_samples(entry, values)
            if action == "确认出样":
                return self._confirm_samples(entry, values)
            return super().run_action(entry_id, action, values)

    def _record_samples(
        self, entry: dict[str, Any], values: dict[str, Any] | None
    ) -> tuple[dict[str, Any] | None, str]:
        """补录样本数量：只更新数量，不触发派发，也不替值班员做确认。"""
        raw, provided = count_from_values(values)
        if not provided:
            return None, "补录样本数量需要提供样本数量"
        if entry.get("派发已接受"):
            # 派发已经接受后再改数量会破坏派发清单与任务的一致性。
            return None, f"该策略已派发为 {entry.get('派发任务编号','')}，不能再补录样本数量"
        normalized, reason = parse_sample_count(raw)
        if normalized is None:
            record_invalid_attempt(entry, raw, reason, "补录样本数量")
            build_validation_detail(
                entry,
                raw_value=raw,
                raw_provided=True,
                action="补录样本数量",
                accepted=False,
                reason=reason,
            )
            return None, f"补录失败：{reason}"

        entry["样本数量"] = normalized
        entry["派发前状态"] = entry.get("status") or "采样中"
        entry["补录样本数量原值"] = display_value(raw)
        detail = build_validation_detail(
            entry,
            raw_value=raw,
            raw_provided=True,
            action="补录样本数量",
            accepted=False,
            reason="样本数量已补录，待值班员再次确认出样后派发",
        )
        entry["补录时间"] = detail["更新时间"]
        return entry, f"样本数量已补录为 {normalized}，待再次确认出样"

    def _confirm_samples(
        self, entry: dict[str, Any], values: dict[str, Any] | None
    ) -> tuple[dict[str, Any] | None, str]:
        """确认出样：采样阶段可以完成，但只有合法数量才进入可派发范围。

        数量为空/小数/非数字/负数时仍记录“已出样”，同时在出样校验明细中
        标成“暂无可用数量”，由派发链路跳过，不占用空闲派发任务。
        """
        raw, provided = count_from_values(values)
        if not (provided and str(raw).strip()):
            raw = entry.get("样本数量")

        normalized, reason = parse_sample_count(raw)
        build_kwargs = {
            "raw_value": raw,
            "raw_provided": True,
            "action": "确认出样",
        }
        already_dispatched = bool(entry.get("派发已接受"))
        if normalized is None and already_dispatched:
            # 已派发的策略不接受无效确认，也不回退任何数量/状态。
            record_invalid_attempt(entry, raw, reason, "确认出样")
            return None, f"已派发的策略不接受无效数量确认：{reason}"

        entry["status"] = "已出样"
        entry["pending"] = True
        entry["abnormal"] = False

        if normalized is None:
            record_invalid_attempt(entry, raw, reason, "确认出样")
            stored_normalized, _ = parse_sample_count(entry.get("样本数量"))
            if stored_normalized is not None:
                # 本次输入无效，但已登记过合法数量：沿用它，不把无效值当样本量。
                build_validation_detail(
                    entry,
                    raw_value=entry.get("样本数量"),
                    raw_provided=True,
                    action="确认出样",
                    accepted=False,
                    reason=f"本次确认输入无效（{reason}），沿用已登记的有效数量 {stored_normalized}，可派发",
                )
                return entry, (
                    f"本次输入无效（{reason}），沿用已登记的有效样本量 {stored_normalized}"
                )
            build_validation_detail(
                entry,
                accepted=False,
                reason=reason,
                **build_kwargs,
            )
            return entry, f"{self.ENTITY}已确认出样，暂无可用样本量，待补录：{reason}"

        entry["样本数量"] = normalized
        build_validation_detail(
            entry,
            accepted=already_dispatched,
            reason=(
                f"样本数量校验通过，已接受派发任务 {entry.get('派发任务编号','')}"
                if already_dispatched
                else "样本数量校验通过，可派发，等待标注派发消费"
            ),
            task_no=str(entry.get("派发任务编号") or "") or None,
            **build_kwargs,
        )
        if already_dispatched:
            return entry, f"{self.ENTITY}已确认出样（样本数量 {normalized}），派发任务已存在"
        return entry, f"{self.ENTITY}已确认出样（样本数量 {normalized}）"
