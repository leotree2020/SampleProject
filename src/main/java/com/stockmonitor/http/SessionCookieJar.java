package com.stockmonitor.http;

import okhttp3.Cookie;
import okhttp3.CookieJar;
import okhttp3.HttpUrl;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

/** 内存 Cookie 会话：保持 Apple 下发的会话 Cookie，使请求更接近真实浏览器。 */
public class SessionCookieJar implements CookieJar {
    private final ConcurrentHashMap<String, Cookie> store = new ConcurrentHashMap<>();

    @Override
    public void saveFromResponse(HttpUrl url, List<Cookie> cookies) {
        for (Cookie c : cookies) {
            String key = c.domain() + c.path() + "|" + c.name();
            if (c.expiresAt() < System.currentTimeMillis()) {
                store.remove(key);
            } else {
                store.put(key, c);
            }
        }
    }

    @Override
    public List<Cookie> loadForRequest(HttpUrl url) {
        long now = System.currentTimeMillis();
        List<Cookie> result = new ArrayList<>();
        store.values().removeIf(c -> c.expiresAt() < now);
        for (Cookie c : store.values()) {
            if (c.matches(url)) {
                result.add(c);
            }
        }
        return result;
    }

    public void clear() {
        store.clear();
    }
}
