package com.stockmonitor.model;

import java.util.List;

/**
 * 单次库存检查的结果。
 *
 * @param detail       配送/可购信息的人类可读描述（如「お届け予定日：10/23」）
 * @param pickupStores 可到店取货的门店名称
 * @param error        查询失败时的错误信息，成功时为 null
 */
public record CheckResult(Sku sku, StockState state, String detail, List<String> pickupStores,
                          long latencyMs, String error) {

    public static CheckResult of(Sku sku, StockState state, String detail, List<String> pickupStores) {
        return new CheckResult(sku, state, detail, pickupStores == null ? List.of() : List.copyOf(pickupStores), 0, null);
    }

    public static CheckResult failed(Sku sku, String error, long latencyMs) {
        return new CheckResult(sku, StockState.UNKNOWN, null, List.of(), latencyMs, error);
    }

    public CheckResult withLatency(long ms) {
        return new CheckResult(sku, state, detail, pickupStores, ms, error);
    }

    public boolean isSuccess() {
        return error == null;
    }

    public boolean isAvailable() {
        return state == StockState.AVAILABLE;
    }
}
