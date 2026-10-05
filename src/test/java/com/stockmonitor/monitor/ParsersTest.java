package com.stockmonitor.monitor;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.stockmonitor.config.AppConfig;
import com.stockmonitor.model.CheckResult;
import com.stockmonitor.model.Sku;
import com.stockmonitor.model.StockState;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ParsersTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    private final Sku sku = new Sku("MXXA1J/A", "iPhone Duo 256GB");

    @Test
    void buyabilityAvailable() throws Exception {
        String body = "{\"body\":{\"content\":{\"buyabilityMessage\":{\"sth\":{\"MXXA1J/A\":{\"isBuyable\":true}}}}}}";
        assertEquals(StockState.AVAILABLE, BuyabilityParser.parse(JSON.readTree(body), sku).state());
    }

    @Test
    void buyabilityUnavailableAndMissing() throws Exception {
        String no = "{\"body\":{\"content\":{\"buyabilityMessage\":{\"sth\":{\"MXXA1J/A\":{\"isBuyable\":false}}}}}}";
        assertEquals(StockState.UNAVAILABLE, BuyabilityParser.parse(JSON.readTree(no), sku).state());
        assertEquals(StockState.UNKNOWN, BuyabilityParser.parse(JSON.readTree("{\"body\":{}}"), sku).state());
    }

    @Test
    void buyabilityFallbackSearch() throws Exception {
        String moved = "{\"data\":[{\"x\":{\"MXXA1J/A\":{\"isBuyable\":true}}}]}";
        assertEquals(StockState.AVAILABLE, BuyabilityParser.parse(JSON.readTree(moved), sku).state());
    }

    @Test
    void fulfillmentPickupAvailable() throws Exception {
        String body = """
                {"body":{"content":{
                  "deliveryMessage":{"MXXA1J/A":{"regular":{"isBuyable":false,
                     "deliveryOptionMessages":[{"displayName":"現在在庫切れ"}]}}},
                  "pickupMessage":{"stores":[
                    {"storeNumber":"R079","storeName":"銀座","partsAvailability":{"MXXA1J/A":{"pickupDisplay":"available","pickupSearchQuote":"<span>本日</span>"}}},
                    {"storeNumber":"R128","storeName":"渋谷","partsAvailability":{"MXXA1J/A":{"pickupDisplay":"unavailable"}}}
                  ]}}}}""";
        CheckResult r = FulfillmentJsonParser.parse(JSON.readTree(body), sku);
        assertEquals(StockState.AVAILABLE, r.state());
        assertEquals(List.of("Apple 銀座（本日）"), r.pickupStores());
        assertEquals("現在在庫切れ", r.detail());
    }

    @Test
    void fulfillmentDeliveryOnly() throws Exception {
        String body = """
                {"body":{"content":{"deliveryMessage":{"MXXA1J/A":{"regular":{
                   "buyability":{"isBuyable":true},
                   "deliveryOptionMessages":[{"displayName":"お届け予定日：10/23"}]}}}}}}""";
        CheckResult r = FulfillmentJsonParser.parse(JSON.readTree(body), sku);
        assertEquals(StockState.AVAILABLE, r.state());
        assertTrue(r.pickupStores().isEmpty());
    }

    @Test
    void fulfillmentNothingFound() throws Exception {
        assertEquals(StockState.UNKNOWN,
                FulfillmentJsonParser.parse(JSON.readTree("{\"body\":{\"content\":{}}}"), sku).state());
    }

    @Test
    void productPage() {
        String html = "<script>{\"part\":\"MXXA1J/A\",\"price\":1,\"isBuyable\":false}</script>";
        assertEquals(StockState.UNAVAILABLE, ProductPageParser.parse(html, sku).state());
        assertEquals(StockState.UNKNOWN, ProductPageParser.parse("<html></html>", sku).state());
    }

    @Test
    void urlsAreBuiltForJapan() {
        AppConfig.Monitor m = new AppConfig.Monitor();
        m.stores = List.of("R079");
        m.postalCode = "100-0005";
        String url = AppleStoreClient.fulfillmentUrl(m, sku).toString();
        assertTrue(url.startsWith("https://www.apple.com/jp/shop/fulfillment-messages?"), url);
        assertTrue(url.contains("parts.0=MXXA1J%2FA") || url.contains("parts.0=MXXA1J/A"), url);
        assertTrue(url.contains("store=R079") && url.contains("location=100-0005"), url);
        assertEquals("https://www.apple.com/jp/shop/buy-iphone/iphone-duo",
                AppleStoreClient.join("https://www.apple.com/jp/", "/shop/buy-iphone/iphone-duo"));
    }
}
