package com.stockmonitor.monitor;

import com.stockmonitor.model.CheckResult;
import com.stockmonitor.model.Sku;
import com.stockmonitor.model.StockState;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 产品页 HTML 兜底解析：在页面内嵌的 JSON 中，查找部件号附近的 isBuyable / 在庫状态。
 * 产品页主要是静态内容，可靠性低于 JSON 接口，仅在接口不可用时使用。
 */
public final class ProductPageParser {
    private static final Pattern BUYABLE = Pattern.compile("\"isBuyable\"\\s*:\\s*(true|false)");
    private static final int WINDOW = 1500;

    private ProductPageParser() {
    }

    public static CheckResult parse(String html, Sku sku) {
        String part = sku.partNumber;
        int idx = html.indexOf(part);
        if (idx < 0) {
            // 部分页面里部件号不带「/A」后缀
            idx = html.indexOf(part.replace("/A", ""));
        }
        if (idx < 0) {
            return CheckResult.of(sku, StockState.UNKNOWN, "产品页中未找到部件号", List.of());
        }
        String window = html.substring(idx, Math.min(html.length(), idx + WINDOW));
        Matcher m = BUYABLE.matcher(window);
        if (m.find()) {
            boolean buyable = Boolean.parseBoolean(m.group(1));
            return CheckResult.of(sku, buyable ? StockState.AVAILABLE : StockState.UNAVAILABLE,
                    buyable ? "产品页显示可购买" : "产品页显示不可购买", List.of());
        }
        if (window.contains("在庫切れ") || window.contains("売り切れ") || window.contains("sold out")) {
            return CheckResult.of(sku, StockState.UNAVAILABLE, "产品页显示在庫切れ", List.of());
        }
        return CheckResult.of(sku, StockState.UNKNOWN, "产品页无可用库存字段", List.of());
    }
}
