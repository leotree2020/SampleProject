package com.stockmonitor.monitor;

import com.fasterxml.jackson.databind.JsonNode;
import com.stockmonitor.model.CheckResult;
import com.stockmonitor.model.Sku;
import com.stockmonitor.model.StockState;

import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * 解析 /shop/buyability-message 的返回：
 * {"body":{"content":{"buyabilityMessage":{"sth":{"PART":{"isBuyable":true,...}}}}}}
 */
public final class BuyabilityParser {
    private BuyabilityParser() {
    }

    public static CheckResult parse(JsonNode root, Sku sku) {
        JsonNode node = root.path("body").path("content").path("buyabilityMessage").path("sth").path(sku.partNumber);
        if (node.isMissingNode()) {
            node = findPartNode(root, sku.partNumber); // 结构变动时的兜底
        }
        if (node == null || node.isMissingNode() || !node.has("isBuyable")) {
            return CheckResult.of(sku, StockState.UNKNOWN, "返回中未找到部件号 " + sku.partNumber, List.of());
        }
        boolean buyable = node.path("isBuyable").asBoolean(false);
        String detail = buyable ? "オンラインで購入可能（线上可购）" : "現在購入不可（线上不可购）";
        return CheckResult.of(sku, buyable ? StockState.AVAILABLE : StockState.UNAVAILABLE, detail, List.of());
    }

    /** 递归查找 key 为部件号且包含 isBuyable 的节点。 */
    static JsonNode findPartNode(JsonNode node, String part) {
        if (node == null || !node.isContainerNode()) {
            return null;
        }
        if (node.isObject()) {
            JsonNode direct = node.get(part);
            if (direct != null && direct.has("isBuyable")) {
                return direct;
            }
            for (Iterator<Map.Entry<String, JsonNode>> it = node.fields(); it.hasNext(); ) {
                JsonNode found = findPartNode(it.next().getValue(), part);
                if (found != null) {
                    return found;
                }
            }
        } else {
            for (JsonNode child : node) {
                JsonNode found = findPartNode(child, part);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }
}
