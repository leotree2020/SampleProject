package com.stockmonitor.http;

import com.stockmonitor.config.AppConfig;
import okhttp3.ConnectionPool;
import okhttp3.OkHttpClient;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * 构建 OkHttp 客户端。启用代理池时为每个代理构建一个共享连接池/Cookie 的客户端，
 * 每次请求轮换取用。
 */
public class HttpClientFactory {
    private final List<OkHttpClient> clients = new ArrayList<>();
    private final List<String> labels = new ArrayList<>();
    private final ProxyManager proxies;
    private final SessionCookieJar cookieJar = new SessionCookieJar();

    public HttpClientFactory(AppConfig.Http http, ProxyManager proxies) {
        this.proxies = proxies;
        OkHttpClient base = new OkHttpClient.Builder()
                .connectTimeout(Duration.ofSeconds(http.connectTimeoutSeconds))
                .readTimeout(Duration.ofSeconds(http.readTimeoutSeconds))
                .writeTimeout(Duration.ofSeconds(http.writeTimeoutSeconds))
                .connectionPool(new ConnectionPool(http.maxIdleConnections, http.keepAliveMinutes, TimeUnit.MINUTES))
                .cookieJar(cookieJar)
                .followRedirects(true)
                .retryOnConnectionFailure(true)
                .build();
        if (proxies == null || proxies.isEmpty()) {
            clients.add(base);
            labels.add("direct");
            return;
        }
        proxies.installSocksAuthenticator();
        for (ProxyManager.ProxyEntry e : proxies.entries()) {
            clients.add(base.newBuilder()
                    .proxy(e.proxy())
                    .proxyAuthenticator(ProxyManager.httpAuthenticator(e))
                    .build());
            labels.add(e.label());
        }
    }

    public record Lease(OkHttpClient client, String label) {
    }

    public Lease next() {
        if (proxies == null || proxies.isEmpty()) {
            return new Lease(clients.get(0), labels.get(0));
        }
        int idx = proxies.entries().indexOf(proxies.next()); // 轮询或随机，由 rotate-strategy 决定
        return new Lease(clients.get(idx), labels.get(idx));
    }

    public SessionCookieJar cookieJar() {
        return cookieJar;
    }

    public void shutdown() {
        OkHttpClient c = clients.get(0);
        c.dispatcher().executorService().shutdown();
        c.connectionPool().evictAll();
    }
}
