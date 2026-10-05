package com.stockmonitor.model;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/** 检测到有货时派发给各提醒渠道的事件。 */
public record AvailabilityEvent(CheckResult result, String buyUrl, LocalDateTime time, boolean test) {

    private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    public Sku sku() {
        return result.sku();
    }

    public String title() {
        return (test ? "[测试] " : "") + "iPhone 有货: " + sku().displayName();
    }

    public String message() {
        StringBuilder sb = new StringBuilder();
        if (test) {
            sb.append("这是一条测试提醒，用于验证提醒渠道是否可用。\n");
        }
        sb.append("型号: ").append(sku().displayName()).append('\n');
        if (result.detail() != null && !result.detail().isBlank()) {
            sb.append("配送: ").append(result.detail()).append('\n');
        }
        if (!result.pickupStores().isEmpty()) {
            sb.append("可取货门店: ").append(String.join(", ", result.pickupStores())).append('\n');
        }
        sb.append("时间: ").append(time.format(FMT)).append('\n');
        sb.append("购买: ").append(buyUrl);
        return sb.toString();
    }
}
