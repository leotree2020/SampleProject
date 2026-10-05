package com.stockmonitor.monitor;

import com.fasterxml.jackson.databind.JsonNode;
import com.stockmonitor.model.CheckResult;
import com.stockmonitor.model.Sku;
import com.stockmonitor.model.StockState;

import java.util.ArrayList;
import java.util.List;

/**
 * 解析 /shop/fulfillment-messages 的返回，同时判断「配送」与「门店取货」：
 * body.content.deliveryMessage.PART.regular.{isBuyable, deliveryOptionMessages[].displayName}
 * body.content.pickupMessage.stores[].partsAvailability.PART.pickupDisplay == "available"
 */
public final class FulfillmentJsonParser {
    private FulfillmentJsonParser() {
    }

    public static CheckResult parse(JsonNode root, Sku sku) {
        JsonNode content = root.path("body").path("content");
        String part = sku.partNumber;

        boolean found = false;
        boolean deliverable = false;
        String deliveryText = null;

        JsonNode regular = content.path("deliveryMessage").path(part).path("regular");
        if (!regular.isMissingNode()) {
            found = true;
            deliverable = regular.path("isBuyable").asBoolean(false)
                    || regular.path("buyability").path("isBuyable").asBoolean(false);
            JsonNode opts = regular.path("deliveryOptionMessages");
            if (opts.isArray() && !opts.isEmpty()) {
                deliveryText = opts.get(0).path("displayName").asText(null);
            }
            if (deliveryText == null) {
                deliveryText = regular.path("deliveryOptions").path(0).path("date").asText(null);
            }
        }

        List<String> pickup = new ArrayList<>();
        for (JsonNode store : content.path("pickupMessage").path("stores")) {
            JsonNode pa = store.path("partsAvailability").path(part);
            if (pa.isMissingNode()) {
                continue;
            }
            found = true;
            if ("available".equalsIgnoreCase(pa.path("pickupDisplay").asText())) {
                String name = store.path("storeName").asText(store.path("storeNumber").asText("?"));
                String quote = pa.path("pickupSearchQuote").asText("");
                pickup.add(quote.isBlank() ? "Apple " + name : "Apple " + name + "（" + stripTags(quote) + "）");
            }
        }

        if (!found) {
            return CheckResult.of(sku, StockState.UNKNOWN, "返回中未找到部件号 " + part, List.of());
        }
        boolean available = deliverable || !pickup.isEmpty();
        String detail = deliveryText != null ? stripTags(deliveryText) : (deliverable ? "配送可" : "配送不可");
        return CheckResult.of(sku, available ? StockState.AVAILABLE : StockState.UNAVAILABLE, detail, pickup);
    }

    private static String stripTags(String s) {
        return s.replaceAll("<[^>]+>", "").trim();
    }
}
