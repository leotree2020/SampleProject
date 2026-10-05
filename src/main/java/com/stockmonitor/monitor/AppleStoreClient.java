package com.stockmonitor.monitor;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.stockmonitor.config.AppConfig;
import com.stockmonitor.config.ConfigManager;
import com.stockmonitor.http.BrowserHeaders;
import com.stockmonitor.http.HttpClientFactory;
import com.stockmonitor.model.CheckResult;
import com.stockmonitor.model.Sku;
import okhttp3.HttpUrl;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.ResponseBody;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.util.List;

/** 查询单个 SKU 的库存（带重试）。每次请求都实时读取配置，支持热更新。 */
public class AppleStoreClient {
    private static final Logger log = LoggerFactory.getLogger(AppleStoreClient.class);
    private static final ObjectMapper JSON = new ObjectMapper();

    private final ConfigManager configs;
    private final HttpClientFactory http;
    private final BrowserHeaders headers;
    private volatile boolean warmedUp;

    public AppleStoreClient(ConfigManager configs, HttpClientFactory http, BrowserHeaders headers) {
        this.configs = configs;
        this.http = http;
        this.headers = headers;
    }

    public String productPageUrl() {
        return join(configs.get().monitor.baseUrl, configs.activeModel().productPagePath);
    }

    public String buyUrl(Sku sku) {
        return (sku.buyUrl != null && !sku.buyUrl.isBlank()) ? sku.buyUrl : productPageUrl();
    }

    public CheckResult check(Sku sku) throws InterruptedException {
        AppConfig.Retry retry = configs.get().monitor.retry;
        long start = System.nanoTime();
        IOException last = null;
        for (int attempt = 1; attempt <= Math.max(1, retry.maxAttempts); attempt++) {
            try {
                return checkOnce(sku).withLatency((System.nanoTime() - start) / 1_000_000);
            } catch (HttpStatusException e) {
                last = e;
                if (!e.retryable()) {
                    break;
                }
                if (e.throttled()) {
                    warmedUp = false; // 被拦截后重新访问产品页获取新 Cookie
                }
            } catch (IOException e) {
                last = e;
            }
            if (attempt < retry.maxAttempts) {
                long wait = RetryPolicy.backoffMs(retry, attempt);
                log.debug("{} 第 {} 次查询失败（{}），{}ms 后重试", sku.partNumber, attempt, last.getMessage(), wait);
                Thread.sleep(wait);
            }
        }
        long ms = (System.nanoTime() - start) / 1_000_000;
        return CheckResult.failed(sku, last == null ? "unknown" : last.getMessage(), ms);
    }

    CheckResult checkOnce(Sku sku) throws IOException {
        AppConfig.Monitor m = configs.get().monitor;
        warmUpIfNeeded();
        return switch (m.checkMode) {
            case "fulfillment" -> FulfillmentJsonParser.parse(getJson(fulfillmentUrl(m, sku)), sku);
            case "product-page" -> ProductPageParser.parse(get(productPageUrl(), false), sku);
            default -> BuyabilityParser.parse(getJson(buyabilityUrl(m, sku)), sku);
        };
    }

    static HttpUrl buyabilityUrl(AppConfig.Monitor m, Sku sku) {
        return HttpUrl.get(join(m.baseUrl, m.buyabilityPath)).newBuilder()
                .addQueryParameter("parts.0", sku.partNumber)
                .build();
    }

    static HttpUrl fulfillmentUrl(AppConfig.Monitor m, Sku sku) {
        HttpUrl.Builder b = HttpUrl.get(join(m.baseUrl, m.fulfillmentPath)).newBuilder()
                .addQueryParameter("fae", "true")
                .addQueryParameter("pl", "true")
                .addQueryParameter("mts.0", "regular")
                .addQueryParameter("mts.1", "compact")
                .addQueryParameter("parts.0", sku.partNumber);
        List<String> stores = m.stores == null ? List.of() : m.stores;
        if (!stores.isEmpty()) {
            b.addQueryParameter("store", stores.get(0)).addQueryParameter("searchNearby", "true");
        }
        if (m.postalCode != null && !m.postalCode.isBlank()) {
            b.addQueryParameter("location", m.postalCode);
        }
        return b.build();
    }

    /** 先以浏览器方式访问一次产品页，拿到 Apple 下发的会话 Cookie。 */
    private void warmUpIfNeeded() {
        if (warmedUp) {
            return;
        }
        try {
            get(productPageUrl(), false);
            log.debug("会话预热完成：{}", productPageUrl());
        } catch (IOException e) {
            log.debug("会话预热失败（忽略）：{}", e.getMessage());
        }
        warmedUp = true;
    }

    private JsonNode getJson(HttpUrl url) throws IOException {
        String body = get(url.toString(), true);
        try {
            return JSON.readTree(body);
        } catch (IOException e) {
            throw new IOException("返回不是合法 JSON（可能被重定向到排队/验证页）", e);
        }
    }

    private String get(String url, boolean json) throws IOException {
        HttpClientFactory.Lease lease = http.next();
        Request req = headers.apply(new Request.Builder().url(url).get(), json ? productPageUrl() : null, json).build();
        try (Response resp = lease.client().newCall(req).execute()) {
            if (!resp.isSuccessful()) {
                throw new HttpStatusException(resp.code(), url + " via " + lease.label());
            }
            ResponseBody body = resp.body();
            return body == null ? "" : body.string();
        }
    }

    static String join(String base, String path) {
        if (path == null || path.isBlank()) {
            return base;
        }
        return base.replaceAll("/+$", "") + "/" + path.replaceAll("^/+", "");
    }
}
