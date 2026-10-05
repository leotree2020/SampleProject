package com.stockmonitor.http;

import okhttp3.Request;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ThreadLocalRandom;

/** 生成与日本地区桌面浏览器一致的请求头。 */
public final class BrowserHeaders {
    public static final List<String> DEFAULT_USER_AGENTS = List.of(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"
    );

    private final String userAgent;
    private final Map<String, String> extra;

    /** 每个会话固定一个 UA（同一会话里频繁换 UA 反而更可疑）。 */
    public BrowserHeaders(List<String> userAgents, Map<String, String> extra) {
        List<String> pool = (userAgents == null || userAgents.isEmpty()) ? DEFAULT_USER_AGENTS : userAgents;
        this.userAgent = pool.get(ThreadLocalRandom.current().nextInt(pool.size()));
        this.extra = extra == null ? Map.of() : extra;
    }

    public String userAgent() {
        return userAgent;
    }

    public Request.Builder apply(Request.Builder b, String referer, boolean json) {
        b.header("User-Agent", userAgent)
                .header("Accept", json ? "application/json, text/plain, */*"
                        : "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                .header("Accept-Language", "ja-JP,ja;q=0.9,en-US;q=0.7,en;q=0.6")
                .header("Cache-Control", "no-cache")
                .header("Pragma", "no-cache");
        if (referer != null) {
            b.header("Referer", referer);
        }
        if (json) {
            b.header("Sec-Fetch-Dest", "empty").header("Sec-Fetch-Mode", "cors").header("Sec-Fetch-Site", "same-origin");
        } else {
            b.header("Sec-Fetch-Dest", "document").header("Sec-Fetch-Mode", "navigate").header("Sec-Fetch-Site", "none");
        }
        extra.forEach(b::header);
        return b;
    }
}
