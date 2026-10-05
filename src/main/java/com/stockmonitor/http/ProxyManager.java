package com.stockmonitor.http;

import com.stockmonitor.config.AppConfig;
import okhttp3.Authenticator;
import okhttp3.Credentials;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.Proxy;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicInteger;

/** 代理池：支持 http:// 与 socks5://（可带 user:pass@），按轮询或随机方式选取。 */
public class ProxyManager {
    private static final Logger log = LoggerFactory.getLogger(ProxyManager.class);

    public record ProxyEntry(Proxy proxy, String username, String password, String label) {
        public boolean hasAuth() {
            return username != null && !username.isEmpty();
        }
    }

    private final List<ProxyEntry> entries = new ArrayList<>();
    private final boolean random;
    private final AtomicInteger cursor = new AtomicInteger();

    public ProxyManager(AppConfig.Proxy cfg) {
        this.random = "random".equalsIgnoreCase(cfg.rotateStrategy);
        if (!cfg.enabled) {
            return;
        }
        for (String raw : cfg.proxies) {
            try {
                entries.add(parse(raw));
            } catch (Exception e) {
                log.warn("忽略无效代理 '{}': {}", raw, e.getMessage());
            }
        }
        log.info("代理池已启用：{} 个代理，策略 {}", entries.size(), cfg.rotateStrategy);
    }

    static ProxyEntry parse(String raw) {
        URI uri = URI.create(raw.trim());
        String scheme = uri.getScheme() == null ? "http" : uri.getScheme().toLowerCase();
        Proxy.Type type = scheme.startsWith("socks") ? Proxy.Type.SOCKS : Proxy.Type.HTTP;
        int port = uri.getPort() > 0 ? uri.getPort() : (type == Proxy.Type.SOCKS ? 1080 : 8080);
        String user = null;
        String pass = null;
        if (uri.getRawUserInfo() != null) {
            String[] parts = uri.getRawUserInfo().split(":", 2);
            user = URLDecoder.decode(parts[0], StandardCharsets.UTF_8);
            pass = parts.length > 1 ? URLDecoder.decode(parts[1], StandardCharsets.UTF_8) : "";
        }
        Proxy proxy = new Proxy(type, InetSocketAddress.createUnresolved(uri.getHost(), port));
        return new ProxyEntry(proxy, user, pass, scheme + "://" + uri.getHost() + ":" + port);
    }

    public boolean isEmpty() {
        return entries.isEmpty();
    }

    public List<ProxyEntry> entries() {
        return entries;
    }

    public ProxyEntry next() {
        if (entries.isEmpty()) {
            return null;
        }
        int idx = random ? ThreadLocalRandom.current().nextInt(entries.size())
                : Math.floorMod(cursor.getAndIncrement(), entries.size());
        return entries.get(idx);
    }

    /** HTTP 代理认证（407）。 */
    public static Authenticator httpAuthenticator(ProxyEntry entry) {
        if (entry == null || !entry.hasAuth() || entry.proxy().type() != Proxy.Type.HTTP) {
            return Authenticator.NONE;
        }
        String credential = Credentials.basic(entry.username(), entry.password());
        return (route, response) -> {
            if (response.request().header("Proxy-Authorization") != null) {
                return null; // 已尝试过，避免死循环
            }
            return response.request().newBuilder().header("Proxy-Authorization", credential).build();
        };
    }

    /** SOCKS5 认证需通过 JDK 全局 Authenticator 提供。 */
    public void installSocksAuthenticator() {
        boolean anySocksAuth = entries.stream().anyMatch(e -> e.hasAuth() && e.proxy().type() == Proxy.Type.SOCKS);
        if (!anySocksAuth) {
            return;
        }
        java.net.Authenticator.setDefault(new java.net.Authenticator() {
            @Override
            protected PasswordAuthentication getPasswordAuthentication() {
                for (ProxyEntry e : entries) {
                    InetSocketAddress addr = (InetSocketAddress) e.proxy().address();
                    if (e.hasAuth() && addr.getHostString().equalsIgnoreCase(getRequestingHost())
                            && addr.getPort() == getRequestingPort()) {
                        return new PasswordAuthentication(e.username(), e.password().toCharArray());
                    }
                }
                return null;
            }
        });
    }
}
